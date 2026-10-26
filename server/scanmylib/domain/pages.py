"""A page's rules: its key, its OCR attempts and the summary of its OCR, the orientation the sandbox detects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import timestamps
from .records import OcrSummary

MAX_OCR_RETRIES = 3
_PAGE_ID_PREFIX_LENGTHS = (8, 12, 16, 32)


@dataclass(frozen=True)
class AttemptOutcome:
    status: str
    attempt_count: int
    error: str | None


def conclude_failed_attempt(previous_attempt_count: int, message: str, *, is_retryable: bool) -> AttemptOutcome:
    attempt_count = previous_attempt_count + 1
    if is_retryable and attempt_count <= MAX_OCR_RETRIES:
        return AttemptOutcome("queued", attempt_count, None)
    return AttemptOutcome("error", attempt_count, message)


def conclude_released_attempt(attempt_count: int) -> AttemptOutcome:
    return AttemptOutcome("queued", attempt_count, None)


def propose_page_keys(captured_at: datetime, page_id: str) -> tuple[str, ...]:
    hex_id = page_id.replace("-", "")
    return tuple(f"{timestamps.compact(captured_at)}_{hex_id[:length]}" for length in _PAGE_ID_PREFIX_LENGTHS)


def summarize_ocr(
    *, engine: str, markdown: str, image_count: int, duration_seconds: float, finished_at: datetime
) -> OcrSummary:
    return {
        "engine": engine.lower(),
        "model": engine,
        "duration_s": round(duration_seconds, 2),
        "at": timestamps.iso(finished_at),
        "images": image_count,
        "chars": len(markdown),
    }


def should_detect_orientation(rotation_degrees: int) -> bool:
    return rotation_degrees == 0
