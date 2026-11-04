from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import make_image
from dashcam_ml.classes import MappingError
from dashcam_ml.convert import roboflow


def build_export(src: Path, names, files: dict[str, dict[str, str]]) -> None:
    src.mkdir(parents=True)
    (src / "data.yaml").write_text(yaml.safe_dump({"names": names}))
    for split, entries in files.items():
        for stem, label in entries.items():
            make_image(src / split / "images" / f"{stem}.jpg")
            lp = src / split / "labels" / f"{stem}.txt"
            lp.parent.mkdir(parents=True, exist_ok=True)
            lp.write_text(label)


@pytest.mark.parametrize("stem,key", [
    ("img12_jpg.rf.3f9a0b", "img12"),
    ("IMG_0001_JPG.rf.abcdef0123", "IMG_0001"),
    ("plain_photo", "plain_photo"),
])
def test_group_key(stem: str, key: str) -> None:
    assert roboflow.group_key(stem) == key


def test_remaps_drops_and_handles_polygons(tmp_path: Path, class_names: list[str]) -> None:
    src = tmp_path / "export"
    build_export(src, {0: "Pothole", 1: "manhole"}, {
        "train": {"p1_jpg.rf.aaa": "0 0.5 0.5 0.2 0.2\n1 0.1 0.1 0.1 0.1\n",
                  "p1_jpg.rf.bbb": "0 0.1 0.1 0.3 0.1 0.3 0.3 0.1 0.3\n"},  # polygon row
        "valid": {"p2_jpg.rf.ccc": ""},
    })
    entry = {"license": "CC BY 4.0", "labels": {"Pothole": "pothole", "manhole": None}}
    rep = roboflow.convert(src, tmp_path / "out", "pot_a", entry, class_names, max_side=None, mode="copy")
    pid = class_names.index("pothole")
    assert rep["images"] == 3 and rep["groups"] == 2
    assert rep["dropped_boxes_by_label"] == {"manhole": 1}
    poly = (tmp_path / "out/pot_a/labels/pot_a__train__p1_jpg.rf.bbb.txt").read_text().split()
    assert poly == [str(pid), "0.200000", "0.200000", "0.200000", "0.200000"]
    assert rep["background_images"] == 1


def test_unmapped_source_class_is_an_error(tmp_path: Path, class_names: list[str]) -> None:
    src = tmp_path / "export"
    build_export(src, ["pothole", "crack"], {"train": {"a": "0 0.5 0.5 0.1 0.1\n"}})
    with pytest.raises(MappingError, match="crack"):
        roboflow.convert(src, tmp_path / "out", "x", {"labels": {"pothole": "pothole"}}, class_names, None, "copy")
