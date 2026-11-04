"""Turn a pipeline output folder (events.json, annotated.mp4, clips/) into database rows.

Used by the worker after a local run and by the Kaggle-zip import, so both paths produce
identical trips. Everything for a trip is replaced, never appended, so running it twice
(a retry, a re-import) can't duplicate events.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from dashcam_perception.schema import EventsDocument
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    Event,
    EventType,
    GpsPoint,
    Severity,
    Trip,
    TripReport,
    TripStatus,
)
from app.services import hazards
from app.services.gps import Fix, Track
from app.services.scoring import RiskConfig, ScoredEvent, score_trip
from app.storage import Storage

_CLIP = re.compile(r"^clips/event_\d{1,6}\.mp4$")


NO_GPS = {
    "type": "gps",
    "label": "Map positions",
    "status": "skipped_no_gps",
    "reason": "no GPS file was uploaded, so events and hazards aren't on the map and the score is per hour",
}


class BadResults(ValueError):
    """The results folder is not something we can ingest (bad events.json, missing files)."""


def load_document(out_dir: Path) -> EventsDocument:
    path = out_dir / "events.json"
    if not path.is_file():
        raise BadResults("events.json is missing")
    try:
        return EventsDocument.model_validate_json(path.read_bytes())
    except ValidationError as e:
        raise BadResults(
            f"events.json does not match schema 1.0: {e.error_count()} problem(s): {e.errors()[:3]}"
        ) from e


def _run_summary(out_dir: Path) -> dict:
    try:
        data = json.loads((out_dir / "run_summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # optional file: metadata only
    return data if isinstance(data, dict) else {}


def load_track(db: Session, trip_id: uuid.UUID) -> Track | None:
    rows = db.execute(
        select(GpsPoint.t_s, GpsPoint.lat, GpsPoint.lon).where(GpsPoint.trip_id == trip_id).order_by(GpsPoint.t_s)
    ).all()
    return Track([Fix(r.t_s, r.lat, r.lon) for r in rows]) if len(rows) >= 2 else None


def ingest_results(
    db: Session,
    storage: Storage,
    settings: Settings,
    risk: RiskConfig,
    trip: Trip,
    out_dir: Path,
) -> None:
    """Store files, replace the trip's events/sightings/report, mark it done. The caller commits."""
    doc = load_document(out_dir)
    prefix = f"trips/{trip.id}"

    # Files first: keys are deterministic, so a retry overwrites instead of leaving orphans.
    annotated = out_dir / "annotated.mp4"
    trip.annotated_key = None
    if annotated.is_file():
        trip.annotated_key = f"{prefix}/annotated.mp4"
        storage.put_file(trip.annotated_key, annotated)

    clip_keys: dict[int, str] = {}
    for ev in doc.events:
        if not ev.clip:
            continue
        if not _CLIP.fullmatch(ev.clip):
            raise BadResults(f"unexpected clip path {ev.clip!r}")
        src = out_dir / ev.clip
        if src.is_file():
            clip_keys[ev.event_id] = f"{prefix}/{ev.clip}"
            storage.put_file(clip_keys[ev.event_id], src)

    track = load_track(db, trip.id)

    db.execute(delete(Event).where(Event.trip_id == trip.id))
    db.execute(delete(TripReport).where(TripReport.trip_id == trip.id))
    hazards.clear_trip_sightings(db, trip.id)

    rows: list[Event] = []
    for ev in doc.events:
        pos = (ev.gps.lat, ev.gps.lon) if ev.gps else (track.position_at(ev.peak_time_s) if track else None)
        rows.append(
            Event(
                trip_id=trip.id,
                pipeline_event_id=ev.event_id,
                type=EventType(ev.type),
                severity=Severity(ev.severity),
                class_name=ev.class_name,
                track_id=ev.track_id,
                start_s=ev.start_time_s,
                end_s=max(ev.end_time_s, ev.start_time_s),
                peak_s=ev.peak_time_s,
                min_ttc_s=ev.min_ttc_s,
                min_distance_m=ev.min_distance_m,
                distance_confidence=ev.distance_confidence,
                max_confidence=ev.max_confidence,
                lat=pos[0] if pos else None,
                lon=pos[1] if pos else None,
                clip_key=clip_keys.get(ev.event_id),
                metrics={"peak_box_xyxy": list(ev.peak_box_xyxy), "start_frame": ev.start_frame},
            )
        )
    db.add_all(rows)
    db.flush()  # assigns ids, which the feedback lines link to

    for hz in doc.hazards:
        # Position when the hazard was LAST seen: the camera is closest to it then (just before
        # driving over or past it), so that fix is the best estimate of where it is.
        pos = (hz.gps.lat, hz.gps.lon) if hz.gps else (track.position_at(hz.last_seen_s) if track else None)
        if pos:
            hazards.add_sighting(db, trip.id, hz.class_, pos[0], pos[1], hz.last_seen_s, settings.hazard_merge_radius_m)

    checks = doc.trip_summary.checks.model_dump()
    distance_km = trip.distance_km if track else None
    report = score_trip(
        risk,
        [ScoredEvent(e.id, e.type.value, e.severity.value, e.peak_s, e.min_ttc_s) for e in rows],
        checks,
        doc.video.duration_s,
        distance_km,
    )
    db.add(
        TripReport(
            trip_id=trip.id,
            score=report.score,
            risk_rate=report.risk_rate,
            exposure_unit=report.exposure_unit,
            exposure_value=report.exposure_value,
            provisional=report.provisional,
            scoring_version=report.scoring_version,
            breakdown={
                "by_type": report.breakdown,
                "trip": {
                    "ttc_below_warning_s": doc.trip_summary.ttc_below_warning_s,
                    "ttc_below_critical_s": doc.trip_summary.ttc_below_critical_s,
                    "min_ttc_s": doc.trip_summary.min_ttc_s,
                    "objects_seen": doc.objects_seen,
                    "gps": "ran" if track else checks.get("gps"),
                    "thresholds": doc.thresholds.model_dump(),
                    "classes_version": doc.classes_version,
                    # "h264" plays in browsers; "mp4v" (no ffmpeg on the worker) does not.
                    "video_codec": _run_summary(out_dir).get("video_codec"),
                },
            },
            feedback=report.feedback,
            not_checked=report.not_checked + ([] if track else [NO_GPS]),
        )
    )

    trip.duration_s = doc.video.duration_s
    trip.fps = doc.video.fps
    trip.status = TripStatus.done
    trip.error = None
    trip.processed_at = datetime.now(UTC)
