from __future__ import annotations

import pytest

from app.services.gps import Fix, GpsParseError, Track, haversine_m, parse_gps, track_distance_km

GPX = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
 <trk><trkseg>
  <trkpt lat="19.0760" lon="72.8777"><time>2026-11-03T10:00:00Z</time></trkpt>
  <trkpt lat="19.0770" lon="72.8777"><time>2026-11-03T10:00:05Z</time></trkpt>
  <trkpt lat="19.0780" lon="72.8777"><time>2026-11-03T10:00:10Z</time></trkpt>
 </trkseg></trk>
</gpx>"""


def test_gpx_times_become_seconds_from_first_fix():
    fixes = parse_gps(GPX, "ride.GPX")
    assert [f.t_s for f in fixes] == [0, 5, 10]
    assert fixes[1].lat == pytest.approx(19.077)


def test_gpx_with_doctype_is_refused():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><gpx>&a;</gpx>'
    with pytest.raises(GpsParseError, match="DOCTYPE"):
        parse_gps(evil, "x.gpx")


def test_csv_with_seconds_from_video_start():
    fixes = parse_gps(b"t_s,lat,lon\n3,19.0,72.0\n1,19.1,72.1\n", "t.csv")
    assert [f.t_s for f in fixes] == [1, 3]  # sorted


def test_csv_with_timestamps_and_alternative_column_names():
    data = b"Timestamp,Latitude,Longitude\n2026-11-03T10:00:10+05:30,19.0,72.0\n2026-11-03T10:00:00+05:30,19.1,72.1\n"
    fixes = parse_gps(data, "t.csv")
    assert [f.t_s for f in fixes] == [0, 10]


def test_csv_with_unix_timestamps():
    fixes = parse_gps(b"timestamp,lat,lon\n1700000000,19,72\n1700000002.5,19,72\n", "t.csv")
    assert fixes[-1].t_s == 2.5


@pytest.mark.parametrize(
    ("data", "name", "match"),
    [
        (b"a,b\n1,2\n", "t.csv", "columns"),
        (b"t_s,lat,lon\n0,91,72\n1,19,72\n", "t.csv", "out of range"),
        (b"t_s,lat,lon\n0,19,72\n", "t.csv", "at least 2"),
        (b"t_s,lat,lon\nx,19,72\n1,19,72\n", "t.csv", "t_s"),
        (b"whatever", "t.kml", ".gpx or .csv"),
        (b"<gpx", "t.gpx", "not valid"),
    ],
)
def test_bad_files_explain_what_is_wrong(data, name, match):
    with pytest.raises(GpsParseError, match=match):
        parse_gps(data, name)


def test_distance_skips_gaps_and_teleports():
    north_100m = 100 / 111_195
    fixes = [
        Fix(0, 19.0, 72.0),
        Fix(10, 19.0 + north_100m, 72.0),  # 100 m in 10 s: counted
        Fix(100, 19.0 + 2 * north_100m, 72.0),  # after a 90 s gap: not counted
        Fix(101, 20.0, 72.0),  # 100 km in 1 s: GPS noise, not counted
    ]
    assert track_distance_km(fixes) == pytest.approx(0.1, rel=1e-3)


def test_position_is_interpolated_and_none_outside_the_track():
    track = Track([Fix(0, 19.0, 72.0), Fix(10, 19.1, 72.2)])
    lat, lon = track.position_at(5)
    assert (lat, lon) == (pytest.approx(19.05), pytest.approx(72.1))
    assert track.position_at(-1) is None and track.position_at(11) is None
    assert track.position_at(10) == (19.1, 72.2)


def test_no_position_inside_a_gap():
    assert Track([Fix(0, 19, 72), Fix(120, 19.1, 72)]).position_at(60) is None


def test_haversine_one_degree_latitude():
    assert haversine_m(0, 0, 1, 0) == pytest.approx(111_195, rel=1e-3)
