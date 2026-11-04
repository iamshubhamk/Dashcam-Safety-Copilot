"""File storage behind a small interface, so S3 can replace local disk without touching callers.

Keys are relative, forward-slash paths such as ``trips/<id>/source.mp4``. The database stores
keys only, never absolute paths, so the storage folder can move.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, Protocol

_KEY = re.compile(r"^[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-.]+)*$")


class StorageError(Exception):
    pass


def check_key(key: str) -> str:
    """Reject anything that could escape the storage root (.., absolute paths, backslashes)."""
    if not _KEY.fullmatch(key) or any(part in {".", ".."} for part in key.split("/")):
        raise StorageError(f"invalid storage key: {key!r}")
    return key


class Storage(Protocol):
    def put_file(self, key: str, src: Path) -> int: ...
    def put_stream(self, key: str, stream: BinaryIO, max_bytes: int) -> int: ...
    def open(self, key: str) -> BinaryIO: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def local_path(self, key: str) -> Path | None:
        """A filesystem path if the backend has one (lets the API serve with range support)."""
        ...


class TooLarge(StorageError):
    pass


class LocalStorage:
    CHUNK = 1024 * 1024

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / check_key(key)

    def put_file(self, key: str, src: Path) -> int:
        dst = self._path(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        shutil.copyfile(src, tmp)
        tmp.replace(dst)  # atomic on the same filesystem: readers never see half a file
        return dst.stat().st_size

    def put_stream(self, key: str, stream: BinaryIO, max_bytes: int) -> int:
        dst = self._path(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".part")
        written = 0
        try:
            with tmp.open("wb") as out:
                for chunk in _chunks(stream, self.CHUNK):
                    written += len(chunk)
                    if written > max_bytes:
                        raise TooLarge(f"file is larger than {max_bytes} bytes")
                    out.write(chunk)
            tmp.replace(dst)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return written

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        shutil.rmtree(self._path(prefix.rstrip("/")), ignore_errors=True)

    def local_path(self, key: str) -> Path | None:
        return self._path(key)


def _chunks(stream: BinaryIO, size: int) -> Iterator[bytes]:
    while chunk := stream.read(size):
        yield chunk


def get_storage() -> Storage:
    from app.config import get_settings

    return LocalStorage(get_settings().storage_dir)
