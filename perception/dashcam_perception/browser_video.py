"""Make output videos playable in a browser.

OpenCV can portably write only MPEG-4 Part 2 ("mp4v"), which browsers don't play. Its H.264
("avc1") writer depends on an OpenH264 DLL being present on Windows, so we don't rely on it.
Instead we write mp4v and then, when ffmpeg is on PATH, transcode to H.264 with the index at
the front of the file (+faststart) so playback starts before the whole clip downloads.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffmpeg_command(ffmpeg: str, src: Path, dst: Path) -> list[str]:
    return [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",  # the only pixel format every browser decodes
        "-movflags", "+faststart",
        "-an",  # outputs carry no audio
        str(dst),
    ]  # fmt: skip


def to_browser_h264(path: Path, ffmpeg: str | None) -> bool:
    """Transcode `path` in place to H.264. Returns False (file left as mp4v) when ffmpeg is
    missing or fails, so a missing codec never loses the pipeline's results."""
    if ffmpeg is None or not path.exists():
        return False
    tmp = path.with_suffix(".h264.mp4")
    try:
        subprocess.run(ffmpeg_command(ffmpeg, path, tmp), check=True, capture_output=True, timeout=3600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    return True
