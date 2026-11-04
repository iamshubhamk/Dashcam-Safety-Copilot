"""Response models: the API's public contract with the dashboard (also shown at /docs)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class JobOut(_Out):
    status: str
    attempts: int
    error: str | None


class TripOut(_Out):
    id: uuid.UUID
    label: str | None
    status: str
    source: str
    original_filename: str | None
    duration_s: float | None
    distance_km: float | None
    has_gps: bool
    has_original_video: bool
    has_annotated_video: bool
    score: float | None
    event_count: int
    error: str | None
    created_at: datetime
    processed_at: datetime | None


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class FeedbackLine(BaseModel):
    kind: str  # issue | positive | pattern | worst_moments
    text: str
    event_ids: list[int]
    type: str | None = None


class NotChecked(BaseModel):
    type: str
    label: str
    status: str
    reason: str


class ReportOut(_Out):
    trip_id: uuid.UUID
    score: float | None
    risk_rate: float | None
    exposure_unit: str
    exposure_value: float
    provisional: bool
    scoring_version: int
    breakdown: dict[str, Any]
    feedback: list[FeedbackLine]
    not_checked: list[NotChecked]


class EventOut(_Out):
    id: int
    trip_id: uuid.UUID
    type: str
    severity: str
    class_name: str
    track_id: int
    start_s: float
    end_s: float
    peak_s: float
    min_ttc_s: float | None
    min_distance_m: float | None
    distance_confidence: str
    max_confidence: float
    lat: float | None
    lon: float | None
    has_clip: bool
    metrics: dict[str, Any]


class HazardOut(BaseModel):
    id: int
    hazard_class: str
    lat: float
    lon: float
    seen_count: int
    trip_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class HazardList(BaseModel):
    items: list[HazardOut]
    truncated: bool


class HealthOut(BaseModel):
    status: str  # ok | degraded
    database: str
    worker: str  # ok | stale | never_seen
    worker_last_seen_s: float | None
