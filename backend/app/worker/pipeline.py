"""How the worker runs perception. A Protocol, so tests swap in a fake that needs no GPU or model."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Protocol

from app.config import REPO_ROOT, Settings


class PipelineError(Exception):
    def __init__(self, message: str, permanent: bool) -> None:
        super().__init__(message)
        # permanent = retrying can't help (unreadable video, bad config). Otherwise retry.
        self.permanent = permanent


class PipelineRunner(Protocol):
    def run(self, video: Path, out_dir: Path) -> None: ...


class SubprocessRunner:
    """Runs `python -m dashcam_perception.run` in its own process.

    Why a subprocess and not an import: PyTorch/CUDA can live in a different venv from the
    API, a GPU out-of-memory crash kills only the child, and GPU memory is fully released after
    every trip.
    """

    # dashcam_perception.run returns 2 for "can't open the video" and config errors.
    PERMANENT_EXIT_CODES = frozenset({2})

    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def command(self, video: Path, out_dir: Path) -> list[str]:
        cmd = [
            self.s.perception_python or sys.executable,
            "-m",
            "dashcam_perception.run",
            "--video",
            str(video),
            "--out",
            str(out_dir),
        ]
        if self.s.perception_weights:
            cmd += ["--weights", self.s.perception_weights]
        if self.s.perception_device:
            cmd += ["--device", self.s.perception_device]
        return cmd

    def run(self, video: Path, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        log = out_dir / "pipeline.log"
        try:
            with log.open("wb") as f:
                proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    self.command(video, out_dir),
                    cwd=REPO_ROOT,  # perception resolves its config paths from the repo root
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=self.s.perception_timeout_s,
                    check=False,
                )
        except subprocess.TimeoutExpired as e:
            raise PipelineError(
                f"perception timed out after {self.s.perception_timeout_s:.0f} s", permanent=True
            ) from e
        except OSError as e:
            raise PipelineError(f"could not start perception: {e}", permanent=False) from e
        if proc.returncode != 0:
            tail = log.read_text(encoding="utf-8", errors="replace")[-2000:]
            raise PipelineError(
                f"perception exited with code {proc.returncode}:\n{tail}",
                permanent=proc.returncode in self.PERMANENT_EXIT_CODES,
            )
