from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from dashcam_perception.config import PipelineConfig, load_classes, parse_config

REPO = Path(__file__).resolve().parents[2]
DEFAULT_YAML = REPO / "perception" / "configs" / "default.yaml"
CLASSES = load_classes(REPO / "configs" / "classes.yaml")


@pytest.fixture
def raw_config() -> dict:
    return copy.deepcopy(yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8")))


@pytest.fixture
def cfg(raw_config: dict) -> PipelineConfig:
    return parse_config(raw_config, CLASSES)
