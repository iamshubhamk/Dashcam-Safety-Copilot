"""Build and write events.json (schema v1, see schema.py)."""

from __future__ import annotations

from pathlib import Path

from dashcam_perception.alerts import AlertEvent
from dashcam_perception.config import PipelineConfig
from dashcam_perception.schema import (
    EVENT_TYPES,
    SEVERITIES,
    Checks,
    Event,
    EventsDocument,
    Hazard,
    Thresholds,
    TripSummary,
    Video,
)
from dashcam_perception.summary import TripAccumulator


def _r(v: float | None, nd: int) -> float | None:
    return None if v is None else round(v, nd)


def to_event(e: AlertEvent, clip: str | None, distance_confidence: str) -> Event:
    b = e.peak_box
    return Event(
        event_id=e.event_id,
        type=str(e.type),
        severity=str(e.severity),
        track_id=e.track_id,
        class_name=e.class_name,
        start_frame=e.start_frame,
        start_time_s=round(e.start_time_s, 3),
        end_time_s=round(e.end_time_s, 3),
        peak_time_s=round(e.peak_time_s, 3),
        min_ttc_s=_r(e.min_ttc_s, 2),
        min_distance_m=_r(e.min_distance_m, 1),
        distance_confidence=distance_confidence,
        max_confidence=round(e.max_confidence, 3),
        peak_box_xyxy=(round(b.x1, 1), round(b.y1, 1), round(b.x2, 1), round(b.y2, 1)),
        gps=None,  # no GPS source yet; the backend fills it from a GPX/CSV sidecar later
        clip=clip,
    )


def build_checks(cfg: PipelineConfig, detector_classes: set[str]) -> Checks:
    """'ran' only when the rule was on AND the model can see what it needs.
    The stock COCO model has no pothole/barricade/... classes, so obstacle_in_lane is
    'absent' with it even though the rule is enabled."""
    fc = cfg.alerts.forward_collision
    ob = cfg.alerts.obstacle_in_lane
    return Checks(
        forward_collision="ran" if fc.enabled and fc.classes & detector_classes else "absent",
        obstacle_in_lane="ran" if ob.enabled and ob.classes & detector_classes else "absent",
        tailgating="skipped_no_ego_speed",
        harsh_braking="skipped_no_ego_speed",
        gps="skipped_no_gps",
    )


def build_document(
    cfg: PipelineConfig,
    *,
    classes_version: int,
    class_names: list[str],
    detector_classes: set[str],
    video: Video,
    events: list[AlertEvent],
    trip: TripAccumulator,
    clips: dict[int, str] | None = None,
) -> EventsDocument:
    clips = clips or {}
    distance_confidence = "ok" if cfg.camera.calibrated else "low"
    counts = {t: dict.fromkeys(SEVERITIES, 0) for t in EVENT_TYPES}
    for e in events:
        counts[str(e.type)][str(e.severity)] += 1
    fc = cfg.alerts.forward_collision
    return EventsDocument(
        classes_version=classes_version,
        video=video,
        thresholds=Thresholds(ttc_warning_s=fc.ttc_warning_s, ttc_critical_s=fc.ttc_critical_s),
        events=[to_event(e, clips.get(e.event_id), distance_confidence) for e in events],
        hazards=[
            Hazard(
                class_=h.class_name,
                track_id=tid,
                first_seen_s=round(h.first_seen_s, 3),
                last_seen_s=round(h.last_seen_s, 3),
                gps=None,
            )
            for tid, h in trip.hazards()
        ],
        trip_summary=TripSummary(
            ttc_below_warning_s=round(trip.ttc_below_warning_s, 3),
            ttc_below_critical_s=round(trip.ttc_below_critical_s, 3),
            min_ttc_s=_r(trip.min_ttc_s, 2),
            event_counts=counts,
            checks=build_checks(cfg, detector_classes),
        ),
        objects_seen=trip.objects_seen(class_names),
    )


def write_document(path: Path, doc: EventsDocument) -> None:
    path.write_text(doc.to_json(), encoding="utf-8")
