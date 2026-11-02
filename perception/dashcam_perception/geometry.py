"""Ego-lane test and monocular distance estimates.

Distance from one camera has no true depth, so we use two classic approximations and
take the smaller (closer) one, because over-estimating distance is the dangerous error:

1. Ground plane: a level camera at height H sees a point on flat road that is Z metres
   ahead at image row y = horizon + f*H/Z, so Z = f*H / (y_bottom - y_horizon).
   Breaks on slopes, speed breakers, and when the box bottom is hidden or cut off.
2. Known width: a car is ~1.8 m wide, so Z = f*W_real / w_pixels.
   Breaks for unusual vehicles and side-on views (a cow side-on is much wider).

Both need the focal length f in pixels, derived from the camera's horizontal field of view.
With uncalibrated defaults expect errors of 20-40%; the numbers are labelled approximate.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from dashcam_perception.config import CameraConfig
from dashcam_perception.types import Box

# Typical real-world widths (metres) seen from behind/in front. Rough on purpose.
CLASS_WIDTH_M: dict[str, float] = {
    "car": 1.8,
    "bus": 2.5,
    "truck": 2.5,
    "two_wheeler": 0.8,
    "auto_rickshaw": 1.4,
    "pedestrian": 0.5,
    "animal": 0.8,
    "barricade": 1.5,
}

# Box bottom must be at least this many pixels below the horizon for the ground-plane
# formula; closer to the horizon a 1-pixel error means tens of metres.
_MIN_PIXELS_BELOW_HORIZON = 4.0


def focal_length_px(image_width: int, horizontal_fov_deg: float) -> float:
    return (image_width / 2.0) / math.tan(math.radians(horizontal_fov_deg) / 2.0)


def ground_plane_distance(box: Box, image_width: int, image_height: int, cam: CameraConfig) -> float | None:
    f = focal_length_px(image_width, cam.horizontal_fov_deg)
    dy = box.y2 - cam.horizon_y_frac * image_height
    if dy < _MIN_PIXELS_BELOW_HORIZON:
        return None
    return f * cam.mount_height_m / dy


def width_prior_distance(box: Box, class_name: str, image_width: int, cam: CameraConfig) -> float | None:
    real_w = CLASS_WIDTH_M.get(class_name)
    if real_w is None or box.width < 1.0:
        return None
    return focal_length_px(image_width, cam.horizontal_fov_deg) * real_w / box.width


def estimate_distance(
    box: Box, class_name: str, image_width: int, image_height: int, cam: CameraConfig
) -> float | None:
    """Conservative (smaller) of the available estimates, or None if neither applies."""
    candidates = [
        d
        for d in (
            ground_plane_distance(box, image_width, image_height, cam),
            width_prior_distance(box, class_name, image_width, cam),
        )
        if d is not None
    ]
    return min(candidates) if candidates else None


def _polygon_x_span_at(polygon: Sequence[tuple[float, float]], y: float) -> tuple[float, float] | None:
    """Horizontal extent [x_min, x_max] of a convex polygon at row y, or None if y is outside."""
    xs: list[float] = []
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if y1 == y2:
            if y == y1:
                xs.extend([x1, x2])
            continue
        lo, hi = min(y1, y2), max(y1, y2)
        if lo <= y <= hi:
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    if not xs:
        return None
    return min(xs), max(xs)


def lane_overlap(box: Box, polygon_frac: Sequence[tuple[float, float]], image_width: int, image_height: int) -> float:
    """Fraction of the box's bottom edge (where the object touches the road) inside the lane.

    Using the bottom edge rather than the whole box matters: a tall truck in the next lane
    can overlap the lane trapezoid visually while its wheels are clearly outside it.
    """
    polygon = [(x * image_width, y * image_height) for x, y in polygon_frac]
    y = min(box.y2, image_height - 1e-6)
    span = _polygon_x_span_at(polygon, y)
    if span is None or box.width <= 0:
        return 0.0
    inside = min(box.x2, span[1]) - max(box.x1, span[0])
    return max(0.0, inside) / box.width
