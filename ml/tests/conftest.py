from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def class_names() -> list[str]:
    from dashcam_ml.classes import load_classes

    return load_classes(REPO / "configs" / "classes.yaml")


def make_image(path: Path, size: tuple[int, int] = (200, 100), color: tuple[int, int, int] = (0, 0, 0)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path
