import json

import pytest
from conftest import REPO
from pydantic import ValidationError

from dashcam_perception.schema import EventsDocument, Hazard, json_schema

SCHEMA_FILE = REPO / "perception" / "schema" / "events.v1.json"


def test_exported_schema_matches_models():
    """The backend/UI read the exported file; it must not drift from the pydantic models.
    Fix with: python -m dashcam_perception.schema (from the repo root)."""
    assert SCHEMA_FILE.read_text(encoding="utf-8") == json_schema()


def test_hazard_uses_class_as_json_key():
    h = Hazard(class_="pothole", track_id=3, first_seen_s=1.0, last_seen_s=2.0, gps=None)
    assert json.loads(h.model_dump_json(by_alias=True))["class"] == "pothole"
    assert Hazard.model_validate({"class": "debris", "track_id": 1, "first_seen_s": 0, "last_seen_s": 0, "gps": None})


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        Hazard.model_validate(
            {"class": "pothole", "track_id": 1, "first_seen_s": 0, "last_seen_s": 0, "gps": None, "extra": 1}
        )


def test_bad_enum_rejected():
    with pytest.raises(ValidationError):
        Hazard.model_validate({"class": "cow", "track_id": 1, "first_seen_s": 0, "last_seen_s": 0, "gps": None})


def test_schema_requires_trip_summary():
    schema = json.loads(json_schema())
    assert "trip_summary" in schema["required"] and "objects_seen" in schema["required"]
    assert EventsDocument.model_fields["schema_version"].default == "1.0"
