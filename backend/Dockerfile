# API image: FastAPI + Alembic, with perception's *core* deps only (no PyTorch).
# Inference runs in the worker, which on Shubham's laptop runs natively on Windows
# to use the GPU. Build context is the repo root (see docker-compose.yml).
FROM python:3.11.14-slim-bookworm

RUN pip install --no-cache-dir uv==0.11.32

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Same layout as the repo, so app.config.REPO_ROOT (= /app) finds configs/ and perception/.
WORKDIR /app/backend

# Dependencies first (cached until a lockfile changes), from the lockfile, without dev extras.
COPY perception/pyproject.toml /app/perception/pyproject.toml
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN mkdir -p /app/perception/dashcam_perception && touch /app/perception/dashcam_perception/__init__.py \
    && uv sync --frozen --no-dev --no-install-project --no-install-package dashcam-perception

COPY configs /app/configs
COPY perception /app/perception
COPY backend /app/backend
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 app && mkdir -p /data/storage /data/work && chown -R app /data
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/api/v1/healthz', timeout=4)" || exit 1

# Migrate, then serve. One process: 8 GB of RAM doesn't leave room for several workers.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
