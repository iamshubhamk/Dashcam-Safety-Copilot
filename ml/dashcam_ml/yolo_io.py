"""Small helpers shared by the converters: box maths, label files, image placement.

YOLO label format, one line per box: `class_id x_center y_center width height`, with all
four coordinates normalised to 0..1 by the image width/height. Normalised coordinates are
why we can shrink images (to save disk/upload time) without touching the labels.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
MIN_BOX_PX = 2.0  # boxes thinner than this after clipping are annotation noise


@dataclass(frozen=True)
class YoloBox:
    cls: int
    xc: float
    yc: float
    w: float
    h: float

    def line(self) -> str:
        return f"{self.cls} {self.xc:.6f} {self.yc:.6f} {self.w:.6f} {self.h:.6f}"


def voc_to_yolo(
    cls: int, xmin: float, ymin: float, xmax: float, ymax: float, img_w: int, img_h: int
) -> tuple[YoloBox | None, bool]:
    """Convert a pixel-corner box to YOLO. Returns (box or None if degenerate, was_clipped)."""
    cx0, cy0 = max(0.0, min(xmin, xmax)), max(0.0, min(ymin, ymax))
    cx1, cy1 = min(float(img_w), max(xmin, xmax)), min(float(img_h), max(ymin, ymax))
    clipped = (cx0, cy0, cx1, cy1) != (min(xmin, xmax), min(ymin, ymax), max(xmin, xmax), max(ymin, ymax))
    bw, bh = cx1 - cx0, cy1 - cy0
    if bw < MIN_BOX_PX or bh < MIN_BOX_PX:
        return None, clipped
    return (
        YoloBox(cls, (cx0 + cx1) / 2 / img_w, (cy0 + cy1) / 2 / img_h, bw / img_w, bh / img_h),
        clipped,
    )


def read_yolo_labels(path: Path) -> list[tuple[int, list[float]]]:
    """Read a YOLO label file. Rows may be boxes (4 numbers) or polygons (2k numbers)."""
    rows: list[tuple[int, list[float]]] = []
    if not path.exists():
        return rows
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split()
        if not parts:
            continue
        try:
            rows.append((int(float(parts[0])), [float(p) for p in parts[1:]]))
        except ValueError as e:
            raise ValueError(f"{path}:{n}: bad label line {line!r}") from e
    return rows


def coords_to_box(cls: int, coords: list[float]) -> YoloBox | None:
    """Box row (xc yc w h) as-is; polygon row (x1 y1 x2 y2 ...) -> its bounding box."""
    if len(coords) == 4:
        xc, yc, w, h = coords
        x0, y0, x1, y1 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
    elif len(coords) >= 6 and len(coords) % 2 == 0:
        xs, ys = coords[0::2], coords[1::2]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    else:
        raise ValueError(f"label row has {len(coords)} coordinates; expected 4 or an even number >= 6")
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return YoloBox(cls, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)


def write_labels(path: Path, boxes: list[YoloBox]) -> None:
    """Write a label file. An empty file means "image with no objects" (a background image)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(b.line() + "\n" for b in boxes), encoding="utf-8")


def place_image(src: Path, dst: Path, max_side: int | None = None, mode: str = "hardlink") -> None:
    """Put an image at dst: shrunk if its longest side exceeds max_side, else linked/copied.

    mode: "hardlink" (no extra disk, works on Windows NTFS without admin; falls back to copy
    across drives), "copy", or "symlink" (needs Developer Mode/admin on Windows).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    if max_side:
        with Image.open(src) as im:
            if max(im.size) > max_side:
                im = im.convert("RGB")
                im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                im.save(dst.with_suffix(".jpg") if dst.suffix.lower() not in (".jpg", ".jpeg") else dst,
                        quality=92)
                return
    if mode == "symlink":
        dst.symlink_to(src.resolve())
    elif mode == "hardlink":
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    elif mode == "copy":
        shutil.copy2(src, dst)
    else:
        raise ValueError(f"unknown mode {mode!r}")


def find_image(stem_path: Path) -> Path | None:
    """Find an image given a path without suffix (IDD split files list ids, not filenames)."""
    for suf in IMAGE_SUFFIXES + tuple(s.upper() for s in IMAGE_SUFFIXES):
        p = stem_path.with_name(stem_path.name + suf)
        if p.exists():
            return p
    return None


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size
