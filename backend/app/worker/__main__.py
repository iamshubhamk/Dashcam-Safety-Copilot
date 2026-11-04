"""python -m app.worker  -- process queued trips, one at a time, until Ctrl+C."""

from app.worker.main import main

raise SystemExit(main())
