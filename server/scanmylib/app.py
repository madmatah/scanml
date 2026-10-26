"""Application factory: wires the services, routes and middlewares."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .adapters.sqlite.database import Database
from .adapters.system_clock import SystemClock
from .api import documents, pages, system, web
from .api.deps import Services
from .application.scan_images import ImageRejected, ImageTooLarge
from .auth import Authenticator, load_or_create_token
from .config import Settings
from .domain.records import Conflict, InvalidRequest, NotFound
from .images import MAX_UPLOAD_BYTES, PillowImages
from .library import LibraryService
from .middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware, body_limit
from .ocr_client import OcrClient
from .ocr_loop import OcrLoop
from .storage import LibraryFiles

log = logging.getLogger(__name__)

# Multipart overhead allowed on top of the 40 MiB file of an upload.
_UPLOAD_OVERHEAD_BYTES = 1024 * 1024
_JSON_BODY_LIMIT_BYTES = 1024 * 1024

# Domain errors → HTTP status (FastAPI's {"detail": "..."} shape).
_ERROR_STATUS: dict[type[Exception], int] = {
    NotFound: 404,
    Conflict: 409,
    InvalidRequest: 422,
    ImageTooLarge: 413,
    ImageRejected: 415,
}


class _AsciiJSONResponse(JSONResponse):
    """JSON with non-ASCII characters escaped: lone surrogates cannot be encoded in UTF-8."""

    def render(self, content: object) -> bytes:
        return json.dumps(content, allow_nan=False, separators=(",", ":")).encode("ascii")


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    # FastAPI's default handler, without echoing the invalid input back: it may
    # be what JSON cannot carry (NaN, Infinity, a lone surrogate "\ud800"...),
    # which turned the 422 into a 500.
    assert isinstance(exc, RequestValidationError)
    errors = [{key: value for key, value in error.items() if key != "input"} for error in exc.errors()]
    return _AsciiJSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.db_path)
        clock = SystemClock()
        images = PillowImages()
        library = LibraryService(settings, db, LibraryFiles(settings.library_dir, clock), clock, images)
        auth = Authenticator(load_or_create_token(settings.token_path, settings.token), db, clock)
        ocr = OcrClient(settings.ocr_socket, settings.ocr_timeout_s)
        ocr_loop = OcrLoop(library, ocr, images, max_side=settings.ocr_max_side, retry_max_s=settings.ocr_retry_max_s)
        library.add_work_listener(ocr_loop.notify)
        requeued = library.start()
        ocr_loop.start()
        app.state.services = Services(settings=settings, library=library, auth=auth, ocr=ocr)
        log.info(
            "ScanMyLib %s: library %s, OCR socket %s, %d interrupted page(s) re-queued",
            __version__,
            settings.library_dir,
            settings.ocr_socket,
            requeued,
        )
        try:
            yield
        finally:
            await ocr_loop.aclose()
            await library.aclose()
            await ocr.aclose()
            db.close()

    app = FastAPI(
        title="ScanMyLib",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    async def domain_error(request: Request, exc: Exception) -> JSONResponse:
        status = next(code for kind, code in _ERROR_STATUS.items() if isinstance(exc, kind))
        return JSONResponse({"detail": str(exc)}, status_code=status)

    for kind in _ERROR_STATUS:
        app.add_exception_handler(kind, domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)

    app.include_router(system.public)
    app.include_router(system.protected)
    app.include_router(documents.router)
    app.include_router(pages.router)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=settings.web_dir / "static", check_dir=False), name="static")

    # Added last = outermost: the 413 responses get the security headers too.
    app.add_middleware(
        BodySizeLimitMiddleware,
        limit_for=body_limit(MAX_UPLOAD_BYTES + _UPLOAD_OVERHEAD_BYTES, _JSON_BODY_LIMIT_BYTES),
    )
    app.add_middleware(SecurityHeadersMiddleware)
    return app
