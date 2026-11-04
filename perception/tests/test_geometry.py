import math

import pytest

from dashcam_perception.config import CameraConfig
from dashcam_perception.geometry import (
    estimate_distance,
    focal_length_px,
    ground_plane_distance,
    lane_overlap,
    width_prior_distance,
)
from dashcam_perception.types import Box

CAM = CameraConfig(horizontal_fov_deg=90.0, mount_height_m=1.5, horizon_y_frac=0.5)
W, H = 1000, 600
LANE = ((0.2, 1.0), (0.45, 0.5), (0.55, 0.5), (0.8, 1.0))


def test_focal_length_from_fov():
    assert focal_length_px(1000, 90.0) == pytest.approx(500.0)


def test_ground_plane_matches_pinhole_projection():
    # Point 10 m ahead projects to horizon + f*H/Z = 300 + 500*1.5/10 = 375
    assert ground_plane_distance(Box(400, 340, 600, 375), W, H, CAM) == pytest.approx(10.0)


def test_ground_plane_undefined_at_or_above_horizon():
    assert ground_plane_distance(Box(400, 200, 600, 301), W, H, CAM) is None


def test_width_prior():
    # car 1.8 m wide, 90 px wide -> 500*1.8/90 = 10 m
    assert width_prior_distance(Box(0, 0, 90, 50), "car", W, CAM) == pytest.approx(10.0)
    assert width_prior_distance(Box(0, 0, 90, 50), "pothole", W, CAM) is None


def test_estimate_takes_the_closer_estimate():
    box = Box(400, 340, 490, 375)  # ground plane 10 m, width prior 10 m
    assert estimate_distance(box, "car", W, H, CAM) == pytest.approx(10.0)
    wide = Box(400, 340, 580, 375)  # width prior says 5 m
    assert estimate_distance(wide, "car", W, H, CAM) == pytest.approx(5.0)


def test_estimate_none_when_no_method_applies():
    assert estimate_distance(Box(400, 100, 600, 250), "pothole", W, H, CAM) is None


@pytest.mark.parametrize(
    ("box", "expected"),
    [
        (Box(450, 500, 550, 599), 1.0),  # centred, fully in lane
        (Box(0, 500, 100, 599), 0.0),  # far left, outside
        (Box(100, 500, 300, 599), None),  # straddling the left edge: partial
        (Box(450, 100, 550, 200), 0.0),  # above the lane's top edge
    ],
)
def test_lane_overlap(box, expected):
    got = lane_overlap(box, LANE, W, H)
    if expected is None:
        assert 0.0 < got < 1.0
    else:
        assert got == pytest.approx(expected)


def test_lane_overlap_uses_bottom_edge_not_box():
    # Tall truck in the next lane: its top overlaps the lane area, its wheels don't
    tall = Box(820, 50, 980, 599)
    assert lane_overlap(tall, LANE, W, H) == 0.0
    assert not math.isnan(lane_overlap(Box(500, 0, 500, 599), LANE, W, H))
