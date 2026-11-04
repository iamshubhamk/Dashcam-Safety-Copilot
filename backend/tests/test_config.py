from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_relative_paths_become_absolute(tmp_path, monkeypatch):
    # The worker hands paths to perception, which runs with cwd=REPO_ROOT. A relative path would
    # then resolve against the wrong folder ("video not found").
    monkeypatch.chdir(tmp_path)
    s = Settings(storage_dir=Path("../data/storage"), work_dir=Path("work"), risk_config=Path("risk.yaml"))
    assert s.storage_dir == (tmp_path / "../data/storage").resolve()
    assert s.work_dir.is_absolute() and s.risk_config.is_absolute()
