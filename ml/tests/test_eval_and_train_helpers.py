from __future__ import annotations

from pathlib import Path

from conftest import REPO
from dashcam_ml.classes import load_flat_mapping
from dashcam_ml.evaluate import coco_class_remap, label_path
from dashcam_ml.train import apply_overrides

COCO_NAMES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck", 9: "traffic light",
              14: "bird", 19: "cow"}


def test_coco_remap(class_names: list[str]) -> None:
    remap = coco_class_remap(COCO_NAMES, load_flat_mapping(REPO / "ml/configs/coco_map.yaml", class_names))
    assert remap[0] == class_names.index("pedestrian")
    assert remap[1] == remap[3] == class_names.index("two_wheeler")
    assert remap[19] == class_names.index("animal")
    assert 9 not in remap  # traffic light has no target class
    assert class_names.index("auto_rickshaw") not in remap.values()


def test_label_path_uses_last_images_dir() -> None:
    p = Path("/data/images_backup/merged/images/val/idd__a.jpg")
    assert label_path(p) == Path("/data/images_backup/merged/labels/val/idd__a.txt")


def test_overrides() -> None:
    cfg = apply_overrides({"train": {"epochs": 100}}, ["train.epochs=5", "train.imgsz=960", "model=yolo26n.pt"])
    assert cfg == {"train": {"epochs": 5, "imgsz": 960}, "model": "yolo26n.pt"}
