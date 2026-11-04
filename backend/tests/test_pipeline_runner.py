"""The real subprocess runner against the real perception CLI (no model needed for these paths)."""

from __future__ import annotations

import sys

import pytest

from app.worker.pipeline import PipelineError, SubprocessRunner


def test_command_includes_overrides(settings, tmp_path):
    settings.perception_weights, settings.perception_device = "weights/best.pt", "0"
    cmd = SubprocessRunner(settings).command(tmp_path / "v.mp4", tmp_path / "out")
    assert cmd[:3] == [sys.executable, "-m", "dashcam_perception.run"]
    assert cmd[-4:] == ["--weights", "weights/best.pt", "--device", "0"]


def test_unreadable_video_is_a_permanent_failure(settings, tmp_path):
    # perception exits 2 for a missing/unopenable video before it loads any model.
    with pytest.raises(PipelineError) as err:
        SubprocessRunner(settings).run(tmp_path / "missing.mp4", tmp_path / "out")
    assert err.value.permanent is True
    assert "video not found" in str(err.value)


def test_missing_interpreter_is_retryable(settings, tmp_path):
    settings.perception_python = str(tmp_path / "no-such-python")
    with pytest.raises(PipelineError) as err:
        SubprocessRunner(settings).run(tmp_path / "v.mp4", tmp_path / "out")
    assert err.value.permanent is False
