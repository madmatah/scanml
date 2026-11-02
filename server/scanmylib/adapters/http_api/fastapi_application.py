"""The FastAPI application of the HTTP API: its routes, its static files, its answers to errors and its middlewares.
It serves no generated documentation of the API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import Lifespan

from ..pillow_images import MAX_UPLOAD_BYTES
from . import documents, pages, system, web
from .dependencies import HttpApiSettings
from .error_answers import add_error_answers
from .middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware, body_limit

# Multipart overhead allowed on top of the 40 MiB file of an upload.
_UPLOAD_OVERHEAD_BYTES = 1024 * 1024
_JSON_BODY_LIMIT_BYTES = 1024 * 1024


def build_fastapi_application(lifespan: Lifespan[FastAPI], settings: HttpApiSettings) -> FastAPI:
    app = FastAPI(
        title="ScanMyLib",
        version=settings.version,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    add_error_answers(app)

    app.include_router(system.public)
    app.include_router(system.protected)
    app.include_router(documents.router)
    app.include_router(pages.router)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=settings.web_directory / "static", check_dir=False), name="static")

    # Added last = outermost: the 413 responses get the security headers too.
    app.add_middleware(
        BodySizeLimitMiddleware,
        limit_for=body_limit(MAX_UPLOAD_BYTES + _UPLOAD_OVERHEAD_BYTES, _JSON_BODY_LIMIT_BYTES),
    )
    app.add_middleware(SecurityHeadersMiddleware)
    return app
