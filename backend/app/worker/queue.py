"""The Postgres job queue: enqueue, claim, heartbeat, finish, recover.

Claiming uses `SELECT ... FOR UPDATE SKIP LOCKED`: the row lock stops two workers taking the same
job, and SKIP LOCKED makes a second worker move on to the next job instead of waiting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus, Trip, TripStatus, WorkerHeartbeat


@dataclass(frozen=True)
class Claimed:
    job_id: uuid.UUID
    trip_id: uuid.UUID
    attempt: int


def enqueue(db: Session, trip: Trip) -> Job:
    job = Job(trip_id=trip.id)
    db.add(job)
    trip.status = TripStatus.queued
    return job


def claim(db: Session) -> Claimed | None:
    """Take the oldest runnable job. Commits, so the claim is visible to other workers at once."""
    next_id = (
        select(Job.id)
        .where(Job.status == JobStatus.queued, Job.run_after <= func.now())
        .order_by(Job.run_after, Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    row = db.execute(
        update(Job)
        .where(Job.id == next_id)
        .values(status=JobStatus.running, attempts=Job.attempts + 1, locked_at=func.now(), heartbeat_at=func.now())
        .returning(Job.id, Job.trip_id, Job.attempts)
    ).first()
    if row is None:
        db.rollback()
        return None
    db.execute(update(Trip).where(Trip.id == row.trip_id).values(status=TripStatus.processing, error=None))
    db.commit()
    return Claimed(row.id, row.trip_id, row.attempts)


def heartbeat(db: Session, job_id: uuid.UUID) -> bool:
    """Returns False if the job is no longer ours (recovered as stale, or its trip was deleted)."""
    row = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.running)
        .values(heartbeat_at=func.now())
        .returning(Job.id)
    ).first()
    db.commit()
    return row is not None


def succeed(db: Session, job_id: uuid.UUID) -> None:
    db.execute(
        update(Job).where(Job.id == job_id).values(status=JobStatus.succeeded, finished_at=func.now(), error=None)
    )


def fail(db: Session, job_id: uuid.UUID, error: str, *, permanent: bool, max_attempts: int) -> bool:
    """Record a failure. Returns True if the job will be retried. The caller commits."""
    job = db.get(Job, job_id, with_for_update=True)
    if job is None:  # trip deleted meanwhile (cascade)
        return False
    retry = not permanent and job.attempts < max_attempts
    job.error = error[-4000:]
    if retry:
        job.status = JobStatus.queued
        # Back off 30 s, 60 s, 120 s ... so a flapping problem (disk full, GPU busy) gets time to clear.
        job.run_after = func.now() + timedelta(seconds=30 * 2 ** (job.attempts - 1))
        job.locked_at = None
    else:
        job.status = JobStatus.failed
        job.finished_at = func.now()
    trip = db.get(Trip, job.trip_id)
    if trip is not None:
        trip.status = TripStatus.queued if retry else TripStatus.failed
        trip.error = None if retry else _user_error(error)
    return retry


def _user_error(error: str) -> str:
    """Short message for the UI: the first line, plus the last line when there is a log tail
    (that's where Python puts the actual exception, e.g. "No module named 'cv2'")."""
    lines = [ln.strip() for ln in error.strip().splitlines() if ln.strip()]
    if not lines:
        return "processing failed"
    msg = lines[0] if len(lines) == 1 else f"{lines[0].rstrip(':')}: {lines[-1]}"
    return msg[:500]


def recover_stale(db: Session, stale_after_s: float, max_attempts: int) -> int:
    """Jobs left `running` by a worker that died (no heartbeat for stale_after_s) go back to the
    queue, or fail if they already used all attempts. Returns how many were recovered."""
    cutoff = func.now() - timedelta(seconds=stale_after_s)
    stale = db.scalars(
        select(Job).where(Job.status == JobStatus.running, Job.heartbeat_at < cutoff).with_for_update(skip_locked=True)
    ).all()
    for job in stale:
        fail(db, job.id, "worker stopped responding (no heartbeat)", permanent=False, max_attempts=max_attempts)
    db.commit()
    return len(stale)


def worker_alive(db: Session, worker_id: str) -> None:
    stmt = pg_insert(WorkerHeartbeat).values(worker_id=worker_id)
    db.execute(stmt.on_conflict_do_update(index_elements=["worker_id"], set_={"last_seen_at": func.now()}))
    db.commit()


def latest_worker_age_s(db: Session) -> float | None:
    """Seconds since any worker last showed life, for /healthz. None = no worker has ever run."""
    age = db.scalar(select(func.extract("epoch", func.now() - func.max(WorkerHeartbeat.last_seen_at))))
    return float(age) if age is not None else None
