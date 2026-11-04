"""Delete original videos older than N days, keeping clips, annotated videos and reports.

    python -m app.cleanup --originals-older-than 30d            # show what would be deleted
    python -m app.cleanup --originals-older-than 30d --yes      # actually delete

Only finished trips are touched. A trip whose original is gone can't be reprocessed.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.models import Trip, TripStatus
from app.db.session import get_sessionmaker
from app.storage import get_storage


def parse_age(value: str) -> timedelta:
    m = re.fullmatch(r"(\d+)d", value.strip())
    if not m:
        raise argparse.ArgumentTypeError("use a number of days, e.g. 30d")
    return timedelta(days=int(m.group(1)))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--originals-older-than", type=parse_age, required=True, metavar="Nd")
    p.add_argument("--yes", action="store_true", help="delete (without it, only list)")
    args = p.parse_args(argv)

    cutoff = datetime.now(UTC) - args.originals_older_than
    storage = get_storage()
    with get_sessionmaker()() as db:
        trips = db.scalars(
            select(Trip)
            .where(Trip.status == TripStatus.done, Trip.video_key.is_not(None), Trip.processed_at < cutoff)
            .order_by(Trip.processed_at)
        ).all()
        total = sum(t.video_bytes or 0 for t in trips)
        for t in trips:
            print(f"{'deleting' if args.yes else 'would delete'} {t.video_key} ({(t.video_bytes or 0) / 1e6:.0f} MB)")
            if args.yes and t.video_key is not None:
                key, t.video_key = t.video_key, None
                db.commit()  # forget the key first: a crash leaves an orphan file, never a dangling key
                storage.delete(key)
        print(f"{len(trips)} original video(s), {total / 1e9:.2f} GB{'' if args.yes else ' (dry run; add --yes)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
