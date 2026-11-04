"""Database schema. Invariants live in the database (CHECKs, FKs, enums, uniques), not only in Python.

Read the "Database schema" section of the backend design doc for why each table exists.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # Store the lowercase value ("queued"), not the Python member name.
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class TripStatus(enum.StrEnum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class TripSource(enum.StrEnum):
    upload = "upload"  # processed by our worker
    imported = "imported"  # results zip produced elsewhere (e.g. Kaggle)


class EventType(enum.StrEnum):
    forward_collision = "forward_collision"
    obstacle_in_lane = "obstacle_in_lane"
    tailgating = "tailgating"
    harsh_braking = "harsh_braking"


class Severity(enum.StrEnum):
    warning = "warning"
    critical = "critical"


class HazardClass(enum.StrEnum):
    pothole = "pothole"
    barricade = "barricade"
    speed_breaker = "speed_breaker"
    debris = "debris"


def _now() -> Any:
    return func.now()


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[TripStatus] = mapped_column(_enum(TripStatus, "trip_status"), default=TripStatus.queued)
    source: Mapped[TripSource] = mapped_column(_enum(TripSource, "trip_source"), default=TripSource.upload)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    video_key: Mapped[str | None] = mapped_column(String(500))  # null after cleanup, or for imports
    video_bytes: Mapped[int | None] = mapped_column(BigInteger)
    annotated_key: Mapped[str | None] = mapped_column(String(500))
    gps_key: Mapped[str | None] = mapped_column(String(500))
    duration_s: Mapped[float | None] = mapped_column(Float)
    fps: Mapped[float | None] = mapped_column(Float)
    distance_km: Mapped[float | None] = mapped_column(Float)  # from the GPS track; null without GPS
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list[Event]] = relationship(back_populates="trip", passive_deletes=True)
    report: Mapped[TripReport | None] = relationship(back_populates="trip", passive_deletes=True)

    __table_args__ = (
        CheckConstraint("duration_s IS NULL OR duration_s >= 0", name="duration_nonneg"),
        CheckConstraint("distance_km IS NULL OR distance_km >= 0", name="distance_nonneg"),
        CheckConstraint("video_bytes IS NULL OR video_bytes >= 0", name="video_bytes_nonneg"),
        Index("ix_trips_created_at_id", "created_at", "id"),  # newest-first cursor pagination
    )


class Job(Base):
    """The job queue. The worker claims rows with SELECT ... FOR UPDATE SKIP LOCKED."""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), default=JobStatus.queued)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_nonneg"),
        # The claim query scans only queued jobs, oldest first.
        Index("ix_jobs_queued", "run_after", "created_at", postgresql_where="status = 'queued'"),
        # At most one live job per trip, so a double-click on "retry" can't process a trip twice.
        Index(
            "uq_jobs_one_live_per_trip",
            "trip_id",
            unique=True,
            postgresql_where="status IN ('queued', 'running')",
        ),
    )


class GpsPoint(Base):
    __tablename__ = "gps_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    t_s: Mapped[float] = mapped_column(Float)  # seconds from the start of the video
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="lon_range"),
        CheckConstraint("t_s >= 0", name="t_nonneg"),
        Index("ix_gps_points_trip_t", "trip_id", "t_s"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    pipeline_event_id: Mapped[int] = mapped_column(Integer)  # event_id from events.json
    type: Mapped[EventType] = mapped_column(_enum(EventType, "event_type"))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"))
    class_name: Mapped[str] = mapped_column(String(50))
    track_id: Mapped[int] = mapped_column(Integer)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    peak_s: Mapped[float] = mapped_column(Float)
    min_ttc_s: Mapped[float | None] = mapped_column(Float)
    min_distance_m: Mapped[float | None] = mapped_column(Float)
    distance_confidence: Mapped[str] = mapped_column(String(10))
    max_confidence: Mapped[float] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    clip_key: Mapped[str | None] = mapped_column(String(500))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # peak box etc., for display

    trip: Mapped[Trip] = relationship(back_populates="events")

    __table_args__ = (
        UniqueConstraint("trip_id", "pipeline_event_id", name="uq_events_trip_pipeline_id"),
        CheckConstraint("start_s >= 0 AND end_s >= start_s", name="times_ordered"),
        CheckConstraint("distance_confidence IN ('low', 'ok')", name="distance_confidence_values"),
        CheckConstraint("(lat IS NULL) = (lon IS NULL)", name="latlon_together"),
        Index("ix_events_trip_peak", "trip_id", "peak_s"),
    )


class Hazard(Base):
    """One physical pothole/obstacle. Sightings within `merge_radius_m` of each other merge here."""

    __tablename__ = "hazards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hazard_class: Mapped[HazardClass] = mapped_column(_enum(HazardClass, "hazard_class"))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

    __table_args__ = (
        CheckConstraint("lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("lon BETWEEN -180 AND 180", name="lon_range"),
        Index("ix_hazards_class_lat_lon", "hazard_class", "lat", "lon"),
        Index("ix_hazards_lat_lon", "lat", "lon"),
    )


class HazardSighting(Base):
    """Each time a trip saw a hazard. seen_count and last_seen are derived from these rows, so
    deleting or reprocessing a trip can never leave a stale counter behind."""

    __tablename__ = "hazard_sightings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hazard_id: Mapped[int] = mapped_column(ForeignKey("hazards.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    t_s: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())


class TripReport(Base):
    __tablename__ = "trip_reports"

    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[float | None] = mapped_column(Float)  # null when nothing could be checked
    risk_rate: Mapped[float | None] = mapped_column(Float)
    exposure_unit: Mapped[str] = mapped_column(String(20))  # "per_100_km" | "per_hour"
    exposure_value: Mapped[float] = mapped_column(Float)
    provisional: Mapped[bool] = mapped_column(default=True)  # R_half not yet calibrated on real footage
    scoring_version: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    feedback: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    not_checked: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())

    trip: Mapped[Trip] = relationship(back_populates="report")

    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="score_range"),
        CheckConstraint("exposure_value > 0", name="exposure_positive"),
        CheckConstraint("exposure_unit IN ('per_100_km', 'per_hour')", name="exposure_unit_values"),
    )


class WorkerHeartbeat(Base):
    """One row per worker process, refreshed while idle too, so /healthz can tell "no jobs" from
    "no worker running"."""

    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now())
