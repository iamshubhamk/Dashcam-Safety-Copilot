from __future__ import annotations

from pathlib import Path

import pytest

from conftest import REPO, make_image
from dashcam_ml.classes import MappingError, load_flat_mapping
from dashcam_ml.convert import idd


def voc(objects: list[tuple[str, int, int, int, int]], size: tuple[int, int] | None = (200, 100)) -> str:
    size_xml = f"<size><width>{size[0]}</width><height>{size[1]}</height></size>" if size else ""
    objs = "".join(
        f"<object><name>{n}</name><bndbox><xmin>{a}</xmin><ymin>{b}</ymin><xmax>{c}</xmax><ymax>{d}</ymax>"
        "</bndbox></object>" for n, a, b, c, d in objects)
    return f"<annotation>{size_xml}{objs}</annotation>"


def build_idd(root: Path, items: dict[str, dict[str, str]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for split, entries in items.items():
        (root / f"{split}.txt").write_text("\n".join(entries) + "\n")
        for image_id, xml in entries.items():
            x = root / "Annotations" / f"{image_id}.xml"
            x.parent.mkdir(parents=True, exist_ok=True)
            x.write_text(xml)
            make_image(root / "JPEGImages" / f"{image_id}.jpg")


@pytest.fixture
def mapping(class_names: list[str]) -> dict[str, int | None]:
    return load_flat_mapping(REPO / "ml/configs/idd_mapping.yaml", class_names)


def test_converts_maps_drops_and_clips(tmp_path: Path, class_names: list[str], mapping: dict) -> None:
    root, out = tmp_path / "IDD", tmp_path / "out"
    build_idd(root, {
        "train": {
            "frontFar/seqA/000001": voc([("car", 0, 0, 100, 50), ("rider", 10, 10, 20, 20),
                                         ("autorickshaw", 150, 50, 250, 100)]),  # extends past right edge
            "frontNear/seqB/000002": voc([("traffic sign", 1, 1, 10, 10)]),      # only dropped labels
        },
        "val": {"frontFar/seqC/000003": voc([("motorcycle", 50, 50, 51, 60)], size=None)},  # degenerate, no size
    })
    report = idd.convert(root, out, mapping, class_names, max_side=None, mode="copy", workers=1)

    lbl = (out / "labels/train/idd__frontFar__seqA__000001.txt").read_text().splitlines()
    assert lbl[0] == "0 0.250000 0.250000 0.500000 0.500000"
    assert lbl[1] == f"{class_names.index('auto_rickshaw')} 0.875000 0.750000 0.250000 0.500000"  # clipped at x=200
    assert len(lbl) == 2  # rider dropped
    assert (out / "images/train/idd__frontFar__seqA__000001.jpg").exists()
    assert (out / "labels/train/idd__frontNear__seqB__000002.txt").read_text() == ""  # kept as background
    assert (out / "labels/val/idd__frontFar__seqC__000003.txt").read_text() == ""
    tr = report["splits"]["train"]
    assert tr["dropped_boxes_by_label"] == {"rider": 1, "traffic sign": 1}
    assert tr["clipped_boxes"] == 1 and tr["background_images"] == 1
    assert report["splits"]["val"]["degenerate_boxes_removed"] == 1


def test_unknown_label_stops_before_writing(tmp_path: Path, class_names: list[str], mapping: dict) -> None:
    root, out = tmp_path / "IDD", tmp_path / "out"
    build_idd(root, {"train": {"a/b/1": voc([("tempo", 0, 0, 50, 50)])}, "val": {"a/b/2": voc([])}})
    with pytest.raises(MappingError, match="tempo"):
        idd.convert(root, out, mapping, class_names, max_side=None, mode="copy", workers=1)
    assert not out.exists()


def test_missing_files_are_skipped_and_counted(tmp_path: Path, class_names: list[str], mapping: dict) -> None:
    root, out = tmp_path / "IDD", tmp_path / "out"
    build_idd(root, {"train": {"a/b/1": voc([("car", 0, 0, 50, 50)])}, "val": {"a/b/2": voc([])}})
    (root / "train.txt").write_text("a/b/1\na/b/missing\n")
    report = idd.convert(root, out, mapping, class_names, max_side=None, mode="copy", workers=1)
    assert report["missing"] == {"train:xml": 1}
    assert report["splits"]["train"]["images"] == 1


def test_resize_keeps_normalised_labels(tmp_path: Path, class_names: list[str], mapping: dict) -> None:
    root, out = tmp_path / "IDD", tmp_path / "out"
    build_idd(root, {"train": {"a/b/1": voc([("car", 0, 0, 100, 50)])}, "val": {"a/b/2": voc([])}})
    idd.convert(root, out, mapping, class_names, max_side=100, mode="copy", workers=1)
    from PIL import Image

    with Image.open(out / "images/train/idd__a__b__1.jpg") as im:
        assert im.size == (100, 50)
    assert (out / "labels/train/idd__a__b__1.txt").read_text().startswith("0 0.250000 0.250000 0.500000 0.500000")
