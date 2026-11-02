"""events.json writer.

The schema is a DRAFT owned by the architecture thread (milestone M4, "events schema
freeze"); the backend will ingest this file. Bump SCHEMA_VERSION on any change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dashcam_perception.alerts import AlertEvent

SCHEMA_VERSION = "0.1-draft"


def _round(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(v, nd)


def event_to_dict(e: AlertEvent, clip_path: str | None) -> dict[str, Any]:
    b = e.peak_box
    return {
        "event_id": e.event_id,
        "type": str(e.type),
        "severity": str(e.severity),
        "track_id": e.track_id,
        "class_name": e.class_name,
        "start_frame": e.start_frame,
        "start_time_s": _round(e.start_time_s),
        "end_time_s": _round(e.end_time_s),
        "peak_time_s": _round(e.peak_time_s),
        "min_ttc_s": _round(e.min_ttc_s, 2),
        # Monocular, uncalibrated: approximate (see geometry.py).
        "min_distance_m_approx": _round(e.min_distance_m, 1),
        "max_confidence": _round(e.max_confidence, 3),
        "peak_box_xyxy": [round(b.x1, 1), round(b.y1, 1), round(b.x2, 1), round(b.y2, 1)],
        # No GPS source yet (no device). Filled by the backend from a GPX/CSV sidecar later.
        "gps": None,
        "clip": clip_path,
    }


def write_events(
    path: Path,
    events: list[AlertEvent],
    video: dict[str, Any],
    run: dict[str, Any],
    clips: dict[int, str] | None = None,
) -> None:
    clips = clips or {}
    doc = {
        "schema_version": SCHEMA_VERSION,
        "video": video,
        "run": run,
        "events": [event_to_dict(e, clips.get(e.event_id)) for e in events],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
