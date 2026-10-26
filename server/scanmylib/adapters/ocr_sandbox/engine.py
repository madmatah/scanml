"""The OCR engine over the sandbox's protocol: a page's reading, timed."""

from __future__ import annotations

import asyncio
import time

from ...application.ocr_engine import PageReading
from .client import OcrClient
from .results import build_page_output


class SandboxOcrEngine:
    def __init__(self, client: OcrClient) -> None:
        self._client = client

    async def warm_up(self) -> None:
        await self._client.load()

    async def read_page(
        self, page_image: bytes, *, page_id: str, page_key: str, should_unwarp: bool, should_detect_orientation: bool
    ) -> PageReading:
        started_seconds = time.monotonic()
        response = await self._client.parse(
            page_image, request_id=page_id, unwarp=should_unwarp, orientation=should_detect_orientation
        )
        elapsed_seconds = time.monotonic() - started_seconds
        output = await asyncio.to_thread(build_page_output, response, page_key)
        return PageReading(output, elapsed_seconds)
