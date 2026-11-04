from __future__ import annotations

import io
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import Select, func, insert, select, tuple_
from sqlalchemy.exc import IntegrityError

from app.api import pagination
from app.api.deps import DbDep, SettingsDep, StorageDep
from app.api.errors import ApiError, not_found
from app.api.schemas import EventOut, Page, ReportOut, TripOut
from app.db.models import Event, EventType, GpsPoint, Severity, Trip, TripReport, TripStatus
from app.services import hazards
from app.services.gps import GpsParseError, parse_gps, track_distance_km
from app.services.uploads import looks_like_video, safe_filename, video_extension
from app.storage import Storage, StorageError, TooLarge
from app.worker import queue

router = APIRouter(prefix="/trips", tags=["trips"])

LabelForm = Annotated[str | None, Form(max_length=200)]


def trip_out(trip: Trip, score: float | None, event_count: int, has_gps: bool) -> TripOut:
    return TripOut(
        id=trip.id,
        label=trip.label,
        status=trip.status.value,
        source=trip.source.value,
        original_filename=trip.original_filename,
        duration_s=trip.duration_s,
        distance_km=trip.distance_km,
        has_gps=has_gps,
        has_original_video=trip.video_key is not None,
        has_annotated_video=trip.annotated_key is not None,
        score=score,
        event_count=event_count,
        error=trip.error,
        created_at=trip.created_at,
        processed_at=trip.processed_at,
    )


def _trip_rows() -> Select:
    events = select(func.count(Event.id)).where(Event.trip_id == Trip.id).correlate(Trip).scalar_subquery()
    has_gps = select(GpsPoint.id).where(GpsPoint.trip_id == Trip.id).limit(1).exists()
    return select(Trip, TripReport.score, events.label("event_count"), has_gps.label("has_gps")).outerjoin(
        TripReport, TripReport.trip_id == Trip.id
    )


def load_trip_out(db: DbDep, trip_id: uuid.UUID) -> TripOut:
    row = db.execute(_trip_rows().where(Trip.id == trip_id)).first()
    if row is None:
        raise not_found("trip")
    return trip_out(row[0], row[1], row[2], row[3])


def save_gps(db: DbDep, storage: Storage, trip: Trip, upload: UploadFile, max_bytes: int) -> None:
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ApiError(413, "too_large", f"GPS file is larger than {max_bytes // 1024**2} MB")
    name = safe_filename(upload.filename) or "track"
    try:
        fixes = parse_gps(data, name)
    except GpsParseError as e:
        raise ApiError(422, "bad_gps", str(e)) from e
    ext = ".gpx" if name.lower().endswith(".gpx") else ".csv"
    trip.gps_key = f"trips/{trip.id}/gps{ext}"
    storage.put_stream(trip.gps_key, io.BytesIO(data), max_bytes)
    db.execute(insert(GpsPoint), [{"trip_id": trip.id, "t_s": f.t_s, "lat": f.lat, "lon": f.lon} for f in fixes])
    trip.distance_km = round(track_distance_km(fixes), 3)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TripOut)
def upload_trip(
    db: DbDep,
    storage: StorageDep,
    settings: SettingsDep,
    video: Annotated[UploadFile, File(description="Dashcam video: .mp4, .mov, .m4v, .avi or .mkv")],
    gps: Annotated[UploadFile | None, File(description="Optional GPS track: .gpx or .csv")] = None,
    label: LabelForm = None,
) -> TripOut:
    """Upload a video (and optional GPS file). Processing starts in the background; poll
    GET /trips/{id} until status is `done` or `failed`."""
    ext = video_extension(video.filename)
    head = video.file.read(16)
    video.file.seek(0)
    if ext is None or not looks_like_video(head):
        raise ApiError(415, "unsupported_media", "Upload a video file (.mp4, .mov, .m4v, .avi or .mkv).")

    trip = Trip(id=uuid.uuid4(), label=(label or "").strip() or None, original_filename=safe_filename(video.filename))
    trip.video_key = f"trips/{trip.id}/source{ext}"
    try:
        trip.video_bytes = storage.put_stream(trip.video_key, video.file, settings.max_upload_bytes)
        if trip.video_bytes == 0:
            raise ApiError(422, "empty_file", "The video file is empty.")
        db.add(trip)
        db.flush()
        if gps is not None and gps.filename:
            save_gps(db, storage, trip, gps, settings.max_gps_bytes)
        queue.enqueue(db, trip)
        db.commit()
    except TooLarge as e:
        db.rollback()
        storage.delete_prefix(f"trips/{trip.id}")
        raise ApiError(413, "too_large", f"Video is larger than {settings.max_upload_bytes // 1024**3} GB.") from e
    except BaseException:
        db.rollback()
        storage.delete_prefix(f"trips/{trip.id}")  # no orphan files when the DB write fails
        raise
    return load_trip_out(db, trip.id)


@router.get("", response_model=Page[TripOut])
def list_trips(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    status_: Annotated[TripStatus | None, Query(alias="status")] = None,
) -> Page[TripOut]:
    """Trips, newest first."""
    stmt = _trip_rows().order_by(Trip.created_at.desc(), Trip.id.desc()).limit(limit + 1)
    if status_ is not None:
        stmt = stmt.where(Trip.status == status_)
    if cursor:
        created, tid = pagination.decode(cursor, 2)
        try:
            key = (datetime.fromisoformat(created), uuid.UUID(tid))
        except (TypeError, ValueError) as e:
            raise ApiError(400, "bad_cursor", "cursor is not valid") from e
        stmt = stmt.where(tuple_(Trip.created_at, Trip.id) < key)
    rows = db.execute(stmt).all()
    items = [trip_out(r[0], r[1], r[2], r[3]) for r in rows[:limit]]
    nxt = (
        pagination.encode(rows[limit - 1][0].created_at.isoformat(), rows[limit - 1][0].id)
        if len(rows) > limit
        else None
    )
    return Page[TripOut](items=items, next_cursor=nxt)


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(db: DbDep, trip_id: uuid.UUID) -> TripOut:
    return load_trip_out(db, trip_id)


@router.get("/{trip_id}/report", response_model=ReportOut)
def get_report(db: DbDep, trip_id: uuid.UUID) -> TripReport:
    report = db.get(TripReport, trip_id)
    if report is None:
        if db.get(Trip, trip_id) is None:
            raise not_found("trip")
        raise ApiError(409, "not_ready", "The report is not ready yet; the trip is still processing or failed.")
    return report


@router.get("/{trip_id}/events", response_model=Page[EventOut])
def list_events(
    db: DbDep,
    trip_id: uuid.UUID,
    type_: Annotated[EventType | None, Query(alias="type")] = None,
    severity: Severity | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> Page[EventOut]:
    """A trip's events in video order."""
    if db.get(Trip, trip_id) is None:
        raise not_found("trip")
    stmt = select(Event).where(Event.trip_id == trip_id).order_by(Event.peak_s, Event.id).limit(limit + 1)
    if type_:
        stmt = stmt.where(Event.type == type_)
    if severity:
        stmt = stmt.where(Event.severity == severity)
    if cursor:
        peak, eid = pagination.decode(cursor, 2)
        if not isinstance(peak, int | float) or not isinstance(eid, int):
            raise ApiError(400, "bad_cursor", "cursor is not valid")
        stmt = stmt.where(tuple_(Event.peak_s, Event.id) > (peak, eid))
    rows = db.scalars(stmt).all()
    items = [event_out(e) for e in rows[:limit]]
    nxt = pagination.encode(rows[limit - 1].peak_s, rows[limit - 1].id) if len(rows) > limit else None
    return Page[EventOut](items=items, next_cursor=nxt)


def event_out(e: Event) -> EventOut:
    return EventOut.model_validate(
        {
            **{c: getattr(e, c) for c in EventOut.model_fields if hasattr(e, c)},
            "type": e.type.value,
            "severity": e.severity.value,
            "has_clip": e.clip_key is not None,
        }
    )


@router.get("/{trip_id}/video", response_class=FileResponse)
def get_video(db: DbDep, storage: StorageDep, trip_id: uuid.UUID, annotated: bool = False) -> Response:
    """The original or annotated video. Supports HTTP Range, so the player can seek."""
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise not_found("trip")
    key = trip.annotated_key if annotated else trip.video_key
    if key is None:
        raise ApiError(404, "not_found", "annotated video not available" if annotated else "original video was deleted")
    return serve(storage, key)


def serve(storage: Storage, key: str) -> Response:
    try:
        path = storage.local_path(key)
    except StorageError as e:
        raise not_found("file") from e
    if path is None or not path.is_file():
        raise not_found("file")
    return FileResponse(path, media_type="video/mp4" if key.endswith((".mp4", ".m4v")) else None)


@router.post("/{trip_id}/retry", response_model=TripOut)
def retry_trip(db: DbDep, trip_id: uuid.UUID) -> TripOut:
    """Requeue a failed trip."""
    trip = db.get(Trip, trip_id, with_for_update=True)
    if trip is None:
        raise not_found("trip")
    if trip.status != TripStatus.failed:
        raise ApiError(409, "not_failed", f"Only failed trips can be retried (this one is {trip.status.value}).")
    if trip.video_key is None:
        raise ApiError(409, "no_video", "The original video was deleted, so this trip can't be reprocessed.")
    queue.enqueue(db, trip)
    trip.error = None
    try:
        db.commit()
    except IntegrityError as e:  # a live job already exists (double click)
        db.rollback()
        raise ApiError(409, "already_queued", "This trip is already queued.") from e
    return load_trip_out(db, trip_id)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(db: DbDep, storage: StorageDep, trip_id: uuid.UUID) -> Response:
    """Delete a trip, its events, report, GPS points and files. Hazards seen only on this trip go too."""
    trip = db.get(Trip, trip_id, with_for_update=True)
    if trip is None:
        raise not_found("trip")
    hazards.clear_trip_sightings(db, trip_id)
    db.delete(trip)
    db.commit()
    storage.delete_prefix(f"trips/{trip_id}")  # after commit: a failed commit must not lose files
    return Response(status_code=status.HTTP_204_NO_CONTENT)
