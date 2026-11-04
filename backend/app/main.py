"""FastAPI app. Run with: uvicorn app.main:app --reload  (from backend/)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api import errors, imports, misc, trips
from app.config import get_settings


class UploadSizeLimit:
    """Refuse oversized uploads from the Content-Length header, before the body is read to disk."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST":
            length = dict(scope["headers"]).get(b"content-length")
            if length and length.isdigit() and int(length) > self.max_bytes:
                body = b'{"code":"too_large","message":"Upload is too large."}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Dashcam Safety Copilot API",
        version="0.1.0",
        description="Upload dashcam videos, get risky moments, a driving score and a hazard map.",
    )
    errors.install(app)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"]
    )
    # Video + GPS + multipart overhead.
    app.add_middleware(
        UploadSizeLimit, max_bytes=max(s.max_upload_bytes, s.max_import_bytes) + s.max_gps_bytes + 1024**2
    )
    for r in (imports.router, trips.router, misc.router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
