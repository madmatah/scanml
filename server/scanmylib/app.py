"""Application factory: wires the services into the HTTP API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .adapters.filesystem.library_files import FilesystemLibrary
from .adapters.filesystem.thumbnails import FilesystemThumbnails
from .adapters.filesystem.token_file import load_or_create_token
from .adapters.http_api.dependencies import HttpApiSettings, Services
from .adapters.http_api.fastapi_application import build_fastapi_application
from .adapters.http_api.preview import HtmlPreviews
from .adapters.ocr_sandbox.client import OcrClient
from .adapters.ocr_sandbox.engine import SandboxOcrEngine
from .adapters.pillow_images import PillowImages
from .adapters.sqlite.catalog import SqliteCatalog
from .adapters.sqlite.database import Database
from .adapters.sqlite.web_sessions import SqliteWebSessions
from .adapters.system_clock import SystemClock
from .application.access import Access
from .application.library import LibraryService
from .application.ocr_loop import OcrLoop
from .application.publisher import Publisher
from .config import Settings
from .version import __version__

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    http_api_settings = HttpApiSettings(
        public_url=settings.public_url,
        apk_path=settings.apk_path,
        web_directory=settings.web_dir,
        library_host_path=settings.library_host_path,
        version=__version__,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.db_path)
        catalog = SqliteCatalog(db)
        clock = SystemClock()
        images = PillowImages()
        files = FilesystemLibrary(settings.library_dir, clock)
        thumbnails = FilesystemThumbnails(settings.thumbs_dir)
        library = LibraryService(
            catalog,
            files,
            thumbnails,
            Publisher(files, clock),
            clock,
            images,
            assembly_delay_seconds=settings.assemble_delay_s,
        )
        access = Access(load_or_create_token(settings.token_path, settings.token), SqliteWebSessions(db), clock)
        ocr_client = OcrClient(settings.ocr_socket, settings.ocr_timeout_s)
        ocr_engine = SandboxOcrEngine(ocr_client)
        ocr_loop = OcrLoop(
            library, ocr_engine, images, max_side=settings.ocr_max_side, retry_max_s=settings.ocr_retry_max_s
        )
        library.add_work_listener(ocr_loop.notify)
        requeued = library.start()
        ocr_loop.start()
        app.state.services = Services(
            settings=http_api_settings, library=library, access=access, ocr=ocr_engine, previews=HtmlPreviews()
        )
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
            await ocr_client.aclose()
            db.close()

    return build_fastapi_application(lifespan, http_api_settings)
