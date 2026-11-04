"""Plain data types passed between pipeline stages (no torch/OpenCV here)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    """Axis-aligned box in pixels: (x1, y1) top-left, (x2, y2) bottom-right."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    def intersection_area(self, other: Box) -> float:
        w = min(self.x2, other.x2) - max(self.x1, other.x1)
        h = min(self.y2, other.y2) - max(self.y1, other.y1)
        return max(0.0, w) * max(0.0, h)


@dataclass(frozen=True)
class TrackedObject:
    """One tracked object in one frame, with class already mapped to our class names."""

    track_id: int
    class_name: str
    confidence: float
    box: Box


@dataclass(frozen=True)
class FrameInfo:
    index: int
    time_s: float
    width: int
    height: int


@dataclass(frozen=True)
class ObjectState:
    """Everything the alert rules need about one object in one frame."""

    obj: TrackedObject
    in_ego_lane: bool
    lane_overlap: float
    distance_m: float | None
    ttc_s: float | None
    closing: bool
