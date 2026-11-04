"""The Postgres job queue: claim order, SKIP LOCKED, retries, stale recovery."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.db.models import Job, JobStatus, Trip, TripStatus
from app.worker import queue


def make_trip(db, n: int = 1) -> list[Trip]:
    trips = []
    for i in range(n):
        t = Trip(label=f"t{i}", video_key=f"trips/x{i}/source.mp4")
        db.add(t)
        db.flush()
        queue.enqueue(db, t)
        db.commit()  # separate commits so created_at orders them
        trips.append(t)
    return trips


def test_claim_takes_oldest_and_marks_trip_processing(db):
    a, b = make_trip(db, 2)
    c = queue.claim(db)
    assert c is not None and c.trip_id == a.id and c.attempt == 1
    db.refresh(a)
    assert a.status == TripStatus.processing
    assert queue.claim(db).trip_id == b.id
    assert queue.claim(db) is None


def test_skip_locked_lets_a_second_worker_take_the_next_job(db, sessions):
    a, b = make_trip(db, 2)
    with sessions() as other:
        # Another worker is mid-claim on the oldest job: it holds the row lock.
        other.execute(select(Job).where(Job.trip_id == a.id).with_for_update())
        with sessions() as me:
            me.execute(text("SET lock_timeout = '2s'"))  # would raise instead of hanging if SKIP LOCKED broke
            c = queue.claim(me)
        assert c is not None and c.trip_id == b.id
        other.rollback()


def test_only_one_live_job_per_trip(db):
    (t,) = make_trip(db)
    queue.enqueue(db, t)
    with pytest.raises(IntegrityError):
        db.commit()


def test_transient_failure_is_retried_with_backoff(db):
    (t,) = make_trip(db)
    c = queue.claim(db)
    assert queue.fail(db, c.job_id, "GPU busy", permanent=False, max_attempts=3) is True
    db.commit()
    job = db.get(Job, c.job_id)
    db.refresh(job)
    db.refresh(t)
    assert job.status == JobStatus.queued and t.status == TripStatus.queued
    assert queue.claim(db) is None  # backoff: not runnable yet
    db.execute(update(Job).values(run_after=func.now() - timedelta(seconds=1)))
    db.commit()
    assert queue.claim(db).attempt == 2


def test_gives_up_after_max_attempts(db):
    (t,) = make_trip(db)
    for _ in range(3):
        c = queue.claim(db)
        queue.fail(db, c.job_id, "boom\ndetails", permanent=False, max_attempts=3)
        db.execute(update(Job).values(run_after=func.now() - timedelta(seconds=1)))
        db.commit()
    db.refresh(t)
    assert t.status == TripStatus.failed and t.error == "boom: details"  # first + last line, for the UI
    assert db.get(Job, c.job_id).status == JobStatus.failed


def test_permanent_failure_is_not_retried(db):
    (t,) = make_trip(db)
    c = queue.claim(db)
    assert queue.fail(db, c.job_id, "can't open video", permanent=True, max_attempts=3) is False
    db.commit()
    db.refresh(t)
    assert t.status == TripStatus.failed


def test_stale_running_job_is_requeued(db):
    (t,) = make_trip(db)
    c = queue.claim(db)
    db.execute(update(Job).values(heartbeat_at=func.now() - timedelta(minutes=10)))
    db.commit()
    assert queue.recover_stale(db, stale_after_s=300, max_attempts=3) == 1
    job = db.get(Job, c.job_id)
    db.refresh(job)
    assert job.status == JobStatus.queued and "heartbeat" in job.error


def test_fresh_running_job_is_left_alone(db):
    make_trip(db)
    queue.claim(db)
    assert queue.recover_stale(db, stale_after_s=300, max_attempts=3) == 0


def test_heartbeat_reports_lost_ownership(db):
    make_trip(db)
    c = queue.claim(db)
    assert queue.heartbeat(db, c.job_id) is True
    db.execute(update(Job).values(status=JobStatus.queued))
    db.commit()
    assert queue.heartbeat(db, c.job_id) is False
