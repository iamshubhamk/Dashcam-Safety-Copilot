"""Convert IDD Detection (Pascal VOC XML) to YOLO format with our 11-class mapping.

    python -m dashcam_ml.convert.idd --root data/raw/IDD_Detection --out data/processed/idd

Expected input (the official IDD Detection download):
    IDD_Detection/
      train.txt, val.txt        # one image id per line, e.g. frontFar/BLR-2018-..._frontFar/000431
      Annotations/<id>.xml      # Pascal VOC boxes
      JPEGImages/<id>.jpg

We keep IDD's own train/val split (its test split has no public labels). Two passes:
first read every XML and check every label is in idd_mapping.yaml (so a surprise label
stops the run before anything is written), then write images and labels.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from dashcam_ml.classes import DEFAULT_CLASSES, MappingError, load_classes, load_flat_mapping
from dashcam_ml.yolo_io import YoloBox, find_image, image_size, place_image, voc_to_yolo, write_labels

SOURCE_PREFIX = "idd"
SPLITS = ("train", "val")


@dataclass
class VocObject:
    label: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float


@dataclass
class VocImage:
    image_id: str
    width: int
    height: int
    objects: list[VocObject] = field(default_factory=list)


def parse_voc(xml_path: Path, image_id: str) -> VocImage:
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    w = int(float(size.findtext("width", "0"))) if size is not None else 0
    h = int(float(size.findtext("height", "0"))) if size is not None else 0
    objs = []
    for obj in root.iter("object"):
        bb = obj.find("bndbox")
        name = (obj.findtext("name") or "").strip()
        if bb is None or not name:
            continue
        objs.append(
            VocObject(
                name,
                float(bb.findtext("xmin", "0")),
                float(bb.findtext("ymin", "0")),
                float(bb.findtext("xmax", "0")),
                float(bb.findtext("ymax", "0")),
            )
        )
    return VocImage(image_id, w, h, objs)


def output_name(image_id: str) -> str:
    """Flatten 'frontFar/SEQ/000431' to 'idd__frontFar__SEQ__000431' (unique, one folder)."""
    return f"{SOURCE_PREFIX}__" + image_id.strip("/").replace("/", "__").replace("\\", "__")


def read_split_ids(root: Path, split: str) -> list[str]:
    f = root / f"{split}.txt"
    if not f.exists():
        raise FileNotFoundError(f"{f} not found. Is --root the folder containing train.txt/val.txt?")
    return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _write_one(args: tuple[str, str, str, list[YoloBox], str, int | None, str]) -> None:
    img_src, img_dst_dir, name, boxes, lbl_dir, max_side, mode = args
    src = Path(img_src)
    place_image(src, Path(img_dst_dir) / (name + src.suffix.lower()), max_side, mode)
    write_labels(Path(lbl_dir) / f"{name}.txt", boxes)


def convert(
    root: Path,
    out: Path,
    mapping: dict[str, int | None],
    class_names: list[str],
    max_side: int | None = 1280,
    mode: str = "hardlink",
    limit: int | None = None,
    workers: int = 4,
) -> dict:
    report: dict = {"source": "IDD Detection", "root": str(root), "max_side": max_side, "splits": {}}
    raw_labels: Counter[str] = Counter()
    parsed: dict[str, list[tuple[VocImage, Path]]] = {}
    missing: Counter[str] = Counter()

    # Pass 1: parse + validate labels.
    for split in SPLITS:
        ids = read_split_ids(root, split)[:limit] if limit else read_split_ids(root, split)
        items = []
        for image_id in ids:
            xml = root / "Annotations" / f"{image_id}.xml"
            img = find_image(root / "JPEGImages" / image_id)
            if not xml.exists() or img is None:
                missing[f"{split}:{'xml' if not xml.exists() else 'image'}"] += 1
                continue
            voc = parse_voc(xml, image_id)
            raw_labels.update(o.label for o in voc.objects)
            items.append((voc, img))
        parsed[split] = items

    unknown = sorted(set(raw_labels) - set(mapping))
    print("IDD labels found (raw box counts):")
    for label, n in raw_labels.most_common():
        target = mapping.get(label, "<UNMAPPED>")
        target_name = class_names[target] if isinstance(target, int) else (target or "(dropped)")
        print(f"  {label:<20} {n:>8}  -> {target_name}")
    if unknown:
        raise MappingError(
            f"labels not in idd_mapping.yaml: {unknown}. Add each one (target class or null) and rerun."
        )

    # Pass 2: write.
    for split, items in parsed.items():
        img_dir, lbl_dir = out / "images" / split, out / "labels" / split
        boxes_per_class: Counter[str] = Counter()
        dropped: Counter[str] = Counter()
        n_clipped = n_degenerate = n_background = 0
        jobs = []
        for voc, img in items:
            w, h = voc.width, voc.height
            if w <= 0 or h <= 0:  # some VOC files omit size; read it from the image
                w, h = image_size(img)
            boxes: list[YoloBox] = []
            for o in voc.objects:
                cls = mapping[o.label]
                if cls is None:
                    dropped[o.label] += 1
                    continue
                box, clipped = voc_to_yolo(cls, o.xmin, o.ymin, o.xmax, o.ymax, w, h)
                n_clipped += clipped
                if box is None:
                    n_degenerate += 1
                    continue
                boxes.append(box)
                boxes_per_class[class_names[cls]] += 1
            n_background += not boxes
            jobs.append((str(img), str(img_dir), output_name(voc.image_id), boxes, str(lbl_dir), max_side, mode))

        if workers > 1:
            with ProcessPoolExecutor(workers) as ex:
                list(ex.map(_write_one, jobs, chunksize=64))
        else:
            for j in jobs:
                _write_one(j)

        report["splits"][split] = {
            "images": len(items),
            "background_images": n_background,
            "boxes_per_class": dict(sorted(boxes_per_class.items())),
            "dropped_boxes_by_label": dict(sorted(dropped.items())),
            "clipped_boxes": n_clipped,
            "degenerate_boxes_removed": n_degenerate,
        }
        print(f"[{split}] {len(items)} images, {sum(boxes_per_class.values())} boxes, "
              f"{n_background} with no kept boxes, {n_degenerate} degenerate boxes removed")

    report["raw_label_counts"] = dict(raw_labels.most_common())
    report["missing"] = dict(missing)
    if missing:
        print(f"WARNING: skipped ids with missing files: {dict(missing)}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "conversion_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, required=True, help="IDD_Detection folder")
    p.add_argument("--out", type=Path, default=Path("data/processed/idd"))
    p.add_argument("--classes", type=Path, default=DEFAULT_CLASSES)
    p.add_argument("--mapping", type=Path, default=Path("ml/configs/idd_mapping.yaml"))
    p.add_argument("--max-side", type=int, default=1280,
                   help="shrink images whose longest side is larger (saves disk/upload); 0 = keep original")
    p.add_argument("--mode", choices=["hardlink", "copy", "symlink"], default="hardlink")
    p.add_argument("--limit", type=int, default=None, help="only the first N ids per split (quick trial)")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args(argv)
    names = load_classes(a.classes)
    try:
        convert(a.root, a.out, load_flat_mapping(a.mapping, names), names,
                a.max_side or None, a.mode, a.limit, a.workers)
    except (MappingError, FileNotFoundError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
