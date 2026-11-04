import pytest

from dashcam_perception.summary import TripAccumulator
from dashcam_perception.types import Box, FrameInfo, ObjectState, TrackedObject


def st(tid, cls, ttc=None, in_lane=True):
    return ObjectState(
        TrackedObject(tid, cls, 0.9, Box(0, 0, 10, 10)), in_lane, 1.0 if in_lane else 0.0, 10.0, ttc, False
    )


def f(i):
    return FrameInfo(i, i / 10, 640, 480)


def test_risky_time_counts_each_frame_once(cfg):
    acc = TripAccumulator(cfg.alerts.forward_collision, frame_dt_s=0.1)
    # two risky cars in the same frame still count 0.1 s, not 0.2 s
    acc.step(f(0), [st(1, "car", ttc=3.0), st(2, "car", ttc=1.5)])
    acc.step(f(1), [st(1, "car", ttc=3.0)])
    acc.step(f(2), [st(1, "car", ttc=9.0)])
    assert acc.ttc_below_warning_s == pytest.approx(0.2)
    assert acc.ttc_below_critical_s == pytest.approx(0.1)
    assert acc.min_ttc_s == 1.5


def test_out_of_lane_and_non_road_users_ignored_for_risk(cfg):
    acc = TripAccumulator(cfg.alerts.forward_collision, frame_dt_s=0.1)
    acc.step(f(0), [st(1, "car", ttc=1.0, in_lane=False), st(2, "pothole", ttc=1.0)])
    assert acc.ttc_below_warning_s == 0 and acc.min_ttc_s is None


def test_objects_seen_counts_tracks_not_frames(cfg):
    acc = TripAccumulator(cfg.alerts.forward_collision, frame_dt_s=0.1)
    for i in range(5):
        acc.step(f(i), [st(1, "car"), st(2, "car"), st(3, "pedestrian")])
    seen = acc.objects_seen(["car", "pedestrian", "bus"])
    assert seen == {"car": 2, "pedestrian": 1, "bus": 0}


def test_hazards_one_per_track_with_span(cfg):
    acc = TripAccumulator(cfg.alerts.forward_collision, frame_dt_s=0.1)
    for i in range(3, 8):
        acc.step(f(i), [st(9, "pothole"), st(1, "car")])
    acc.step(f(10), [st(4, "barricade")])
    hz = acc.hazards()
    assert [(tid, h.class_name, h.first_seen_s, h.last_seen_s) for tid, h in hz] == [
        (9, "pothole", 0.3, 0.7),
        (4, "barricade", 1.0, 1.0),
    ]


def test_unconfirmed_spike_not_in_report(cfg):
    """A one-frame TTC spike that never became an alert must not set the closest call."""
    acc = TripAccumulator(cfg.alerts.forward_collision, frame_dt_s=0.1)
    acc.step(f(0), [st(1, "car", ttc=1.1)], confirmed_tracks=set())
    acc.step(f(1), [st(2, "car", ttc=3.0)], confirmed_tracks={2})
    assert acc.min_ttc_s == 3.0
    assert acc.ttc_below_critical_s == 0
    assert acc.ttc_below_warning_s == pytest.approx(0.1)
