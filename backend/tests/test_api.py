"""HTTP endpoints: uploads, listing, report, events, media with Range, retry, delete, import, hazards."""

from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import Hazard, Trip, TripStatus
from tests import factories
from tests.test_worker import GPS_CSV

API = "/api/v1"


def test_upload_queues_a_trip(upload, client):
    trip = upload(label="  Mumbai to Pune  ")
    assert trip["status"] == "queued" and trip["label"] == "Mumbai to Pune"
    assert trip["has_original_video"] and not trip["has_gps"] and trip["score"] is None
    assert client.get(f"{API}/trips/{trip['id']}").json()["id"] == trip["id"]


def test_upload_with_gps_stores_points_and_distance(upload):
    trip = upload(gps=("track.csv", GPS_CSV))
    assert trip["has_gps"] and trip["distance_km"] == pytest.approx(6.7, abs=0.1)


@pytest.mark.parametrize(
    ("name", "data"),
    [("notes.txt", b"hello world, not a video"), ("trip.mp4", b"definitely not an mp4 file")],
)
def test_non_video_is_refused(client, name, data):
    r = client.post(f"{API}/trips", files={"video": (name, io.BytesIO(data))})
    assert r.status_code == 415 and r.json()["code"] == "unsupported_media"


def test_oversized_upload_is_refused_and_leaves_nothing_behind(client, settings, storage, db):
    settings.max_upload_bytes = 1024
    r = client.post(f"{API}/trips", files={"video": ("t.mp4", io.BytesIO(factories.FAKE_MP4))})
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert db.scalar(select(func.count(Trip.id))) == 0
    assert not any(storage.root.rglob("*.mp4"))


def test_bad_gps_file_is_refused_and_rolls_back(client, db, storage):
    r = client.post(
        f"{API}/trips",
        files={"video": ("t.mp4", io.BytesIO(factories.FAKE_MP4)), "gps": ("g.csv", io.BytesIO(b"x,y\n1,2\n"))},
    )
    assert r.status_code == 422 and r.json()["code"] == "bad_gps"
    assert db.scalar(select(func.count(Trip.id))) == 0
    assert not any(storage.root.rglob("source.mp4"))


def test_validation_errors_use_the_common_shape(client):
    r = client.post(f"{API}/trips")
    assert r.status_code == 422 and r.json()["code"] == "validation_error" and "video" in r.json()["message"]


def test_list_is_newest_first_and_paginates(upload, client):
    ids = [upload(label=f"t{i}")["id"] for i in range(5)]
    page1 = client.get(f"{API}/trips", params={"limit": 2}).json()
    page2 = client.get(f"{API}/trips", params={"limit": 2, "cursor": page1["next_cursor"]}).json()
    page3 = client.get(f"{API}/trips", params={"limit": 2, "cursor": page2["next_cursor"]}).json()
    got = [t["id"] for p in (page1, page2, page3) for t in p["items"]]
    assert got == ids[::-1] and page3["next_cursor"] is None


def test_bad_cursor_is_a_400(client):
    r = client.get(f"{API}/trips", params={"cursor": "nonsense"})
    assert r.status_code == 400 and r.json()["code"] == "bad_cursor"


def test_unknown_trip_is_404(client):
    r = client.get(f"{API}/trips/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json() == {"code": "not_found", "message": "trip not found"}


def test_report_events_and_media_after_processing(upload, worker, client):
    trip = upload()
    assert client.get(f"{API}/trips/{trip['id']}/report").status_code == 409
    worker().run_once()

    t = client.get(f"{API}/trips/{trip['id']}").json()
    assert t["status"] == "done" and t["event_count"] == 2 and t["score"] is not None
    report = client.get(f"{API}/trips/{trip['id']}/report").json()
    assert report["provisional"] is True and report["exposure_unit"] == "per_hour"
    assert {"type": "gps", "status": "skipped_no_gps"}.items() <= report["not_checked"][-1].items()
    assert {"objects_seen", "ttc_below_warning_s", "ttc_below_critical_s"} <= report["breakdown"]["trip"].keys()
    assert {f["kind"] for f in report["feedback"]} >= {"issue", "worst_moments"}

    events = client.get(f"{API}/trips/{trip['id']}/events").json()["items"]
    assert [e["type"] for e in events] == ["forward_collision", "obstacle_in_lane"]
    only_crit = client.get(f"{API}/trips/{trip['id']}/events", params={"severity": "critical"}).json()["items"]
    assert len(only_crit) == 1

    clip = client.get(f"{API}/events/{events[0]['id']}/clip", headers={"Range": "bytes=0-9"})
    assert clip.status_code == 206 and clip.content == factories.FAKE_CLIP[:10]
    video = client.get(f"{API}/trips/{trip['id']}/video", params={"annotated": True})
    assert video.status_code == 200 and video.headers["accept-ranges"] == "bytes"


def test_events_paginate_in_video_order(upload, worker, client):
    doc = factories.document([factories.event(i, peak=float(10 * i)) for i in range(1, 8)])
    trip = upload()
    worker(factories.FakeRunner(doc)).run_once()
    seen, cursor = [], None
    while True:
        page = client.get(f"{API}/trips/{trip['id']}/events", params={"limit": 3, "cursor": cursor}).json()
        seen += [e["peak_s"] for e in page["items"]]
        if not (cursor := page["next_cursor"]):
            break
    assert seen == [10.0 * i for i in range(1, 8)]


def test_retry_only_failed_trips(upload, worker, client):
    from app.worker.pipeline import PipelineError

    trip = upload()
    assert client.post(f"{API}/trips/{trip['id']}/retry").json()["code"] == "not_failed"
    worker(factories.FakeRunner(error=PipelineError("bad", permanent=True))).run_once()
    r = client.post(f"{API}/trips/{trip['id']}/retry")
    assert r.status_code == 200 and r.json()["status"] == "queued" and r.json()["error"] is None
    worker().run_once()
    assert client.get(f"{API}/trips/{trip['id']}").json()["status"] == "done"


def test_delete_removes_rows_files_and_orphan_hazards(upload, worker, client, db, storage):
    trip = upload(gps=("track.csv", GPS_CSV))
    worker().run_once()
    assert db.scalar(select(func.count(Hazard.id))) == 1
    assert client.delete(f"{API}/trips/{trip['id']}").status_code == 204
    assert db.get(Trip, trip["id"]) is None
    assert db.scalar(select(func.count(Hazard.id))) == 0
    assert not (storage.root / "trips" / trip["id"]).exists()
    assert client.delete(f"{API}/trips/{trip['id']}").status_code == 404


def bbox_around(lat: float, lon: float, d: float = 0.01) -> str:
    return f"{lon - d},{lat - d},{lon + d},{lat + d}"


def test_hazards_merge_across_trips_within_15_m(upload, worker, client):
    base = (19.0, 72.8)
    near = (19.0 + 10 / 111_195, 72.8)  # 10 m north: same pothole
    far = (19.0 + 40 / 111_195, 72.8)  # 40 m north: a different one
    for gps in (base, near, far):
        doc = factories.document(hazards=[factories.hazard(1, gps=gps)])
        upload()
        worker(factories.FakeRunner(doc)).run_once()
    body = client.get(f"{API}/hazards", params={"bbox": bbox_around(*base)}).json()
    counts = sorted(h["seen_count"] for h in body["items"])
    assert counts == [1, 2] and body["truncated"] is False
    merged = next(h for h in body["items"] if h["seen_count"] == 2)
    assert merged["trip_count"] == 2 and merged["lat"] == pytest.approx(base[0])  # keeps the first position


def test_different_classes_do_not_merge(upload, worker, client):
    for cls in ("pothole", "barricade"):
        upload()
        worker(
            factories.FakeRunner(factories.document(hazards=[factories.hazard(1, cls, gps=(19.0, 72.8))]))
        ).run_once()
    assert len(client.get(f"{API}/hazards", params={"bbox": bbox_around(19.0, 72.8)}).json()["items"]) == 2


def test_hazards_outside_bbox_are_not_returned(upload, worker, client):
    upload()
    worker(factories.FakeRunner(factories.document(hazards=[factories.hazard(1, gps=(19.0, 72.8))]))).run_once()
    assert client.get(f"{API}/hazards", params={"bbox": bbox_around(28.6, 77.2)}).json()["items"] == []
    assert client.get(f"{API}/hazards", params={"bbox": "1,2,3"}).json()["code"] == "bad_bbox"


def test_import_results_zip(client, tmp_path, db, storage):
    doc = factories.document([factories.event(1, severity="critical")], [factories.hazard(3, gps=(19.0, 72.8))])
    z = factories.results_zip(tmp_path / "out.zip", doc, folder="kaggle_out", extra={"../../evil.txt": b"x"})
    r = client.post(f"{API}/trips/import", files={"results": ("out.zip", z.open("rb"))}, data={"label": "Kaggle"})
    assert r.status_code == 201, r.text
    trip = r.json()
    assert trip["status"] == "done" and trip["source"] == "imported" and trip["event_count"] == 1
    assert not trip["has_original_video"] and trip["has_annotated_video"]
    assert not any(p.name == "evil.txt" for p in tmp_path.parent.rglob("evil.txt"))
    assert client.get(f"{API}/trips/{trip['id']}/report").status_code == 200


def test_import_without_events_json_is_refused(client, tmp_path, db):
    import zipfile

    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("annotated.mp4", b"x")
    r = client.post(f"{API}/trips/import", files={"results": ("bad.zip", z.open("rb"))})
    assert r.status_code == 422 and r.json()["code"] == "bad_results"
    assert db.scalar(select(func.count(Trip.id))) == 0


def test_import_with_wrong_schema_is_refused(client, tmp_path, db):
    import zipfile

    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("events.json", '{"schema_version": "2.0"}')
    r = client.post(f"{API}/trips/import", files={"results": ("bad.zip", z.open("rb"))})
    assert r.status_code == 422 and "schema" in r.json()["message"]
    assert db.scalar(select(func.count(Trip.id))) == 0


def test_not_a_zip(client):
    r = client.post(f"{API}/trips/import", files={"results": ("x.zip", io.BytesIO(b"not a zip"))})
    assert r.status_code == 422 and r.json()["code"] == "bad_zip"


def test_trip_status_filter(upload, client, db):
    a, b = upload(), upload()
    db.get(Trip, a["id"]).status = TripStatus.failed
    db.commit()
    items = client.get(f"{API}/trips", params={"status": "failed"}).json()["items"]
    assert [t["id"] for t in items] == [a["id"]]
    assert b["id"] not in [t["id"] for t in items]
