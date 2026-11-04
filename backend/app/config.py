"""Settings, read from environment variables (or backend/.env). One place, typed."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo root. Perception and configs/ resolve paths from here.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DASHCAM_", extra="ignore")

    database_url: str = "postgresql+psycopg://dashcam:dashcam@localhost:5432/dashcam"
    storage_dir: Path = REPO_ROOT / "data" / "storage"
    risk_config: Path = REPO_ROOT / "configs" / "risk.yaml"

    # Upload limits. 2 GB is roughly 30-40 min of 1080p phone video.
    max_upload_bytes: int = 2 * 1024**3
    max_gps_bytes: int = 20 * 1024**2
    max_import_bytes: int = 2 * 1024**3

    # Worker
    poll_interval_s: float = 2.0
    heartbeat_interval_s: float = 15.0
    stale_after_s: float = 300.0  # a running job with no heartbeat for this long is presumed dead
    max_attempts: int = 3
    # The pipeline runs as `<python> -m dashcam_perception.run` in a subprocess, so it can live in
    # its own venv with PyTorch/CUDA and a crash or GPU OOM can't take the worker down with it.
    perception_python: str | None = None  # None = the worker's own interpreter
    perception_weights: str | None = None  # e.g. weights/best.pt; None = perception config default
    perception_device: str | None = None  # "0" for the first GPU, "cpu"; None = auto
    perception_timeout_s: float = 6 * 3600
    work_dir: Path = REPO_ROOT / "data" / "work"

    # Browser origins allowed to call the API (the Vite dev server by default).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Pothole/obstacle sightings closer than this (same class) are treated as the same hazard.
    hazard_merge_radius_m: float = 15.0

    # A worker that hasn't sent a heartbeat for this long makes /healthz report "degraded".
    worker_heartbeat_max_age_s: float = 120.0

    @field_validator("storage_dir", "work_dir", "risk_config")
    @classmethod
    def _absolute(cls, v: Path) -> Path:
        # Relative paths are taken from the directory you start the API/worker in, and made absolute
        # here. Perception runs with cwd=REPO_ROOT, so a relative path handed to it would point
        # somewhere else ("video not found").
        return v.expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
