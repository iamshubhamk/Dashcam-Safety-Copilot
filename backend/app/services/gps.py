"""GPS sidecar parsing (GPX or CSV) and helpers to place events on the map.

Time alignment: the video has no wall clock we can trust, so every track is converted to
"seconds from the start of the video". For files with absolute timestamps (all GPX files and
CSVs with a `timestamp` column) we ASSUME the first fix was taken when recording started. If the
phone started logging earlier or later than the camera, positions shift by that offset. A CSV can
avoid the guess by giving `t_s` (seconds from video start) directly.
"""

from __future__ import annotations

import csv
import io
import math
import xml.etree.ElementTree as ET
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime


class GpsParseError(ValueError):
    pass


@dataclass(frozen=True)
class Fix:
    t_s: float
    lat: float
    lon: float


MAX_POINTS = 200_000  # ~55 h at 1 Hz; protects the DB from a hostile or broken file


def parse_gps(data: bytes, filename: str) -> list[Fix]:
    name = filename.lower()
    if name.endswith(".gpx"):
        fixes = _parse_gpx(data)
    elif name.endswith(".csv"):
        fixes = _parse_csv(data)
    else:
        raise GpsParseError("GPS file must be .gpx or .csv")
    if len(fixes) < 2:
        raise GpsParseError("GPS file needs at least 2 points with time, latitude and longitude")
    if len(fixes) > MAX_POINTS:
        raise GpsParseError(f"GPS file has more than {MAX_POINTS} points")
    fixes.sort(key=lambda f: f.t_s)
    return fixes


def _check(lat: float, lon: float) -> None:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or math.isnan(lat) or math.isnan(lon):
        raise GpsParseError(f"coordinate out of range: {lat}, {lon}")


def _parse_time(raw: str) -> datetime:
    raw = raw.strip()
    try:
        return datetime.fromtimestamp(float(raw), tz=UTC)  # unix seconds
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as e:
        raise GpsParseError(f"unreadable timestamp: {raw!r}") from e
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _relative(points: list[tuple[datetime, float, float]]) -> list[Fix]:
    if not points:
        return []
    t0 = min(p[0] for p in points)
    return [Fix((t - t0).total_seconds(), lat, lon) for t, lat, lon in points]


def _parse_gpx(data: bytes) -> list[Fix]:
    # ElementTree does not fetch external entities; we also refuse DTDs outright (billion-laughs).
    if b"<!DOCTYPE" in data[:2048].upper() or b"<!ENTITY" in data.upper():
        raise GpsParseError("GPX files with a DOCTYPE are not accepted")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise GpsParseError(f"not valid GPX/XML: {e}") from e
    points: list[tuple[datetime, float, float]] = []
    for el in root.iter():
        if not el.tag.endswith("trkpt"):
            continue
        time_el = next((c for c in el if c.tag.endswith("time")), None)
        if time_el is None or not time_el.text:
            continue  # a point without time can't be aligned to the video
        try:
            lat, lon = float(el.attrib["lat"]), float(el.attrib["lon"])
        except (KeyError, ValueError) as e:
            raise GpsParseError("trkpt without numeric lat/lon") from e
        _check(lat, lon)
        points.append((_parse_time(time_el.text), lat, lon))
    return _relative(points)


def _parse_csv(data: bytes) -> list[Fix]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise GpsParseError("CSV must be UTF-8") from e
    reader = csv.DictReader(io.StringIO(text))
    cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
    lat_c = cols.get("lat") or cols.get("latitude")
    lon_c = cols.get("lon") or cols.get("lng") or cols.get("longitude")
    t_c, ts_c = cols.get("t_s"), cols.get("timestamp") or cols.get("time")
    if not lat_c or not lon_c or not (t_c or ts_c):
        raise GpsParseError("CSV needs columns lat, lon and either t_s (seconds from video start) or timestamp")
    rel: list[Fix] = []
    absolute: list[tuple[datetime, float, float]] = []
    for line_no, row in enumerate(reader, start=2):
        try:
            lat, lon = float(row[lat_c]), float(row[lon_c])
        except (TypeError, ValueError) as e:
            raise GpsParseError(f"line {line_no}: lat/lon must be numbers") from e
        _check(lat, lon)
        if t_c:
            try:
                t = float(row[t_c])
            except (TypeError, ValueError) as e:
                raise GpsParseError(f"line {line_no}: t_s must be a number") from e
            if t < 0 or math.isnan(t):
                raise GpsParseError(f"line {line_no}: t_s must be >= 0")
            rel.append(Fix(t, lat, lon))
        else:
            absolute.append((_parse_time(row[ts_c] or ""), lat, lon))  # type: ignore[index]
    return rel if t_c else _relative(absolute)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Fixes further apart than this are a gap (tunnel, phone sleeping), not a straight-line drive.
MAX_GAP_S = 30.0
# A jump implying more than this speed is GPS noise, not driving.
MAX_SPEED_MPS = 60.0


def track_distance_km(fixes: list[Fix]) -> float:
    total = 0.0
    for a, b in zip(fixes, fixes[1:], strict=False):
        dt = b.t_s - a.t_s
        if dt <= 0 or dt > MAX_GAP_S:
            continue
        d = haversine_m(a.lat, a.lon, b.lat, b.lon)
        if d / dt <= MAX_SPEED_MPS:
            total += d
    return total / 1000.0


class Track:
    """A sorted GPS track with cached times, so many lookups stay O(log n) each."""

    def __init__(self, fixes: list[Fix]) -> None:
        self.fixes = sorted(fixes, key=lambda f: f.t_s)
        self._times = [f.t_s for f in self.fixes]

    def position_at(self, t_s: float) -> tuple[float, float] | None:
        """Linear interpolation between the fixes around t_s. None outside the track or inside a gap."""
        fixes, i = self.fixes, bisect_left(self._times, t_s)
        if i < len(fixes) and fixes[i].t_s == t_s:
            return fixes[i].lat, fixes[i].lon
        if i == 0 or i == len(fixes):
            return None
        a, b = fixes[i - 1], fixes[i]
        if b.t_s - a.t_s > MAX_GAP_S:
            return None
        f = (t_s - a.t_s) / (b.t_s - a.t_s)
        return a.lat + f * (b.lat - a.lat), a.lon + f * (b.lon - a.lon)
