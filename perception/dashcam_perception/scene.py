"""Turn tracked boxes into ObjectStates (lane, distance, TTC). Pure Python, no torch."""

from __future__ import annotations

from dashcam_perception.config import PipelineConfig
from dashcam_perception.geometry import estimate_distance, lane_overlap
from dashcam_perception.ttc import TrackSizeHistory
from dashcam_perception.types import Box, FrameInfo, ObjectState, TrackedObject


class SceneEstimator:
    def __init__(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg
        self.sizes = TrackSizeHistory(cfg.ttc.window_s, cfg.ttc.min_samples, cfg.ttc.max_gap_s)

    def step(self, frame: FrameInfo, objects: list[TrackedObject]) -> list[ObjectState]:
        out: list[ObjectState] = []
        for obj in objects:
            overlap = lane_overlap(obj.box, self.cfg.ego_lane.polygon, frame.width, frame.height)
            ttc_s, rate = self.sizes.update(obj.track_id, frame.time_s, obj.box.width, obj.box.height)
            out.append(
                ObjectState(
                    obj=obj,
                    in_ego_lane=overlap >= self.cfg.ego_lane.min_overlap and overlap > 0,
                    lane_overlap=overlap,
                    distance_m=estimate_distance(obj.box, obj.class_name, frame.width, frame.height, self.cfg.camera),
                    ttc_s=ttc_s,
                    closing=rate is not None and rate > 0,
                )
            )
        self.sizes.prune(frame.time_s)
        return out


def suppress_riders(objects: list[TrackedObject], min_overlap: float) -> list[TrackedObject]:
    """Drop 'pedestrian' boxes that are mostly inside a two-wheeler box (the rider)."""
    bikes = [o.box for o in objects if o.class_name == "two_wheeler"]
    if not bikes:
        return objects
    kept: list[TrackedObject] = []
    for o in objects:
        if o.class_name == "pedestrian" and o.box.area > 0:
            # Riders sit above the bike, so extend the bike box upward by its own height.
            if any(
                o.box.intersection_area(Box(b.x1, b.y1 - b.height, b.x2, b.y2)) / o.box.area >= min_overlap
                for b in bikes
            ):
                continue
        kept.append(o)
    return kept
