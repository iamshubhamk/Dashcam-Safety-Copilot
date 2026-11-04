"""Per-trip accumulators for the driving report: risky-following time, closest call,
objects seen and hazards. Pure Python; fed one frame at a time by run.py."""

from __future__ import annotations

from dataclasses import dataclass, field

from dashcam_perception.config import ForwardCollisionConfig
from dashcam_perception.schema import HAZARD_CLASSES
from dashcam_perception.types import FrameInfo, ObjectState


@dataclass
class _HazardSpan:
    class_name: str
    first_seen_s: float
    last_seen_s: float


@dataclass
class TripAccumulator:
    fc: ForwardCollisionConfig
    frame_dt_s: float
    ttc_below_warning_s: float = 0.0
    ttc_below_critical_s: float = 0.0
    min_ttc_s: float | None = None
    _tracks_by_class: dict[str, set[int]] = field(default_factory=dict)
    _hazards: dict[int, _HazardSpan] = field(default_factory=dict)

    def step(self, frame: FrameInfo, states: list[ObjectState], confirmed_tracks: set[int] | None = None) -> None:
        """`confirmed_tracks`: tracks with an active forward-collision episode this frame
        (from AlertEngine). Only those count towards risky time and the closest call, so a
        one-frame TTC spike that never became an alert can't show up in the report.
        None = count every in-lane object (used by unit tests of the arithmetic)."""
        # The frame counts once towards risky time even if several objects are risky,
        # so the totals are "seconds of the trip", never more than the trip's duration.
        lead_ttcs = [
            s.ttc_s
            for s in states
            if s.in_ego_lane
            and s.ttc_s is not None
            and s.obj.class_name in self.fc.classes
            and (confirmed_tracks is None or s.obj.track_id in confirmed_tracks)
        ]
        if lead_ttcs:
            worst = min(lead_ttcs)
            self.min_ttc_s = worst if self.min_ttc_s is None else min(self.min_ttc_s, worst)
            if worst <= self.fc.ttc_warning_s:
                self.ttc_below_warning_s += self.frame_dt_s
            if worst <= self.fc.ttc_critical_s:
                self.ttc_below_critical_s += self.frame_dt_s

        for s in states:
            o = s.obj
            self._tracks_by_class.setdefault(o.class_name, set()).add(o.track_id)
            if o.class_name in HAZARD_CLASSES:
                span = self._hazards.get(o.track_id)
                if span is None:
                    self._hazards[o.track_id] = _HazardSpan(o.class_name, frame.time_s, frame.time_s)
                else:
                    span.last_seen_s = frame.time_s

    def objects_seen(self, class_names: list[str]) -> dict[str, int]:
        return {name: len(self._tracks_by_class.get(name, ())) for name in class_names}

    def hazards(self) -> list[tuple[int, _HazardSpan]]:
        return sorted(self._hazards.items(), key=lambda kv: (kv[1].first_seen_s, kv[0]))
