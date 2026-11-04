"""Test fixtures. Database tests run against a REAL Postgres (SKIP LOCKED, enums, partial unique
indexes and JSONB behave differently or don't exist in SQLite).

Start one with `docker compose up -d db` from the repo root, or point DASHCAM_TEST_DATABASE_URL
at any Postgres 16 where the user may create databases. The test database is rebuilt from the
Alembic migrations once per run, so the migrations are tested too.
"""

from __future__ import annotations

import io
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

TEST_DB_URL = os.environ.get(
    "DASHCAM_TEST_DATABASE_URL", "postgresql+psycopg://dashcam:dashcam@localhost:5432/dashcam_test"
)
os.environ["DASHCAM_DATABASE_URL"] = TEST_DB_URL  # before app modules read settings

from app.config import REPO_ROOT, Settings, get_settings  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.storage import LocalStorage, get_storage  # noqa: E402
from tests import factories  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def _ensure_database(url: str) -> None:
    u = make_url(url)
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            if not c.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": u.database}):
                c.execute(text(f'CREATE DATABASE "{u.database}"'))
    except Exception as e:  # pragma: no cover - environment problem, not a test failure
        pytest.exit(
            f"Postgres not reachable at {u.render_as_string(hide_password=True)}: {e}\n"
            "Start it with `docker compose up -d db` or set DASHCAM_TEST_DATABASE_URL.",
            returncode=3,
        )
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def engine():
    from alembic import command
    from alembic.config import Config

    _ensure_database(TEST_DB_URL)
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DB_URL
    eng = create_engine(TEST_DB_URL)
    with eng.begin() as c:  # start from nothing, then build the schema with the real migrations
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def sessions(engine) -> Iterator[sessionmaker[Session]]:
    with engine.begin() as c:
        tables = c.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version'")
        ).all()
        c.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    yield sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def db(sessions) -> Iterator[Session]:
    with sessions() as s:
        yield s


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=TEST_DB_URL,
        storage_dir=tmp_path / "storage",
        work_dir=tmp_path / "work",
        risk_config=REPO_ROOT / "configs" / "risk.yaml",
        poll_interval_s=0.01,
        heartbeat_interval_s=0.05,
    )


@pytest.fixture
def storage(settings: Settings) -> LocalStorage:
    return LocalStorage(settings.storage_dir)


@pytest.fixture
def client(sessions, settings, storage):
    from fastapi.testclient import TestClient

    app = create_app()

    def _db():
        with sessions() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c:
        yield c


@pytest.fixture
def upload(client):
    """Upload a small fake video; returns the trip JSON."""

    def _upload(label: str | None = None, gps: tuple[str, bytes] | None = None) -> dict:
        files = {"video": ("trip.mp4", io.BytesIO(factories.FAKE_MP4), "video/mp4")}
        if gps:
            files["gps"] = (gps[0], io.BytesIO(gps[1]), "application/octet-stream")
        r = client.post("/api/v1/trips", files=files, data={"label": label} if label else None)
        assert r.status_code == 201, r.text
        return r.json()

    return _upload


@pytest.fixture
def worker(settings, sessions, storage):
    from app.worker.main import Worker

    def _make(runner=None) -> Worker:
        return Worker(settings, sessions, storage, runner or factories.FakeRunner(), worker_id="test-worker")

    return _make


@pytest.fixture(autouse=True)
def _no_leftover_work(tmp_path: Path) -> Iterator[None]:
    yield
    shutil.rmtree(tmp_path / "work", ignore_errors=True)
