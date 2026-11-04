from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app import cleanup
from app.db.models import Trip
from app.storage import LocalStorage


def test_cleanup_deletes_only_old_finished_originals(upload, worker, db, settings, storage, monkeypatch, capsys):
    old, new = upload(), upload()
    w = worker()
    w.run_once()
    w.run_once()
    db.execute(update(Trip).where(Trip.id == old["id"]).values(processed_at=datetime.now(UTC) - timedelta(days=40)))
    db.commit()
    monkeypatch.setattr(cleanup, "get_storage", lambda: LocalStorage(settings.storage_dir))
    monkeypatch.setattr(cleanup, "get_sessionmaker", lambda: w.sessions)

    assert cleanup.main(["--originals-older-than", "30d"]) == 0  # dry run
    assert storage.exists(f"trips/{old['id']}/source.mp4")
    assert "dry run" in capsys.readouterr().out

    cleanup.main(["--originals-older-than", "30d", "--yes"])
    db.expire_all()
    assert db.get(Trip, old["id"]).video_key is None
    assert not storage.exists(f"trips/{old['id']}/source.mp4")
    assert storage.exists(db.get(Trip, old["id"]).annotated_key)  # results kept
    assert db.get(Trip, new["id"]).video_key is not None
