"""Alert rules: per-frame conditions -> confirmed, de-duplicated alert episodes.

Three layers, each testable on its own:
1. `evaluate_*`: pure functions. Given one object's state in one frame, return the
   severity this frame (None / "warning" / "critical").
2. Confirmation: a condition must hold in `confirm_hits` of the last `confirm_window`
   frames of that track. One noisy frame can't raise an alert, but a real risk is
   confirmed within ~2 frames (~70 ms at 30 fps).
3. Episodes: while a track keeps triggering the same alert type, that's ONE event whose
   severity is the worst seen. It closes after `episode_gap_s` without the condition.
   So a car slowly closing in for 3 s produces one event, not 90.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from dashcam_perception.config import AlertsConfig, ForwardCollisionConfig, ObstacleConfig
from dashcam_perception.types import Box, FrameInfo, ObjectState


class AlertType(StrEnum):
    FORWARD_COLLISION = "forward_collision"
    OBSTACLE_IN_LANE = "obstacle_in_lane"


class Severity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


_RANK = {None: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}


def worse(a: Severity | None, b: Severity | None) -> Severity | None:
    return a if _RANK[a] >= _RANK[b] else b


def evaluate_forward_collision(s: ObjectState, cfg: ForwardCollisionConfig) -> Severity | None:
    if not cfg.enabled or s.obj.class_name not in cfg.classes or not s.in_ego_lane:
        return None
    sev: Severity | None = None
    if s.ttc_s is not None and s.ttc_s <= cfg.ttc_critical_s:
        return Severity.CRITICAL
    if s.closing and s.distance_m is not None and s.distance_m <= cfg.critical_distance_m:
        return Severity.CRITICAL
    if s.ttc_s is not None and s.ttc_s <= cfg.ttc_warning_s:
        sev = Severity.WARNING
    if (
        s.obj.class_name in cfg.vulnerable_classes
        and s.distance_m is not None
        and s.distance_m <= cfg.vulnerable_distance_m
    ):
        sev = worse(sev, Severity.WARNING)
    return sev


def evaluate_obstacle(s: ObjectState, cfg: ObstacleConfig) -> Severity | None:
    if not cfg.enabled or s.obj.class_name not in cfg.classes or not s.in_ego_lane or s.distance_m is None:
        return None
    if s.distance_m <= cfg.critical_distance_m:
        return Severity.CRITICAL
    if s.distance_m <= cfg.warning_distance_m:
        return Severity.WARNING
    return None


@dataclass
class AlertEvent:
    """One alert episode. Serialised into events.json by dashcam_perception.events."""

    event_id: int
    type: AlertType
    severity: Severity
    track_id: int
    class_name: str
    start_frame: int
    start_time_s: float
    end_time_s: float
    peak_time_s: float
    peak_box: Box
    min_ttc_s: float | None = None
    min_distance_m: float | None = None
    max_confidence: float = 0.0

    def update(self, frame: FrameInfo, s: ObjectState, sev: Severity) -> None:
        self.end_time_s = frame.time_s
        self.max_confidence = max(self.max_confidence, s.obj.confidence)
        if s.ttc_s is not None:
            self.min_ttc_s = s.ttc_s if self.min_ttc_s is None else min(self.min_ttc_s, s.ttc_s)
        if s.distance_m is not None:
            self.min_distance_m = (
                s.distance_m if self.min_distance_m is None else min(self.min_distance_m, s.distance_m)
            )
        if _RANK[sev] > _RANK[self.severity]:
            self.severity = sev
            self.peak_time_s = frame.time_s
            self.peak_box = s.obj.box


@dataclass
class _TrackRuleState:
    hits: deque[bool]
    last_hit_time_s: float = float("-inf")
    episode: AlertEvent | None = None


@dataclass
class AlertEngine:
    cfg: AlertsConfig
    finished: list[AlertEvent] = field(default_factory=list)
    _state: dict[tuple[int, AlertType], _TrackRuleState] = field(default_factory=dict)
    _next_id: int = 1

    def step(self, frame: FrameInfo, states: list[ObjectState]) -> list[AlertEvent]:
        """Process one frame. Returns the episodes active in this frame (for drawing)."""
        active: list[AlertEvent] = []
        for s in states:
            for alert_type, sev in (
                (AlertType.FORWARD_COLLISION, evaluate_forward_collision(s, self.cfg.forward_collision)),
                (AlertType.OBSTACLE_IN_LANE, evaluate_obstacle(s, self.cfg.obstacle_in_lane)),
            ):
                ev = self._observe(frame, s, alert_type, sev)
                if ev is not None:
                    active.append(ev)
        self._close_stale(frame.time_s)
        return active

    def _observe(
        self, frame: FrameInfo, s: ObjectState, alert_type: AlertType, sev: Severity | None
    ) -> AlertEvent | None:
        key = (s.obj.track_id, alert_type)
        st = self._state.get(key)
        if st is None:
            if sev is None:
                return None  # nothing to remember for a track that has never triggered
            st = self._state[key] = _TrackRuleState(hits=deque(maxlen=self.cfg.confirm_window))
        st.hits.append(sev is not None)
        if sev is None:
            return st.episode
        st.last_hit_time_s = frame.time_s
        if st.episode is not None:
            st.episode.update(frame, s, sev)
            return st.episode
        if sum(st.hits) >= self.cfg.confirm_hits:
            st.episode = AlertEvent(
                event_id=self._next_id,
                type=alert_type,
                severity=sev,
                track_id=s.obj.track_id,
                class_name=s.obj.class_name,
                start_frame=frame.index,
                start_time_s=frame.time_s,
                end_time_s=frame.time_s,
                peak_time_s=frame.time_s,
                peak_box=s.obj.box,
            )
            self._next_id += 1
            st.episode.update(frame, s, sev)
            return st.episode
        return None

    def _close_stale(self, now_s: float) -> None:
        for key in list(self._state):
            st = self._state[key]
            if now_s - st.last_hit_time_s > self.cfg.episode_gap_s:
                if st.episode is not None:
                    self.finished.append(st.episode)
                del self._state[key]

    def finish(self) -> list[AlertEvent]:
        """Close any open episodes (end of video) and return all events in start order."""
        for st in self._state.values():
            if st.episode is not None:
                self.finished.append(st.episode)
        self._state.clear()
        return sorted(self.finished, key=lambda e: (e.start_time_s, e.event_id))
