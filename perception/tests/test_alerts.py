from dataclasses import replace

from dashcam_perception.alerts import (
    AlertEngine,
    AlertType,
    Severity,
    evaluate_forward_collision,
    evaluate_obstacle,
)
from dashcam_perception.types import Box, FrameInfo, ObjectState, TrackedObject


def state(cls="car", tid=1, in_lane=True, dist=None, ttc=None, closing=False, conf=0.9) -> ObjectState:
    return ObjectState(
        obj=TrackedObject(tid, cls, conf, Box(0, 0, 10, 10)),
        in_ego_lane=in_lane,
        lane_overlap=1.0 if in_lane else 0.0,
        distance_m=dist,
        ttc_s=ttc,
        closing=closing,
    )


def frame(i: int, fps: float = 30.0) -> FrameInfo:
    return FrameInfo(i, i / fps, 1280, 720)


# --- per-frame rules -------------------------------------------------------


def test_forward_collision_levels(cfg):
    fc = cfg.alerts.forward_collision
    assert evaluate_forward_collision(state(ttc=1.5), fc) == Severity.CRITICAL
    assert evaluate_forward_collision(state(ttc=3.0), fc) == Severity.WARNING
    assert evaluate_forward_collision(state(ttc=8.0), fc) is None
    assert evaluate_forward_collision(state(), fc) is None


def test_forward_collision_ignores_other_lanes_and_classes(cfg):
    fc = cfg.alerts.forward_collision
    assert evaluate_forward_collision(state(ttc=1.0, in_lane=False), fc) is None
    assert evaluate_forward_collision(state(cls="pothole", ttc=1.0), fc) is None


def test_close_and_closing_is_critical_without_ttc(cfg):
    fc = cfg.alerts.forward_collision
    assert evaluate_forward_collision(state(dist=3.0, closing=True), fc) == Severity.CRITICAL
    # Same distance but not closing (stopped in traffic): no alert for a car
    assert evaluate_forward_collision(state(dist=3.0, closing=False), fc) is None


def test_pedestrian_in_lane_nearby_warns_even_when_static(cfg):
    fc = cfg.alerts.forward_collision
    assert evaluate_forward_collision(state(cls="pedestrian", dist=10.0), fc) == Severity.WARNING
    assert evaluate_forward_collision(state(cls="animal", dist=40.0), fc) is None
    assert evaluate_forward_collision(state(cls="car", dist=10.0), fc) is None


def test_obstacle_levels(cfg):
    ob = cfg.alerts.obstacle_in_lane
    assert evaluate_obstacle(state(cls="pothole", dist=8.0), ob) == Severity.CRITICAL
    assert evaluate_obstacle(state(cls="barricade", dist=20.0), ob) == Severity.WARNING
    assert evaluate_obstacle(state(cls="debris", dist=50.0), ob) is None
    assert evaluate_obstacle(state(cls="pothole", dist=None), ob) is None
    assert evaluate_obstacle(state(cls="pothole", dist=8.0, in_lane=False), ob) is None


def test_disabled_rules_never_fire(cfg):
    fc = replace(cfg.alerts.forward_collision, enabled=False)
    assert evaluate_forward_collision(state(ttc=0.5), fc) is None


# --- engine: confirmation, episodes ------------------------------------------


def test_single_noisy_frame_does_not_alert(cfg):
    eng = AlertEngine(cfg.alerts)
    eng.step(frame(0), [state(ttc=1.0)])
    for i in range(1, 60):
        eng.step(frame(i), [state(ttc=None)])
    assert eng.finish() == []


def test_confirmed_within_two_frames(cfg):
    eng = AlertEngine(cfg.alerts)
    assert eng.step(frame(0), [state(ttc=3.0)]) == []
    active = eng.step(frame(1), [state(ttc=3.0)])
    assert len(active) == 1 and active[0].type == AlertType.FORWARD_COLLISION


def test_one_event_per_episode_with_peak_severity(cfg):
    eng = AlertEngine(cfg.alerts)
    ttcs = [3.5, 3.2, 2.8, 2.4, 1.9, 1.6, 1.4]
    for i, t in enumerate(ttcs):
        eng.step(frame(i), [state(ttc=t, dist=20 - i)])
    events = eng.finish()
    assert len(events) == 1
    e = events[0]
    assert e.severity == Severity.CRITICAL
    assert e.min_ttc_s == 1.4
    assert e.start_frame == 1
    assert e.min_distance_m == 20 - 6


def test_episode_survives_short_dropout_but_splits_after_gap(cfg):
    eng = AlertEngine(cfg.alerts)  # episode_gap_s = 1.0
    i = 0
    for _ in range(5):
        eng.step(frame(i), [state(ttc=3.0)])
        i += 1
    for _ in range(15):  # 0.5 s without the condition: same episode
        eng.step(frame(i), [state(ttc=None)])
        i += 1
    for _ in range(5):
        eng.step(frame(i), [state(ttc=3.0)])
        i += 1
    for _ in range(45):  # 1.5 s gap: episode closes
        eng.step(frame(i), [])
        i += 1
    for _ in range(5):
        eng.step(frame(i), [state(ttc=3.0)])
        i += 1
    events = eng.finish()
    assert len(events) == 2
    assert [e.event_id for e in events] == [1, 2]


def test_separate_tracks_get_separate_events(cfg):
    eng = AlertEngine(cfg.alerts)
    for i in range(3):
        eng.step(frame(i), [state(tid=1, ttc=3.0), state(tid=2, cls="pedestrian", dist=8.0)])
    events = eng.finish()
    assert {(e.track_id, e.type) for e in events} == {
        (1, AlertType.FORWARD_COLLISION),
        (2, AlertType.FORWARD_COLLISION),
    }
