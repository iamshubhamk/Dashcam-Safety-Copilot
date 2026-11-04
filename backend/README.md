# backend/

Phase 3. Upload a dashcam video and get back the risky moments with clips, an annotated video,
a 0–100 driving score with plain-language feedback, and a map of potholes and obstacles.

```
POST /trips ─► video on disk + row in `jobs` ─► worker claims it ─► perception (subprocess, GPU)
                                                                        │
dashboard ◄── REST API ◄── events, hazards, report (one transaction) ◄──┘ events.json + clips
```

FastAPI and PostgreSQL (SQLAlchemy and Alembic). The job queue is a Postgres table, so there's
no Redis or Celery. Files go through a small `Storage` interface: local disk today, S3 later.

## Run it

You need Python 3.11–3.13 and a Postgres 16. Any Postgres works; the shortest route is Docker:

```bash
docker run -d --name dashcam-db -p 5432:5432 -e POSTGRES_USER=dashcam -e POSTGRES_PASSWORD=dashcam \
  -e POSTGRES_DB=dashcam postgres:16
```

Then, from `backend/`:

```bash
uv sync --extra dev                 # or: pip install -e ../perception -e ".[dev]"
cp .env.example .env                # Windows: copy .env.example .env
uv run alembic upgrade head         # create the tables
uv run uvicorn app.main:app --reload --port 8000   # API at http://localhost:8000/docs
uv run python -m app.worker         # in a second terminal: processes queued trips
uv run pytest                       # 71 tests, needs the Postgres above
```

The worker runs perception as `python -m dashcam_perception.run` in a separate process. To use
your GPU, install `perception[run]` (PyTorch with CUDA) into a venv and set
`DASHCAM_PERCEPTION_PYTHON` to that venv's Python. Without CUDA it falls back to CPU, which is slow
but works. On Windows, run the worker natively rather than in Docker, so it can use the GPU without
setting up WSL2 GPU passthrough.

Upload from the command line:

```bash
curl -F video=@data/videos/trip1.mp4 -F gps=@data/videos/trip1.gpx -F label="Pune run" \
  http://localhost:8000/api/v1/trips
```

## API

Interactive docs are at `/docs`. The machine-readable spec is at `/openapi.json`. Errors always look
like `{"code": "...", "message": "..."}`.

| Method and path | Does |
| --- | --- |
| `POST /api/v1/trips` | Upload a video (multipart `video`, optional `gps`, optional `label`); returns the trip, `queued` |
| `GET /api/v1/trips` | Newest first, `{items, next_cursor}`; `?status=` filter |
| `GET /api/v1/trips/{id}` | Status, score, event count, error if it failed |
| `GET /api/v1/trips/{id}/report` | Score, breakdown, feedback lines, checks that didn't run (409 until done) |
| `GET /api/v1/trips/{id}/events` | Events in video order; `?type=`, `?severity=` |
| `GET /api/v1/trips/{id}/video?annotated=true` | Original or annotated video (HTTP Range, so players can seek) |
| `GET /api/v1/events/{id}/clip` | The clip around one event |
| `POST /api/v1/trips/{id}/retry` | Requeue a failed trip |
| `DELETE /api/v1/trips/{id}` | Trip, rows, files, and hazards nobody else saw |
| `POST /api/v1/trips/import` | A zip of perception output made elsewhere (e.g. Kaggle) becomes a finished trip |
| `GET /api/v1/hazards?bbox=w,s,e,n` | Hazards on the visible map, merged across trips |
| `GET /api/v1/healthz` | Database reachable, worker seen recently |

## The driving score

All the numbers are in [`configs/risk.yaml`](../configs/risk.yaml).

```
weight(event) = type_weight × severity_multiplier       e.g. critical forward collision = 3 × 3 = 9
R             = Σ weights / exposure                   exposure = 100 km of GPS track, else hours of video
score         = 100 × 0.5 ^ (R / r_half)               100 = nothing risky; 50 when R = r_half
```

- **Why a rate.** A three-hour highway drive shouldn't score worse than a ten-minute one just for
  being longer. Clips shorter than 15 minutes are scored as 15 minutes (`min_exposure_hours`), so
  one warning in a two-minute clip doesn't turn into 30 per hour.
- **Why `0.5 ^ (R / r_half)`.** It falls smoothly, never goes below zero, and `r_half` has a plain
  meaning: the risk rate that halves the score.
- **Checks that didn't run are not counted as clean.** With the stock COCO model, for example,
  obstacle-in-lane can't run. Tailgating and harsh braking need the vehicle's own speed. These show
  up under `not_checked` with a reason. They add nothing to R, and no "well done" line is ever
  written for them. If nothing at all was checked, the score is null.
- **The weights are judgment calls, not research.** `r_half` is **provisional** until it has been
  calibrated on real footage, and every report carries `provisional: true` until then. To calibrate:
  run a set of your own trips and pick `r_half` so a typical careful drive scores about 80. Then set
  `provisional: false` and bump `version`. Every report stores the version it was scored with.
- **Feedback lines come from rules, not an AI model.** Each line names the events behind it
  (`event_ids`), so every sentence can be traced to a clip.

## GPS files

GPS is optional. It places events and hazards on the map and gives the distance for per-100-km
scoring. Two formats are accepted:

- **GPX**, from most phone GPS-logger apps. Points need a `<time>`.
- **CSV** with `lat` and `lon` columns, plus either `t_s` (seconds from the start of the video) or
  `timestamp` (ISO 8601 or unix seconds).

With absolute timestamps there is no way to know exactly when the camera started, so the backend
**assumes the first GPS fix is the start of the video**. If logging started earlier or later than
recording, positions shift by that amount. Use `t_s` to avoid the guess. Reading GPS embedded inside
the video file isn't implemented yet.

## How the worker stays correct

- **Claiming.** `UPDATE jobs ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)`. Two workers can
  never take the same job, and a partial unique index allows only one live job per trip.
- **Retries.** A crash or out-of-memory error is retried up to 3 times, with backoff of 30 s, 60 s,
  then 120 s. A video perception can't open (exit code 2) or an invalid `events.json` fails straight
  away, because retrying won't help.
- **Dead workers.** Every running job sends a heartbeat every 15 s. A job whose heartbeat is more
  than 5 minutes old goes back to the queue.
- **Reprocessing is idempotent.** A trip's events, hazard sightings and report are replaced in one
  transaction, never appended.
- **Hazards.** A sighting within 15 m of an existing hazard of the same class joins that hazard.
  Counts are derived from the sightings, so deleting a trip can't leave a stale count behind.

## Housekeeping

```bash
uv run python -m app.cleanup --originals-older-than 30d         # list
uv run python -m app.cleanup --originals-older-than 30d --yes   # delete originals; clips + reports stay
```
