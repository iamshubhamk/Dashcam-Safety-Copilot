"""events.json v1: the contract between perception and the backend/dashboard.

These pydantic models are the single source of truth. The backend imports them from this
package; the backend and UI threads read the exported JSON Schema at
perception/schema/events.v1.json, which is regenerated with:

    python -m dashcam_perception.schema

and checked against these models by tests/test_schema.py. Field names were frozen with the
architecture thread on 2026-11-04. Changing them means bumping SCHEMA_VERSION and agreeing
the change there first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["1.0"] = "1.0"
SCHEMA_PATH = Path("perception/schema/events.v1.json")

# Every alert type the report may mention. Only the first two are produced today; the
# others exist so counts are zero-filled and `checks` can say they were skipped.
EventType = Literal["forward_collision", "obstacle_in_lane", "tailgating", "harsh_braking"]
EVENT_TYPES: tuple[str, ...] = ("forward_collision", "obstacle_in_lane", "tailgating", "harsh_braking")
SeverityName = Literal["warning", "critical"]
SEVERITIES: tuple[str, ...] = ("warning", "critical")
CheckStatus = Literal["ran", "skipped_no_ego_speed", "skipped_no_gps", "absent"]
HAZARD_CLASSES: tuple[str, ...] = ("pothole", "barricade", "speed_breaker", "debris")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GPS(_Strict):
    lat: float
    lon: float


class Video(_Strict):
    path: str
    duration_s: float = Field(ge=0)
    fps: float = Field(gt=0)
    frames_processed: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Thresholds(_Strict):
    ttc_warning_s: float = Field(gt=0)
    ttc_critical_s: float = Field(gt=0)


class Event(_Strict):
    event_id: int = Field(ge=1)
    type: EventType
    severity: SeverityName
    track_id: int
    class_name: str
    start_frame: int = Field(ge=0)
    start_time_s: float = Field(ge=0)
    end_time_s: float = Field(ge=0)
    peak_time_s: float = Field(ge=0)
    min_ttc_s: float | None = Field(description="Lowest time-to-collision during the episode; null if never computed")
    min_distance_m: float | None = Field(description="Closest monocular distance estimate during the episode")
    distance_confidence: Literal["low", "ok"] = Field(
        description="'low' while the camera is uncalibrated: distances can be off by 20-40%"
    )
    max_confidence: float = Field(ge=0, le=1, description="Highest detector confidence for this object")
    peak_box_xyxy: tuple[float, float, float, float]
    gps: GPS | None
    clip: str | None = Field(description="Clip path relative to the output folder, if clips were written")


class Hazard(_Strict):
    # `class` is a Python keyword, so the attribute is class_ and the JSON key is "class".
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    class_: Literal["pothole", "barricade", "speed_breaker", "debris"] = Field(alias="class")
    track_id: int
    first_seen_s: float = Field(ge=0)
    last_seen_s: float = Field(ge=0)
    gps: GPS | None


class Checks(_Strict):
    """What the pipeline did and didn't check, so the report never implies a clean bill of
    health for something it couldn't look at."""

    forward_collision: CheckStatus
    obstacle_in_lane: CheckStatus
    tailgating: CheckStatus
    harsh_braking: CheckStatus
    gps: CheckStatus


class TripSummary(_Strict):
    ttc_below_warning_s: float = Field(
        ge=0, description="Seconds with a road user in our lane at TTC <= warning threshold (includes critical time)"
    )
    ttc_below_critical_s: float = Field(ge=0, description="Seconds with a road user in our lane at TTC <= critical")
    min_ttc_s: float | None = Field(description="Lowest in-lane TTC over the trip; null if nothing was ever closing")
    event_counts: dict[EventType, dict[SeverityName, int]]
    checks: Checks


class EventsDocument(_Strict):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    classes_version: int
    video: Video
    thresholds: Thresholds
    events: list[Event]
    hazards: list[Hazard]
    trip_summary: TripSummary
    objects_seen: dict[str, int] = Field(
        description="Unique tracked objects per class (classes.yaml names, zero-filled), not per-frame detections"
    )

    def to_json(self) -> str:
        return self.model_dump_json(indent=2, by_alias=True) + "\n"


def json_schema() -> str:
    return json.dumps(EventsDocument.model_json_schema(by_alias=True), indent=2, sort_keys=True) + "\n"


def main() -> int:
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(json_schema(), encoding="utf-8")
    print(f"wrote {SCHEMA_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
