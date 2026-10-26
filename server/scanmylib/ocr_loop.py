"""The single background OCR loop: queued pages → sandbox → library.

Behavior (docs/API.md): pages are processed FIFO by upload time; when the
sandbox is unavailable (no socket, 503) the page goes back to the queue
without counting a failure and the loop waits with exponential backoff;
processing errors (500) are retried at most MAX_OCR_RETRIES times; refused
pages (400/413/415) and invalid results fail immediately. New work wakes the
loop and pre-warms the engine with POST /v1/load.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from .application.scan_images import ImageRejected, OcrImages
from .domain.pages import should_detect_orientation
from .domain.records import PageClaim
from .library import LibraryService
from .ocr_client import OcrClient, OcrPageFailed, OcrPageRejected, OcrUnavailable
from .ocr_result import OcrResultError, build_page_output

log = logging.getLogger(__name__)

_RETRY_MIN_S = 2.0
_PREWARM_INTERVAL_S = 60.0


class OcrLoop:
    def __init__(
        self, library: LibraryService, client: OcrClient, ocr_images: OcrImages, *, max_side: int, retry_max_s: float
    ) -> None:
        self._library = library
        self._client = client
        self._ocr_images = ocr_images
        self._max_side = max_side
        self._retry_max_s = retry_max_s
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._prewarm_task: asyncio.Task[None] | None = None
        self._last_prewarm = float("-inf")
        self._busy = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="ocr-loop")

    async def aclose(self) -> None:
        for task in (self._task, self._prewarm_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def notify(self) -> None:
        """Pages were queued: wake the loop and pre-warm the engine."""
        self._wake.set()
        now = asyncio.get_running_loop().time()
        prewarming = self._prewarm_task is not None and not self._prewarm_task.done()
        if not self._busy and not prewarming and now - self._last_prewarm >= _PREWARM_INTERVAL_S:
            self._last_prewarm = now
            self._prewarm_task = asyncio.create_task(self._prewarm(), name="ocr-prewarm")

    async def _prewarm(self) -> None:
        try:
            await self._client.load()
        except OcrUnavailable as exc:
            log.info("OCR pre-warm skipped: %s", exc)

    async def _run(self) -> None:
        shortest = min(_RETRY_MIN_S, self._retry_max_s)
        delay = shortest
        while True:
            try:
                claim = self._library.claim_next_page()
                if claim is None:
                    # Nothing awaited since the claim: no notification can be lost here.
                    self._wake.clear()
                    await self._wake.wait()
                    continue
                available = await self._handle(claim)
            except Exception:
                log.exception("OCR loop error")
                await asyncio.sleep(shortest)
                continue
            if available:
                delay = shortest
            else:
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._retry_max_s)

    async def _handle(self, claim: PageClaim) -> bool:
        self._busy = True
        try:
            return await self._process(claim)
        except Exception as exc:
            log.exception("page %s: unexpected error", claim.key)
            self._library.fail_page(claim, f"Internal error: {exc}", retry=True)
            return True
        finally:
            self._busy = False

    async def _process(self, claim: PageClaim) -> bool:
        """OCR one page. Returns False when the sandbox is unavailable (page re-queued)."""
        scan = self._library.locate_claimed_scan(claim)
        try:
            image = await asyncio.to_thread(self._ocr_images.prepare_for_ocr, scan, claim.rotation, self._max_side)
        except (OSError, ImageRejected) as exc:
            self._library.fail_page(claim, f"Unreadable scan: {exc}", retry=False)
            return True

        started = time.monotonic()
        try:
            response = await self._client.parse(
                image,
                request_id=claim.page_id,
                unwarp=claim.unwarp,
                orientation=should_detect_orientation(claim.rotation),
            )
        except OcrUnavailable as exc:
            log.warning("OCR sandbox unavailable (%s); page %s stays queued", exc, claim.key)
            self._library.release_page(claim)
            return False
        except OcrPageRejected as exc:
            self._library.fail_page(claim, f"Image refused by the OCR: {exc}", retry=False)
            return True
        except OcrPageFailed as exc:
            retried = self._library.fail_page(claim, f"OCR failed: {exc}", retry=True)
            log.warning("page %s: OCR failed (%s)%s", claim.key, exc, ", will retry" if retried else "")
            return True
        elapsed = time.monotonic() - started

        try:
            output = await asyncio.to_thread(build_page_output, response, claim.key)
        except OcrResultError as exc:
            log.warning("page %s: invalid OCR result: %s", claim.key, exc)
            self._library.fail_page(claim, f"Invalid OCR result: {exc}", retry=False)
            return True
        if await self._library.complete_page(claim, output, output.duration_s or elapsed):
            log.info("page %s done in %.1f s (%d images)", claim.key, elapsed, len(output.images))
        else:
            log.info("page %s changed during OCR, result dropped", claim.key)
        return True
