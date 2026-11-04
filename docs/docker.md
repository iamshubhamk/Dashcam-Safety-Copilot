# Running the stack with Docker (Windows laptop)

Docker Compose runs three things: **Postgres**, the **API** (FastAPI), and the **dashboard**
(the built React app behind nginx). The **worker**, which runs the detector, runs outside Docker,
straight on Windows. That lets it use the NVIDIA GPU without setting up GPU passthrough.

```
browser ──► localhost:8080  frontend (nginx) ──/api──► api :8000 ──► db :5432
                                                          │             ▲
                                     ./data/storage ◄─────┘             │
                                           ▲                            │
                     worker (native Windows, GPU) ──────────────────────┘
```

The API and the worker work together through the database, which holds the job queue, and
through the `data/storage` folder, which holds videos and clips. Both must point at the same database and folder.

## One-time setup

1. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) and use
   the default WSL2 backend.
2. **Cap Docker's memory.** With 8 GB of RAM, WSL2 would otherwise take up to half of it.
   Create `%UserProfile%\.wslconfig` with:

   ```ini
   [wsl2]
   memory=3GB
   swap=2GB
   ```

   Then run `wsl --shutdown` in PowerShell and restart Docker Desktop. The stack itself is capped at
   about 1.4 GB: db 512 MB, API 768 MB, and frontend 128 MB.
3. Clone the repo **inside a normal Windows folder**, for example `C:\code\dashcam-safety-copilot`.

## Start and stop

From the repo root, in PowerShell:

```powershell
docker compose up -d --build     # first run takes a few minutes
docker compose ps                # db and api should be "healthy"
```

- Dashboard: http://localhost:8080
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/healthz. It reports `"worker": "never_seen"` until you
  start the worker below. That's expected.

```powershell
docker compose down              # stop, keep the database
docker compose down -v           # stop and wipe the database
```

Videos and clips live in `data\storage` in the repo, so they survive `down -v`. Delete that
folder if you want a completely clean start.

## Run the worker natively (uses the GPU)

Do this in a second PowerShell window. Set up the perception venv once, as described in
[perception/README.md](../perception/README.md), with PyTorch and CUDA. Then, from `backend\`:

```powershell
uv sync
$repo = (Resolve-Path ..).Path
$env:DASHCAM_DATABASE_URL = "postgresql+psycopg://dashcam:dashcam@localhost:5432/dashcam"
$env:DASHCAM_STORAGE_DIR  = "$repo\data\storage"      # same folder the API container mounts
$env:DASHCAM_WORK_DIR     = "$repo\data\work"
$env:DASHCAM_PERCEPTION_PYTHON = "$repo\perception\.venv\Scripts\python.exe"
$env:DASHCAM_PERCEPTION_DEVICE = "0"                   # first GPU
uv run python -m app.worker
```

Relative paths work too. They resolve against the folder you start the worker in, but the
full path makes it obvious that the worker and the API container share the same folder.

## Running the backend tests against the Compose database

```powershell
docker compose up -d db
cd backend
uv run pytest          # creates and rebuilds its own dashcam_test database
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `port is already allocated` on 5432 | Another Postgres is running. Stop it, or change the left side of `127.0.0.1:5432:5432`. |
| Upload fails with `413` | The file is over 2 GB, which is the API's limit. |
| `api` restarts, logs say it can't reach the db | Run `docker compose logs db`. Usually Docker ran out of memory, so raise `memory=` in `.wslconfig`. |
| Trip stuck on `queued` | The worker isn't running, or it points at a different database. |
