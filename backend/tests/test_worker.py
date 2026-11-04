"""End to end through the worker with a fake pipeline: upload -> claim -> run -> ingest -> report."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import Event, Hazard, Job, JobStatus, Trip, TripReport, TripStatus
from app.worker.pipeline import PipelineError
from tests import factories

# One fix every 5 s for 10 minutes, driving north at about 11 m/s.
GPS_CSV = ("t_s,lat,lon\n" + "".join(f"{t},{19 + t * 1e-4:.6f},72.8\n" for t in range(0, 605, 5))).encode()


def test_happy_path(upload, worker, db, storage):
    trip = upload(label="Pune run", gps=("track.csv", GPS_CSV))
    w = worker()
    assert w.run_once() is True

    t = db.get(Trip, trip["id"])
    assert t.status == TripStatus.done and t.processed_at is not None
    events = db.scalars(select(Event).where(Event.trip_id == t.id).order_by(Event.peak_s)).all()
    assert [e.pipeline_event_id for e in events] == [1, 2]
    assert all(storage.exists(e.clip_key) for e in events)
    assert storage.exists(t.annotated_key)
    assert events[0].lat is not None  # positioned from the GPS sidecar at the event's peak time
    report = db.get(TripReport, t.id)
    assert report.score is not None and report.provisional
    assert report.breakdown["trip"]["gps"] == "ran"
    assert report.breakdown["trip"]["video_codec"] == "h264"
    assert all(n["type"] != "gps" for n in report.not_checked)
    assert db.scalar(select(func.count(Hazard.id))) == 1
    assert db.scalars(select(Job.status)).one() == JobStatus.succeeded
    assert not any(w.s.work_dir.glob("*"))  # scratch output cleaned up


def test_reprocessing_replaces_instead_of_duplicating(upload, worker, db, sessions):
    trip = upload(gps=("track.csv", GPS_CSV))
    w = worker()
    w.run_once()
    with sessions() as s:
        t = s.get(Trip, trip["id"])
        t.status = TripStatus.failed  # pretend it failed so it can be requeued
        s.commit()
    from app.worker import queue

    with sessions() as s:
        queue.enqueue(s, s.get(Trip, trip["id"]))
        s.commit()
    w.run_once()
    assert db.scalar(select(func.count(Event.id))) == 2
    assert db.scalar(select(func.count(Hazard.id))) == 1


def test_bad_video_fails_permanently(upload, worker, db):
    trip = upload()
    runner = factories.FakeRunner(error=PipelineError("OpenCV could not open the video", permanent=True))
    worker(runner).run_once()
    t = db.get(Trip, trip["id"])
    assert t.status == TripStatus.failed and "OpenCV" in t.error
    assert len(runner.calls) == 1


def test_crash_is_requeued(upload, worker, db):
    trip = upload()
    worker(factories.FakeRunner(error=PipelineError("CUDA out of memory", permanent=False))).run_once()
    assert db.get(Trip, trip["id"]).status == TripStatus.queued


def test_invalid_events_json_fails_permanently(upload, worker, db):
    trip = upload()

    class BrokenRunner(factories.FakeRunner):
        def run(self, video, out_dir):
            out_dir.mkdir(parents=True)
            (out_dir / "events.json").write_text('{"schema_version": "9.9"}')

    worker(BrokenRunner()).run_once()
    t = db.get(Trip, trip["id"])
    assert t.status == TripStatus.failed and "schema" in t.error


def test_trip_deleted_while_processing(upload, worker, client, db):
    trip = upload()

    class DeletingRunner(factories.FakeRunner):
        def run(self, video, out_dir):
            assert client.delete(f"/api/v1/trips/{trip['id']}").status_code == 204
            super().run(video, out_dir)

    worker(DeletingRunner()).run_once()  # must not raise or resurrect the trip
    assert db.get(Trip, trip["id"]) is None


def test_idle_worker_reports_itself_alive(worker, client):
    assert client.get("/api/v1/healthz").json()["worker"] == "never_seen"
    assert worker().run_once() is False
    body = client.get("/api/v1/healthz").json()
    assert body["worker"] == "ok" and body["status"] == "ok"
