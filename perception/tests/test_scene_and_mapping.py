import json

import pytest
import yaml
from conftest import CLASSES, REPO

from dashcam_perception.alerts import AlertEngine
from dashcam_perception.config import ConfigError
from dashcam_perception.detector import build_label_map
from dashcam_perception.events import SCHEMA_VERSION, write_events
from dashcam_perception.geometry import focal_length_px
from dashcam_perception.scene import SceneEstimator, suppress_riders
from dashcam_perception.types import Box, FrameInfo, TrackedObject

COCO_MAP = yaml.safe_load((REPO / "ml" / "configs" / "coco_map.yaml").read_text(encoding="utf-8"))


def obj(tid, cls, box):
    return TrackedObject(tid, cls, 0.8, Box(*box))


def test_rider_on_bike_is_not_a_pedestrian():
    bike = obj(1, "two_wheeler", (100, 300, 160, 400))
    rider = obj(2, "pedestrian", (105, 220, 155, 360))
    walker = obj(3, "pedestrian", (400, 250, 440, 400))
    kept = suppress_riders([bike, rider, walker], 0.5)
    assert [o.track_id for o in kept] == [1, 3]


def test_label_map_coco_model():
    names = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 56: "chair"}
    m = build_label_map(names, CLASSES, COCO_MAP)
    assert m == {0: "pedestrian", 1: "two_wheeler", 2: "car", 3: "two_wheeler"}


def test_label_map_finetuned_model_is_identity():
    names = dict(enumerate(CLASSES))
    assert build_label_map(names, CLASSES, COCO_MAP) == names


def test_label_map_rejects_unrelated_model():
    with pytest.raises(ConfigError):
        build_label_map({0: "cat_face", 1: "dog_face"}, CLASSES, COCO_MAP)


def project_car(x_m: float, z_m: float, cfg, w: int = 1280, h: int = 720) -> tuple[float, float, float, float]:
    """Pinhole projection of a 1.8 m wide, 1.5 m tall car whose rear is z_m ahead and whose
    centre is x_m to the right, using the same camera model the pipeline assumes."""
    f = focal_length_px(w, cfg.camera.horizontal_fov_deg)
    cx, horizon = w / 2, cfg.camera.horizon_y_frac * h
    x1 = cx + f * (x_m - 0.9) / z_m
    x2 = cx + f * (x_m + 0.9) / z_m
    bottom = horizon + f * cfg.camera.mount_height_m / z_m
    top = horizon - f * (1.5 - cfg.camera.mount_height_m) / z_m
    return max(0.0, x1), max(0.0, top), min(w - 1.0, x2), min(h - 1.0, bottom)


def run_track(cfg, x_m: float, z0: float, speed: float, frames: int, cls: str = "car"):
    fps = 30.0
    scene, engine = SceneEstimator(cfg), AlertEngine(cfg.alerts)
    for i in range(frames):
        z = z0 - speed * i / fps
        box = project_car(x_m, z, cfg)
        if box[2] <= box[0]:
            break  # left the frame
        f = FrameInfo(i, i / fps, 1280, 720)
        engine.step(f, scene.step(f, [obj(5, cls, box)]))
    return engine.finish()


def test_approaching_car_end_to_end_without_model(cfg, tmp_path):
    """Car dead ahead, closing at 10 m/s (36 km/h) from 60 m, i.e. 6 s away. Pipeline maths
    alone must raise ONE forward-collision event, early, that escalates to critical."""
    events = run_track(cfg, x_m=0.0, z0=60.0, speed=10.0, frames=175)
    assert len(events) == 1
    e = events[0]
    assert e.severity == "critical"
    assert e.min_ttc_s is not None and e.min_ttc_s < cfg.alerts.forward_collision.ttc_critical_s
    # Warning must come no later than 0.5 s after the true TTC crosses the warning threshold
    true_ttc_at_start = (60.0 - 10.0 * e.start_time_s) / 10.0
    assert true_ttc_at_start >= cfg.alerts.forward_collision.ttc_warning_s - 0.5

    out = tmp_path / "events.json"
    write_events(out, events, {"path": "synthetic"}, {"weights": "none"}, {e.event_id: "clips/x.mp4"})
    doc = json.loads(out.read_text())
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["events"][0]["type"] == "forward_collision"
    assert doc["events"][0]["clip"] == "clips/x.mp4"
    assert doc["events"][0]["gps"] is None


def test_car_in_next_lane_never_alerts(cfg):
    # 3.5 m to the right = centre of the adjacent lane on an Indian road
    assert run_track(cfg, x_m=3.5, z0=25.0, speed=10.0, frames=66) == []


def test_car_ahead_at_constant_gap_never_alerts(cfg):
    assert run_track(cfg, x_m=0.0, z0=12.0, speed=0.0, frames=90) == []


def test_ego_lane_reaches_far_enough_for_highway_warnings(cfg):
    """Closing at 80 km/h (22 m/s) on a stopped car. The lane must reach far enough that the
    warning still comes with ~3 s to spare. It's ~3 s rather than 4 s because TTC is not
    computed for boxes under ttc.min_size_px (a deliberate noise trade-off; see ttc.py)."""
    events = run_track(cfg, x_m=0.0, z0=120.0, speed=22.0, frames=150)
    assert events, "no alert for a car closing at 80 km/h"
    true_ttc_at_start = (120.0 - 22.0 * events[0].start_time_s) / 22.0
    assert true_ttc_at_start >= 2.8
