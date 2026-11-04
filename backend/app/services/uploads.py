"""Checks on uploaded files that don't need the database."""

from __future__ import annotations

from pathlib import PurePath

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def video_extension(filename: str | None) -> str | None:
    ext = PurePath(filename or "").suffix.lower()
    return ext if ext in VIDEO_EXTENSIONS else None


def looks_like_video(head: bytes) -> bool:
    """Check the container signature, not just the file name, so a renamed .txt is refused at
    upload time instead of failing minutes later in the worker."""
    return (
        head[4:8] == b"ftyp"  # MP4 / MOV / M4V
        or head[:4] == b"\x1aE\xdf\xa3"  # Matroska / WebM
        or (head[:4] == b"RIFF" and head[8:12] == b"AVI ")  # AVI
        or head[4:8] in {b"moov", b"mdat", b"wide", b"free"}  # older QuickTime layouts
    )


def safe_filename(name: str | None) -> str | None:
    if not name:
        return None
    return PurePath(name.replace("\\", "/")).name[:255] or None
