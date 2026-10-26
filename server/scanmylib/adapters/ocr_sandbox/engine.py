"""The OCR engine over the sandbox's protocol: a page's reading, timed, and the engine's status from its untrusted
/health."""

from __future__ import annotations

import asyncio
import math
import time

from ...application.ocr_engine import EngineStatus, GpuStatus, OcrUnavailable, PageReading
from ...domain.text import single_line
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

    async def read_status(self) -> EngineStatus:
        try:
            health = await self._client.health()
        except OcrUnavailable as exc:
            return EngineStatus(is_reachable=False, state="unreachable", backend=None, last_error=str(exc), gpu=None)
        engine_value = health.get("engine")
        engine = engine_value if isinstance(engine_value, dict) else {}
        return EngineStatus(
            is_reachable=True,
            state=_sandbox_text(engine.get("state"), 32),
            backend=_sandbox_text(engine.get("backend"), 32),
            last_error=_sandbox_text(engine.get("last_error"), 1000),
            gpu=_sandbox_gpu(health.get("gpu")),
        )


def _sandbox_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    return single_line(value.encode("utf-8", "replace").decode("utf-8"))[:limit] or None


def _sandbox_number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if math.isfinite(value) else None


def _sandbox_gpu(value: object) -> GpuStatus | None:
    if not isinstance(value, dict):
        return None
    return GpuStatus(
        name=_sandbox_text(value.get("name"), 128),
        memory_used_mebibytes=_sandbox_number(value.get("memory_used_mb")),
        memory_total_mebibytes=_sandbox_number(value.get("memory_total_mb")),
    )
