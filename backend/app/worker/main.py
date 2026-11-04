"""The worker loop: claim a job, run perception, ingest the results, repeat.

One trip at a time: a 4 GB GPU fits one model, and a second concurrent trip would only make
both slower. Start a second worker process on another machine if you ever need more.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import socket
import threading
import time
import traceback
import uuid
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.models import Trip
from app.db.session import get_sessionmaker
from app.services.ingest import BadResults, ingest_results
from app.services.scoring import load_risk_config
from app.storage import Storage, get_storage
from app.worker import queue
from app.worker.pipeline import PipelineError, PipelineRunner, SubprocessRunner

log = logging.getLogger("dashcam.worker")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record), "level": record.levelname, "msg": record.getMessage()}
        out.update(getattr(record, "ctx", {}))
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


class Worker:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        storage: Storage,
        runner: PipelineRunner,
        worker_id: str | None = None,
    ) -> None:
        self.s = settings
        self.sessions = sessions
        self.storage = storage
        self.runner = runner
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.stop = threading.Event()
        self._last_alive = 0.0

    # -- loop ---------------------------------------------------------------------------------
    def run_forever(self) -> None:
        log.info("worker started", extra={"ctx": {"worker_id": self.worker_id}})
        with self.sessions() as db:
            n = queue.recover_stale(db, self.s.stale_after_s, self.s.max_attempts)
            if n:
                log.warning("requeued stale jobs", extra={"ctx": {"count": n}})
        while not self.stop.is_set():
            try:
                worked = self.run_once()
            except Exception:  # never let one bad trip or a DB blip kill the loop
                log.exception("worker loop error")
                worked = False
            if not worked:
                self.stop.wait(self.s.poll_interval_s)
        log.info("worker stopped")

    def run_once(self) -> bool:
        """Process at most one job. Returns True if a job was processed."""
        with self.sessions() as db:
            now = time.monotonic()
            if now - self._last_alive >= self.s.heartbeat_interval_s:
                queue.worker_alive(db, self.worker_id)
                queue.recover_stale(db, self.s.stale_after_s, self.s.max_attempts)
                self._last_alive = now
            claimed = queue.claim(db)
        if claimed is None:
            return False
        self.process(claimed)
        return True

    # -- one job ------------------------------------------------------------------------------
    def process(self, job: queue.Claimed) -> None:
        ctx = {"job_id": str(job.job_id), "trip_id": str(job.trip_id), "attempt": job.attempt}
        log.info("job started", extra={"ctx": ctx})
        out_dir = self.s.work_dir / str(job.job_id)
        stop_beat = threading.Event()
        beat = threading.Thread(target=self._heartbeat, args=(job.job_id, stop_beat), daemon=True)
        beat.start()
        t0 = time.monotonic()
        try:
            video = self._video_path(job.trip_id)
            if out_dir.exists():
                shutil.rmtree(out_dir)
            self.runner.run(video, out_dir)
            with self.sessions() as db:
                trip = db.get(Trip, job.trip_id, with_for_update=True)
                if trip is None:
                    log.info("trip deleted while processing", extra={"ctx": ctx})
                    return
                ingest_results(db, self.storage, self.s, load_risk_config(self.s.risk_config), trip, out_dir)
                queue.succeed(db, job.job_id)
                db.commit()
            log.info("job succeeded", extra={"ctx": {**ctx, "seconds": round(time.monotonic() - t0, 1)}})
        except PipelineError as e:
            self._fail(job, str(e), permanent=e.permanent, ctx=ctx)
        except (BadResults, FileNotFoundError) as e:
            self._fail(job, str(e), permanent=True, ctx=ctx)
        except Exception as e:
            self._fail(job, f"{type(e).__name__}: {e}\n{traceback.format_exc()}", permanent=False, ctx=ctx)
        finally:
            stop_beat.set()
            beat.join(timeout=5)
            shutil.rmtree(out_dir, ignore_errors=True)

    def _video_path(self, trip_id: uuid.UUID) -> Path:
        with self.sessions() as db:
            trip = db.get(Trip, trip_id)
            key = trip.video_key if trip else None
        if not key:
            raise FileNotFoundError("the trip's original video is no longer stored")
        path = self.storage.local_path(key)
        if path is None:  # remote storage: download a working copy
            path = self.s.work_dir / f"{trip_id}.video"
            with self.storage.open(key) as src, path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        if not path.is_file():
            raise FileNotFoundError(f"video file missing from storage: {key}")
        return path

    def _fail(self, job: queue.Claimed, error: str, *, permanent: bool, ctx: dict[str, object]) -> None:
        with self.sessions() as db:
            retry = queue.fail(db, job.job_id, error, permanent=permanent, max_attempts=self.s.max_attempts)
            db.commit()
        log.error("job failed", extra={"ctx": {**ctx, "retry": retry, "error": error[:500]}})

    def _heartbeat(self, job_id: uuid.UUID, stop: threading.Event) -> None:
        while not stop.wait(self.s.heartbeat_interval_s):
            try:
                with self.sessions() as db:
                    queue.heartbeat(db, job_id)
                    queue.worker_alive(db, self.worker_id)
            except Exception:
                log.exception("heartbeat failed")


def main() -> int:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    settings = get_settings()
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    worker = Worker(settings, get_sessionmaker(), get_storage(), SubprocessRunner(settings))
    signal.signal(signal.SIGINT, lambda *_: worker.stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: worker.stop.set())
    worker.run_forever()
    return 0
