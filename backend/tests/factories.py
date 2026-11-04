"""Builders for test data. events.json documents are built with perception's own pydantic models,
so the fixtures can't drift from the real contract."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from dashcam_perception.schema import GPS, Checks, Event, EventsDocument, Hazard, Thresholds, TripSummary, Video

from app.worker.pipeline import PipelineError

# 'ftyp' at bytes 4-8 is all our upload check looks for; the pipeline is faked in tests.
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048
FAKE_CLIP = b"\x00\x00\x00\x18ftypisom" + b"clip" * 256

ALL_RAN = {
    "forward_collision": "ran",
    "obstacle_in_lane": "ran",
    "tailgating": "ran",
    "harsh_braking": "ran",
    "gps": "skipped_no_gps",
}
COCO_CHECKS = {
    "forward_collision": "ran",
    "obstacle_in_lane": "absent",
    "tailgating": "skipped_no_ego_speed",
    "harsh_braking": "skipped_no_ego_speed",
    "gps": "skipped_no_gps",
}


def event(
    event_id: int,
    type_: str = "forward_collision",
    severity: str = "warning",
    peak: float = 10.0,
    ttc: float | None = 2.0,
    clip: bool = True,
    gps: tuple[float, float] | None = None,
) -> Event:
    return Event(
        event_id=event_id,
        type=type_,
        severity=severity,
        track_id=100 + event_id,
        class_name="car",
        start_frame=int((peak - 1) * 30),
        start_time_s=peak - 1,
        end_time_s=peak + 1,
        peak_time_s=peak,
        min_ttc_s=ttc,
        min_distance_m=12.5,
        distance_confidence="low",
        max_confidence=0.8,
        peak_box_xyxy=(10.0, 20.0, 110.0, 120.0),
        gps=GPS(lat=gps[0], lon=gps[1]) if gps else None,
        clip=f"clips/event_{event_id:04d}.mp4" if clip else None,
    )


def hazard(
    track_id: int, cls: str = "pothole", last_seen: float = 20.0, gps: tuple[float, float] | None = None
) -> Hazard:
    return Hazard.model_validate(
        {
            "class": cls,
            "track_id": track_id,
            "first_seen_s": max(0.0, last_seen - 2),
            "last_seen_s": last_seen,
            "gps": {"lat": gps[0], "lon": gps[1]} if gps else None,
        }
    )


def document(
    events: list[Event] | None = None,
    hazards: list[Hazard] | None = None,
    checks: dict[str, str] | None = None,
    duration_s: float = 600.0,
) -> EventsDocument:
    events = events or []
    counts = {
        t: {"warning": 0, "critical": 0}
        for t in ("forward_collision", "obstacle_in_lane", "tailgating", "harsh_braking")
    }
    for e in events:
        counts[e.type][e.severity] += 1
    return EventsDocument(
        classes_version=1,
        video=Video(
            path="trip.mp4",
            duration_s=duration_s,
            fps=30.0,
            frames_processed=int(duration_s * 30),
            width=1280,
            height=720,
        ),
        thresholds=Thresholds(ttc_warning_s=2.5, ttc_critical_s=1.5),
        events=events,
        hazards=hazards or [],
        trip_summary=TripSummary(
            ttc_below_warning_s=1.0,
            ttc_below_critical_s=0.0,
            min_ttc_s=min((e.min_ttc_s for e in events if e.min_ttc_s), default=None),
            event_counts=counts,
            checks=Checks(**(checks or COCO_CHECKS)),
        ),
        objects_seen={"car": 3},
    )


def write_output(out_dir: Path, doc: EventsDocument, annotated: bool = True) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "events.json").write_text(doc.to_json(), encoding="utf-8")
    (out_dir / "run_summary.json").write_text(
        json.dumps({"frames": doc.video.frames_processed, "video_codec": "h264"}), encoding="utf-8"
    )
    if annotated:
        (out_dir / "annotated.mp4").write_bytes(FAKE_MP4)
    for e in doc.events:
        if e.clip:
            (out_dir / e.clip).parent.mkdir(parents=True, exist_ok=True)
            (out_dir / e.clip).write_bytes(FAKE_CLIP)


def results_zip(path: Path, doc: EventsDocument, folder: str = "", extra: dict[str, bytes] | None = None) -> Path:
    staging = path.parent / "zip-staging"
    write_output(staging, doc)
    with zipfile.ZipFile(path, "w") as zf:
        for f in staging.rglob("*"):
            if f.is_file():
                zf.write(f, (f"{folder}/" if folder else "") + f.relative_to(staging).as_posix())
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


class FakeRunner:
    """Stands in for perception: writes a fixed output folder, or raises."""

    def __init__(self, doc: EventsDocument | None = None, error: PipelineError | None = None) -> None:
        self.doc = doc or document(
            [event(1, severity="critical", peak=30.0), event(2, "obstacle_in_lane", peak=200.0)],
            [hazard(7)],
            checks=ALL_RAN,
        )
        self.error = error
        self.calls: list[tuple[Path, Path]] = []

    def run(self, video: Path, out_dir: Path) -> None:
        self.calls.append((video, out_dir))
        if self.error:
            raise self.error
        write_output(out_dir, self.doc)
