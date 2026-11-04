"""Convert a Roboflow Universe YOLO export to our classes, as an unsplit "pool".

    python -m dashcam_ml.convert.roboflow --src data/raw/potholes_x --dataset-name potholes_x

Expected input (Roboflow "YOLOv8" / "YOLO" export, unzipped):
    <src>/data.yaml                      # has `names:` (list or {id: name})
    <src>/{train,valid,test}/images/*.jpg
    <src>/{train,valid,test}/labels/*.txt

Why a pool and not Roboflow's own split: Roboflow "augmentation" makes several altered
copies of each training photo (file names like `img12_jpg.rf.<hash>.jpg`). If we re-split
naively, copies of one photo could land in both train and val, and val mAP would be
inflated. So every image is tagged with a group key (the original photo name) and
`dashcam_ml.merge` splits by group.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from dashcam_ml.classes import DEFAULT_CLASSES, MappingError, load_classes, resolve_mapping
from dashcam_ml.yolo_io import IMAGE_SUFFIXES, YoloBox, coords_to_box, place_image, read_yolo_labels, write_labels

SPLIT_DIRS = ("train", "valid", "val", "test")
_RF_SUFFIX = re.compile(r"\.rf\.[0-9a-fA-F]+$")
_EXT_TAG = re.compile(r"_(jpe?g|png|bmp|webp)$", re.IGNORECASE)
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_VALID_NAME = re.compile(r"[A-Za-z0-9._-]+")


def group_key(stem: str) -> str:
    """'img12_jpg.rf.3f9a' -> 'img12'. Augmented copies of one photo share this key."""
    return _EXT_TAG.sub("", _RF_SUFFIX.sub("", stem))


def read_names(src: Path) -> list[str]:
    data = yaml.safe_load((src / "data.yaml").read_text(encoding="utf-8"))
    names = data["names"]
    if isinstance(names, dict):
        return [str(names[k]) for k in sorted(names, key=int)]
    return [str(n) for n in names]


def load_dataset_entry(mapping_path: Path, dataset_name: str) -> dict:
    data = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    entry = (data.get("datasets") or {}).get(dataset_name)
    if entry is None:
        raise MappingError(f"{mapping_path}: no entry for dataset {dataset_name!r}. Add one (see the file header).")
    return entry


def convert(
    src: Path,
    out_root: Path,
    dataset_name: str,
    entry: dict,
    class_names: list[str],
    max_side: int | None = 1280,
    mode: str = "hardlink",
) -> dict:
    if not _VALID_NAME.fullmatch(dataset_name) or "__" in dataset_name:
        raise ValueError("dataset name may use letters, digits, '.', '_', '-' (no double underscore)")
    src_names = read_names(src)
    label_map = resolve_mapping(entry.get("labels") or {}, class_names, f"obstacle_mapping[{dataset_name}]")
    unmapped = [n for n in src_names if n not in label_map]
    if unmapped:
        raise MappingError(f"{dataset_name}: source classes not in obstacle_mapping.yaml: {unmapped}")
    src_to_target = {i: label_map[n] for i, n in enumerate(src_names)}

    out = out_root / dataset_name
    manifest: list[dict] = []
    boxes_per_class: Counter[str] = Counter()
    dropped: Counter[str] = Counter()
    n_background = n_bad = 0
    for split in SPLIT_DIRS:
        img_dir = src / split / "images"
        if not img_dir.is_dir():
            continue
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            boxes: list[YoloBox] = []
            for cls, coords in read_yolo_labels(src / split / "labels" / f"{img.stem}.txt"):
                if cls not in src_to_target:
                    raise MappingError(f"{img}: class id {cls} not in data.yaml names ({len(src_names)} classes)")
                target = src_to_target[cls]
                if target is None:
                    dropped[src_names[cls]] += 1
                    continue
                box = coords_to_box(target, coords)
                if box is None:
                    n_bad += 1
                    continue
                boxes.append(box)
                boxes_per_class[class_names[target]] += 1
            n_background += not boxes
            name = f"{dataset_name}__{split}__{_SAFE.sub('_', img.stem)}"
            place_image(img, out / "images" / (name + img.suffix.lower()), max_side, mode)
            write_labels(out / "labels" / f"{name}.txt", boxes)
            manifest.append({"name": name, "group": f"{dataset_name}/{group_key(img.stem)}",
                             "source_split": split})

    if not manifest:
        raise FileNotFoundError(f"no images found under {src}/{{{','.join(SPLIT_DIRS)}}}/images")
    n_groups = len({m["group"] for m in manifest})
    report: dict[str, Any] = {
        "dataset": dataset_name,
        "source": entry.get("source"),
        "license": entry.get("license"),
        "images": len(manifest),
        "groups": n_groups,
        "background_images": n_background,
        "boxes_per_class": dict(sorted(boxes_per_class.items())),
        "dropped_boxes_by_label": dict(sorted(dropped.items())),
        "invalid_boxes_removed": n_bad,
    }
    (out / "manifest.json").write_text(json.dumps({"report": report, "images": manifest}, indent=2),
                                       encoding="utf-8")
    print(json.dumps(report, indent=2))
    if n_groups < len(manifest):
        print(f"note: {len(manifest)} images come from {n_groups} original photos "
              "(augmented copies); merge will keep each photo's copies in one split.")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", type=Path, required=True, help="unzipped Roboflow YOLO export")
    p.add_argument("--dataset-name", required=True, help="key in obstacle_mapping.yaml")
    p.add_argument("--out", type=Path, default=Path("data/processed/obstacles"))
    p.add_argument("--classes", type=Path, default=DEFAULT_CLASSES)
    p.add_argument("--mapping", type=Path, default=Path("ml/configs/obstacle_mapping.yaml"))
    p.add_argument("--max-side", type=int, default=1280)
    p.add_argument("--mode", choices=["hardlink", "copy", "symlink"], default="hardlink")
    a = p.parse_args(argv)
    names = load_classes(a.classes)
    try:
        entry = load_dataset_entry(a.mapping, a.dataset_name)
        convert(a.src, a.out, a.dataset_name, entry, names, a.max_side or None, a.mode)
    except (MappingError, FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
