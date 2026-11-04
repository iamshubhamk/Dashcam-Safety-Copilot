from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select, text

from app.api.deps import DbDep, SettingsDep, StorageDep
from app.api.errors import ApiError, not_found
from app.api.schemas import EventOut, HazardList, HazardOut, HealthOut
from app.api.trips import event_out, serve
from app.db.models import Event, Hazard, HazardClass, HazardSighting
from app.worker import queue

router = APIRouter()

MAX_HAZARDS = 2000


@router.get("/events/{event_id}", response_model=EventOut, tags=["events"])
def get_event(db: DbDep, event_id: int) -> EventOut:
    e = db.get(Event, event_id)
    if e is None:
        raise not_found("event")
    return event_out(e)


@router.get("/events/{event_id}/clip", tags=["events"])
def get_clip(db: DbDep, storage: StorageDep, event_id: int) -> Response:
    """The short clip around one event (about 5 s before to 5 s after)."""
    e = db.get(Event, event_id)
    if e is None:
        raise not_found("event")
    if e.clip_key is None:
        raise ApiError(404, "not_found", "this event has no clip")
    return serve(storage, e.clip_key)


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """`west,south,east,north`, the order Leaflet's map.getBounds().toBBoxString() produces."""
    try:
        w, s, e, n = (float(v) for v in bbox.split(","))
    except ValueError as err:
        raise ApiError(422, "bad_bbox", "bbox must be west,south,east,north") from err
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= n <= 90):
        raise ApiError(422, "bad_bbox", "bbox is out of range")
    return w, s, e, n


@router.get("/hazards", response_model=HazardList, tags=["hazards"])
def list_hazards(
    db: DbDep,
    bbox: Annotated[str, Query(description="west,south,east,north", examples=["72.8,18.9,73.0,19.1"])],
    hazard_class: Annotated[HazardClass | None, Query(alias="class")] = None,
) -> HazardList:
    """Hazards inside the visible map area, most-seen first."""
    w, s, e, n = parse_bbox(bbox)
    lon_ok = Hazard.lon.between(w, e) if w <= e else (Hazard.lon >= w) | (Hazard.lon <= e)  # antimeridian
    seen = func.count(HazardSighting.id)
    stmt = (
        select(
            Hazard,
            seen.label("seen"),
            func.count(func.distinct(HazardSighting.trip_id)).label("trips"),
            func.min(HazardSighting.seen_at).label("first"),
            func.max(HazardSighting.seen_at).label("last"),
        )
        .join(HazardSighting, HazardSighting.hazard_id == Hazard.id)
        .where(Hazard.lat.between(s, n), lon_ok)
        .group_by(Hazard.id)
        .order_by(seen.desc(), Hazard.id)
        .limit(MAX_HAZARDS + 1)
    )
    if hazard_class:
        stmt = stmt.where(Hazard.hazard_class == hazard_class)
    rows = db.execute(stmt).all()
    items = [
        HazardOut(
            id=h.id,
            hazard_class=h.hazard_class.value,
            lat=h.lat,
            lon=h.lon,
            seen_count=seen_n,
            trip_count=trips,
            first_seen_at=first,
            last_seen_at=last,
        )
        for h, seen_n, trips, first, last in rows[:MAX_HAZARDS]
    ]
    return HazardList(items=items, truncated=len(rows) > MAX_HAZARDS)


@router.get("/healthz", response_model=HealthOut, tags=["health"])
def healthz(db: DbDep, settings: SettingsDep, response: Response) -> HealthOut:
    """API up + database reachable + a worker seen recently. 503 if the database is down."""
    try:
        db.execute(text("SELECT 1"))
        age = queue.latest_worker_age_s(db)
    except Exception:
        response.status_code = 503
        return HealthOut(status="down", database="unreachable", worker="unknown", worker_last_seen_s=None)
    worker = "never_seen" if age is None else ("ok" if age <= settings.worker_heartbeat_max_age_s else "stale")
    return HealthOut(
        status="ok" if worker == "ok" else "degraded",
        database="ok",
        worker=worker,
        worker_last_seen_s=round(age, 1) if age is not None else None,
    )
