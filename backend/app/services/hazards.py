"""Merge pothole/obstacle sightings from many trips into one hazard per physical spot."""

from __future__ import annotations

import math
import uuid

from sqlalchemy import delete, exists, select, text
from sqlalchemy.orm import Session

from app.db.models import Hazard, HazardClass, HazardSighting
from app.services.gps import haversine_m

# Any constant works; it just has to be the same everywhere hazards are merged.
_MERGE_LOCK = 0x4841_5A44  # "HAZD"


def _bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def add_sighting(
    db: Session, trip_id: uuid.UUID, hazard_class: str, lat: float, lon: float, t_s: float, radius_m: float
) -> Hazard:
    """Attach a sighting to the nearest same-class hazard within radius_m, or create a new hazard.

    The hazard keeps the position where it was first seen; later sightings only add to its count.
    (Averaging would let a chain of sightings 14 m apart drift a hazard down the road.)
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _MERGE_LOCK})  # two workers can't race a merge
    lat0, lat1, lon0, lon1 = _bbox(lat, lon, radius_m)
    candidates = db.scalars(
        select(Hazard).where(
            Hazard.hazard_class == HazardClass(hazard_class),
            Hazard.lat.between(lat0, lat1),
            Hazard.lon.between(lon0, lon1),
        )
    ).all()
    best = min(candidates, key=lambda h: haversine_m(lat, lon, h.lat, h.lon), default=None)
    if best is None or haversine_m(lat, lon, best.lat, best.lon) > radius_m:
        best = Hazard(hazard_class=HazardClass(hazard_class), lat=lat, lon=lon)
        db.add(best)
        db.flush()
    db.add(HazardSighting(hazard_id=best.id, trip_id=trip_id, t_s=t_s, lat=lat, lon=lon))
    return best


def clear_trip_sightings(db: Session, trip_id: uuid.UUID) -> None:
    """Remove a trip's sightings (before reprocessing or on delete) and any hazard left with none."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _MERGE_LOCK})
    db.execute(delete(HazardSighting).where(HazardSighting.trip_id == trip_id))
    delete_orphan_hazards(db)


def delete_orphan_hazards(db: Session) -> None:
    db.execute(delete(Hazard).where(~exists().where(HazardSighting.hazard_id == Hazard.id)))
