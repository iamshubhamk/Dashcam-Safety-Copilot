"""Opaque cursors for keyset pagination: stable under inserts, no OFFSET scans."""

from __future__ import annotations

import base64
import json
from typing import Any

from app.api.errors import ApiError


def encode(*values: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, default=str).encode()).decode().rstrip("=")


def decode(cursor: str, n: int) -> list[Any]:
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, json.JSONDecodeError) as e:
        raise ApiError(400, "bad_cursor", "cursor is not valid") from e
    if not isinstance(values, list) or len(values) != n:
        raise ApiError(400, "bad_cursor", "cursor is not valid")
    return values
