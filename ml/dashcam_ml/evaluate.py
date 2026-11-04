"""Score the fine-tuned model and the stock COCO baseline on the same val images.

    python -m dashcam_ml.evaluate --weights weights/best.pt --baseline yolo26s.pt \
        --data data/processed/merged/data.yaml --out results/phase1_eval

Writes <out>.json and <out>.md with per-class AP50 and AP50-95 for both models, plus:
- "shared-class mAP": only classes COCO can express (car, bus, truck, two_wheeler,
  pedestrian, animal). This is the fair head-to-head number.
- "all-class mAP": every class with val boxes. The baseline gets 0 for classes COCO lacks
  (auto_rickshaw and the obstacles), which shows what fine-tuning adds but is not a
  like-for-like comparison, so the report labels it.
- The same numbers on each source subset (IDD images only, obstacle images only),
  because obstacle images don't label cars and IDD images don't label potholes.

Both models are run at the same image size with a low confidence threshold (0.001), which
is the standard way to compute mAP (the PR curve needs low-confidence predictions too).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

from dashcam_ml.classes import DEFAULT_CLASSES, load_classes, load_flat_mapping
from dashcam_ml.metrics import ImageEval, evaluate, mean_ap
from dashcam_ml.stats import source_of
from dashcam_ml.yolo_io import IMAGE_SUFFIXES, coords_to_box, read_yolo_labels

KEYS = ("ap50", "ap50_95")


def val_images(data_yaml: Path, split: str) -> list[Path]:
    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    root = Path(data.get("path") or data_yaml.parent)
    if not root.is_absolute():
        root = data_yaml.parent / root
    img_dir = root / data[split]
    return sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def label_path(img: Path) -> Path:
    parts = list(img.parts)
    i = len(parts) - 1 - parts[::-1].index("images")  # Ultralytics convention: last 'images' -> 'labels'
    parts[i] = "labels"
    return Path(*parts).with_suffix(".txt")


def load_gt(img: Path) -> tuple[np.ndarray, np.ndarray]:
    boxes, classes = [], []
    for cls, coords in read_yolo_labels(label_path(img)):
        b = coords_to_box(cls, coords)
        if b is not None:
            boxes.append([b.xc - b.w / 2, b.yc - b.h / 2, b.xc + b.w / 2, b.yc + b.h / 2])
            classes.append(cls)
    return np.array(boxes, dtype=float).reshape(-1, 4), np.array(classes, dtype=int)


def coco_class_remap(model_names: dict[int, str], coco_map: dict[str, int | None]) -> dict[int, int]:
    """Model class id -> our class id, for COCO classes we care about."""
    return {i: coco_map[n] for i, n in model_names.items() if coco_map.get(n) is not None}  # type: ignore[misc]


def predict(model, images: list[Path], remap: dict[int, int] | None, imgsz: int, batch: int,
            device: str | None, conf: float) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Returns per image (boxes xyxy normalised, our class ids, scores)."""
    out = []
    for i in range(0, len(images), batch):
        chunk = [str(p) for p in images[i:i + batch]]
        for r in model.predict(chunk, imgsz=imgsz, conf=conf, max_det=300, device=device, verbose=False):
            b = r.boxes
            boxes = b.xyxyn.cpu().numpy().astype(float)
            cls = b.cls.cpu().numpy().astype(int)
            scores = b.conf.cpu().numpy().astype(float)
            if remap is not None:
                keep = np.array([c in remap for c in cls], dtype=bool)
                boxes, scores = boxes[keep], scores[keep]
                cls = np.array([remap[c] for c in cls[keep]], dtype=int)
            out.append((boxes.reshape(-1, 4), cls, scores))
        print(f"  {min(i + batch, len(images))}/{len(images)} images", end="\r", flush=True)
    print()
    return out


def score(gts, preds, names: list[str], subset_idx: list[int]) -> dict[int, dict]:
    ims = [ImageEval(gts[i][0], gts[i][1], *preds[i]) for i in subset_idx]
    return evaluate(ims, len(names))


def summarise(per_class: dict[int, dict], shared: list[int], n_classes: int) -> dict:
    all_ids = list(range(n_classes))
    return {
        "per_class": per_class,
        **{f"shared_m{k}": mean_ap(per_class, shared, k) for k in KEYS},
        **{f"all_m{k}": mean_ap(per_class, all_ids, k) for k in KEYS},
    }


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def to_markdown(report: dict) -> str:
    names = report["classes"]
    shared = set(report["shared_classes"])
    L = ["# Phase 1 evaluation", "",
         f"_Generated by `python -m dashcam_ml.evaluate` at {report['generated_at']}. Do not edit by hand._", "",
         f"- Fine-tuned: `{report['models']['finetuned']['weights']}`",
         f"- Baseline (COCO-pretrained, classes remapped): `{report['models']['baseline']['weights']}`",
         f"- Data: `{report['data']}` split `{report['split']}`, imgsz {report['imgsz']}, conf {report['conf']}", ""]
    for subset, res in report["subsets"].items():
        ft, bl = res["finetuned"], res["baseline"]
        L += [f"## Subset: {subset} ({res['images']} images)", "",
              "| metric | baseline | fine-tuned |", "|---|---:|---:|",
              f"| mAP50, shared classes | {fmt(bl['shared_map50'])} | {fmt(ft['shared_map50'])} |",
              f"| mAP50-95, shared classes | {fmt(bl['shared_map50_95'])} | {fmt(ft['shared_map50_95'])} |",
              f"| mAP50, all classes* | {fmt(bl['all_map50'])} | {fmt(ft['all_map50'])} |",
              f"| mAP50-95, all classes* | {fmt(bl['all_map50_95'])} | {fmt(ft['all_map50_95'])} |", "",
              "\\* baseline scores 0 by construction on classes COCO doesn't have.", "",
              "| class | val boxes | baseline AP50 | fine-tuned AP50 | baseline AP50-95 | fine-tuned AP50-95 |",
              "|---|---:|---:|---:|---:|---:|"]
        for c, name in enumerate(names):
            b, f = bl["per_class"][c], ft["per_class"][c]
            mark = "" if c in shared else " (not in COCO)"
            L.append(f"| {name}{mark} | {f['n_gt']} | {fmt(b['ap50'])} | {fmt(f['ap50'])} | "
                     f"{fmt(b['ap50_95'])} | {fmt(f['ap50_95'])} |")
        L.append("")
    if report.get("crosscheck"):
        L += ["## Cross-check against Ultralytics' validator (fine-tuned, all images)", "",
              f"- ours: mAP50 {fmt(report['subsets']['all']['finetuned']['all_map50'])}, "
              f"mAP50-95 {fmt(report['subsets']['all']['finetuned']['all_map50_95'])}",
              f"- ultralytics: mAP50 {fmt(report['crosscheck']['map50'])}, "
              f"mAP50-95 {fmt(report['crosscheck']['map50_95'])}",
              "- These differ somewhat by design: Ultralytics pads images in rectangular batches and matches "
              "boxes by IoU rather than by confidence. Our numbers follow the COCO definition "
              "(checked against pycocotools in the tests).", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--weights", type=Path, required=True, help="fine-tuned .pt (or .onnx)")
    p.add_argument("--baseline", default="yolo26s.pt", help="stock COCO model, same size as the fine-tuned one")
    p.add_argument("--data", type=Path, default=Path("data/processed/merged/data.yaml"))
    p.add_argument("--split", default="val")
    p.add_argument("--classes", type=Path, default=DEFAULT_CLASSES)
    p.add_argument("--coco-map", type=Path, default=Path("ml/configs/coco_map.yaml"))
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=1,
                   help="images per predict call. Keep 1: Ultralytics pads a batch of mixed-size images "
                        "differently from a single image, so larger batches make scores depend on batching")
    p.add_argument("--conf", type=float, default=0.001)
    p.add_argument("--device", default=None, help="e.g. 0 for first GPU, cpu")
    p.add_argument("--limit", type=int, default=None, help="only N images (smoke test; don't quote)")
    p.add_argument("--crosscheck", action="store_true", help="also run Ultralytics val on the fine-tuned model")
    p.add_argument("--out", type=Path, default=Path("results/phase1_eval"))
    a = p.parse_args(argv)

    from ultralytics import YOLO  # heavy import, only when evaluating
    from ultralytics import __version__ as ul_version

    names = load_classes(a.classes)
    data_yaml = a.data.resolve()
    images = val_images(data_yaml, a.split)[: a.limit] if a.limit else val_images(data_yaml, a.split)
    print(f"{len(images)} {a.split} images")
    gts = [load_gt(p) for p in images]

    ft_model = YOLO(str(a.weights))
    if [ft_model.names[i] for i in sorted(ft_model.names)] != names:
        raise SystemExit(f"fine-tuned model classes {ft_model.names} != configs/classes.yaml {names}")
    bl_model = YOLO(a.baseline)
    coco_map = load_flat_mapping(a.coco_map, names)
    remap = coco_class_remap(bl_model.names, coco_map)
    shared = sorted(set(remap.values()))

    print("predicting: fine-tuned")
    ft_preds = predict(ft_model, images, None, a.imgsz, a.batch, a.device, a.conf)
    print("predicting: baseline")
    bl_preds = predict(bl_model, images, remap, a.imgsz, a.batch, a.device, a.conf)

    subsets = {"all": list(range(len(images)))}
    idd_idx = [i for i, p in enumerate(images) if source_of(p.stem) == "idd"]
    obs_idx = [i for i, p in enumerate(images) if source_of(p.stem) != "idd"]
    if idd_idx and obs_idx:  # only worth splitting out when both kinds are present
        subsets["idd"], subsets["obstacles"] = idd_idx, obs_idx

    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "ultralytics_version": ul_version,
        "data": str(a.data), "split": a.split, "imgsz": a.imgsz, "conf": a.conf, "limit": a.limit,
        "classes": names, "shared_classes": shared,
        "models": {"finetuned": {"weights": str(a.weights), "sha256": sha256(a.weights)},
                   "baseline": {"weights": a.baseline, "sha256": sha256(Path(a.baseline)),
                                "coco_to_ours": {bl_model.names[k]: names[v] for k, v in remap.items()}}},
        "subsets": {},
    }
    for subset, idx in subsets.items():
        report["subsets"][subset] = {
            "images": len(idx),
            "finetuned": summarise(score(gts, ft_preds, names, idx), shared, len(names)),
            "baseline": summarise(score(gts, bl_preds, names, idx), shared, len(names)),
        }
    if a.crosscheck:
        m = ft_model.val(data=str(data_yaml), split=a.split, imgsz=a.imgsz, batch=16, device=a.device,
                         conf=a.conf, plots=False, verbose=False)
        report["crosscheck"] = {"map50": float(m.box.map50), "map50_95": float(m.box.map)}
    if a.limit:  # never let a smoke test overwrite a real result file
        a.out = a.out.with_name(a.out.name + "_smoke")
        print(f"WARNING: --limit {a.limit} used; writing {a.out}.* (a smoke test, not a result to quote).")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = to_markdown(report)
    a.out.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
