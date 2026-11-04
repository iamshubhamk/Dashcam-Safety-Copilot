import shutil
import subprocess

import pytest

from dashcam_perception.browser_video import ffmpeg_command, to_browser_h264


def test_command_targets_browser_h264(tmp_path):
    cmd = ffmpeg_command("ffmpeg", tmp_path / "a.mp4", tmp_path / "b.mp4")
    joined = " ".join(cmd)
    assert "-c:v libx264" in joined and "-pix_fmt yuv420p" in joined and "+faststart" in joined


def test_missing_ffmpeg_leaves_file_untouched(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"not a video")
    assert to_browser_h264(f, None) is False
    assert f.read_bytes() == b"not a video"


def test_failed_transcode_keeps_original(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    f = tmp_path / "x.mp4"
    f.write_bytes(b"not a video")
    assert to_browser_h264(f, shutil.which("ffmpeg")) is False
    assert f.read_bytes() == b"not a video"
    assert not (tmp_path / "x.h264.mp4").exists()


def test_transcodes_mp4v_to_h264(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg not installed")
    f = tmp_path / "x.mp4"
    w = cv2.VideoWriter(str(f), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    for i in range(10):
        w.write(np.full((48, 64, 3), i * 20, dtype=np.uint8))
    w.release()
    assert to_browser_h264(f, ffmpeg) is True
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(f)], capture_output=True, text=True).stderr
    assert "h264" in probe
