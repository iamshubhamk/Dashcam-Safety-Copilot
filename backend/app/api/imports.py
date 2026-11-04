"""POST /trips/import: bring in results produced elsewhere (e.g. a Kaggle GPU notebook).

The zip holds a perception output folder: events.json, and optionally annotated.mp4, clips/ and
run_summary.json, either at the top level or inside one folder. It goes through the same
ingest code as a locally processed trip.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.deps import DbDep, RiskDep, SettingsDep, StorageDep
from app.api.errors import ApiError
from app.api.schemas import TripOut
from app.api.trips import load_trip_out, save_gps
from app.db.models import Trip, TripSource, TripStatus
from app.services.ingest import BadResults, ingest_results
from app.services.uploads import safe_filename
from app.storage import TooLarge

router = APIRouter(prefix="/trips", tags=["trips"])

_ALLOWED = re.compile(r"^(events\.json|run_summary\.json|annotated\.mp4|clips/event_\d{1,6}\.mp4)$")
MAX_MEMBERS = 10_000


def extract_results(zip_path: Path, dest: Path, max_total_bytes: int) -> None:
    """Extract only the files we know, refusing path tricks and zip bombs."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise ApiError(422, "bad_zip", "The file is not a valid zip.") from e
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_MEMBERS:
            raise ApiError(422, "bad_zip", "The zip has too many files.")
        names = [PurePosixPath(i.filename) for i in infos]
        # Accept "events.json" or "<one folder>/events.json".
        roots = {n.parts[0] for n in names if len(n.parts) > 1 and n.name == "events.json"}
        prefix = next(iter(roots)) if len(roots) == 1 and not any(n.as_posix() == "events.json" for n in names) else ""
        total = 0
        for info, name in zip(infos, names, strict=True):
            rel = name.as_posix()
            if prefix:
                if not rel.startswith(prefix + "/"):
                    continue
                rel = rel[len(prefix) + 1 :]
            if not _ALLOWED.fullmatch(rel):
                continue  # ignore anything else (notebook files, logs); the regex also rules out ../
            total += info.file_size
            if total > max_total_bytes:
                raise ApiError(413, "too_large", "The zip's contents are too large.")
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, out.open("wb") as dst:
                copied = 0
                while chunk := src.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > info.file_size:  # header lied about the size
                        raise ApiError(422, "bad_zip", "The zip is corrupt.")
                    dst.write(chunk)
    if not (dest / "events.json").is_file():
        raise ApiError(422, "bad_results", "The zip has no events.json.")


@router.post("/import", status_code=status.HTTP_201_CREATED, response_model=TripOut)
def import_results(
    db: DbDep,
    storage: StorageDep,
    settings: SettingsDep,
    risk: RiskDep,
    results: Annotated[UploadFile, File(description="Zip of a perception output folder")],
    gps: Annotated[UploadFile | None, File(description="Optional GPS track: .gpx or .csv")] = None,
    label: Annotated[str | None, Form(max_length=200)] = None,
) -> TripOut:
    """Create a finished trip from a results zip (no video processing happens here)."""
    trip = Trip(
        id=uuid.uuid4(),
        label=(label or "").strip() or None,
        source=TripSource.imported,
        status=TripStatus.processing,
        original_filename=safe_filename(results.filename),
    )
    tmp = Path(tempfile.mkdtemp(prefix="dashcam-import-", dir=_tmp_root(settings.work_dir)))
    try:
        zip_path = tmp / "results.zip"
        try:
            storage_size = _save_upload(results, zip_path, settings.max_import_bytes)
        except TooLarge as e:
            raise ApiError(413, "too_large", "The zip is too large.") from e
        if storage_size == 0:
            raise ApiError(422, "empty_file", "The zip is empty.")
        extract_results(zip_path, tmp / "out", settings.max_import_bytes)
        db.add(trip)
        db.flush()
        if gps is not None and gps.filename:
            save_gps(db, storage, trip, gps, settings.max_gps_bytes)
        try:
            ingest_results(db, storage, settings, risk, trip, tmp / "out")
        except BadResults as e:
            raise ApiError(422, "bad_results", str(e)) from e
        db.commit()
    except BaseException:
        db.rollback()
        storage.delete_prefix(f"trips/{trip.id}")
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return load_trip_out(db, trip.id)


def _tmp_root(work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def _save_upload(upload: UploadFile, dest: Path, max_bytes: int) -> int:
    written = 0
    with dest.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise TooLarge("too large")
            out.write(chunk)
    return written
