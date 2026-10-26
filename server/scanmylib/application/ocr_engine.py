"""A page image is a JPEG. A page's output is already validated and sanitized, and its illustrations are JPEGs named
after the page's key. A reading's elapsed time runs from the request to the engine's answer. A status relays only typed
and bounded fields of the engine's own report, and an engine that does not answer is "unreachable", with the reason as
its last error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict


class OcrUnavailable(Exception):
    """The engine cannot take work right now (unreachable, failed to start...)."""


class OcrPageFailed(Exception):
    """The engine failed on this page; it may succeed on a retry."""


class OcrPageRejected(Exception):
    """The engine refuses this page (bad image, too large...); retrying is pointless."""


class OcrResultError(ValueError):
    """The engine's result is not acceptable."""


class Block(TypedDict):
    label: str
    content: str
    bbox: list[float] | None
    order: int | None


class ImageFile(TypedDict):
    name: str
    file: str


class RejectedImage(TypedDict):
    name: str | None
    reason: str


class Preprocessing(TypedDict):
    angle: float | None
    unwarped: bool


class RawOcrResult(TypedDict):
    key: str
    request_id: str | None
    width: int | None
    height: int | None
    engine: dict[str, str | None]
    timings: dict[str, float | None]
    preprocess: Preprocessing | None
    page_continuation: dict[str, bool] | None
    page_numbers: list[str]
    images: list[ImageFile]
    rejected_images: list[RejectedImage]
    blocks: list[Block]


@dataclass(frozen=True)
class OutputImage:
    filename: str  # "<key>_<n>.jpg", stored under images/
    data: bytes


@dataclass(frozen=True)
class PageOcrOutput:
    """Everything to write for one page, already validated and sanitized."""

    markdown: str  # image references: ../images/<key>_<n>.jpg
    images: tuple[OutputImage, ...]
    detected_numbers: tuple[str, ...]
    engine: str  # e.g. "PaddleOCR-VL-1.6"
    duration_s: float | None
    raw: RawOcrResult  # content of ocr/<key>.json


@dataclass(frozen=True)
class PageReading:
    output: PageOcrOutput
    elapsed_seconds: float


@dataclass(frozen=True)
class GpuStatus:
    name: str | None
    memory_used_mebibytes: int | float | None
    memory_total_mebibytes: int | float | None


@dataclass(frozen=True)
class EngineStatus:
    is_reachable: bool
    state: str | None
    backend: str | None
    last_error: str | None
    gpu: GpuStatus | None


class OcrEngine(Protocol):
    async def warm_up(self) -> None: ...

    async def read_page(
        self, page_image: bytes, *, page_id: str, page_key: str, should_unwarp: bool, should_detect_orientation: bool
    ) -> PageReading: ...


class OcrEngineMonitor(Protocol):
    async def read_status(self) -> EngineStatus: ...
