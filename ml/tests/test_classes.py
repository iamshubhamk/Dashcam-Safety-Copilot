from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import REPO
from dashcam_ml.classes import MappingError, load_classes, load_flat_mapping, resolve_mapping


def test_shared_classes_file(class_names: list[str]) -> None:
    assert len(class_names) == 11
    assert class_names[0] == "car" and class_names[4] == "auto_rickshaw" and class_names[10] == "debris"


def test_class_ids_must_be_contiguous(tmp_path: Path) -> None:
    f = tmp_path / "c.yaml"
    f.write_text(yaml.safe_dump({"classes": {0: "a", 2: "b"}}))
    with pytest.raises(MappingError):
        load_classes(f)


def test_repo_mapping_files_only_use_known_classes(class_names: list[str]) -> None:
    idd = load_flat_mapping(REPO / "ml/configs/idd_mapping.yaml", class_names)
    assert idd["autorickshaw"] == class_names.index("auto_rickshaw")
    assert idd["rider"] is None and idd["vehicle fallback"] is None
    coco = load_flat_mapping(REPO / "ml/configs/coco_map.yaml", class_names)
    assert coco["motorcycle"] == coco["bicycle"] == class_names.index("two_wheeler")


def test_typo_in_target_is_rejected(class_names: list[str]) -> None:
    with pytest.raises(MappingError, match="two-wheeler"):
        resolve_mapping({"motorcycle": "two-wheeler"}, class_names, "test")


def test_repo_obstacle_mapping_is_valid(class_names: list[str]) -> None:
    datasets = yaml.safe_load((REPO / "ml/configs/obstacle_mapping.yaml").read_text())["datasets"]
    for name, entry in datasets.items():
        assert entry.get("license"), f"{name}: licence must be recorded"
        resolve_mapping(entry["labels"], class_names, name)
