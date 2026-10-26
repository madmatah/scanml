"""Validation of a sandbox ``/v1/parse`` response (untrusted) into the files of a page.

Applies docs/SECURITY.md: bounded sizes, image names checked but never used on
disk (images become ``images/<key>_<n>.jpg``), images re-encoded, Markdown
sanitized; raw fields are type-checked and truncated before being stored in
``ocr/<key>.json``.
"""

from __future__ import annotations

import base64
import binascii
import logging
import math
import re
from dataclasses import dataclass
from typing import TypedDict

from ...application.scan_images import ImageRejected
from ..pillow_images import MAX_OCR_IMAGE_BYTES, reencode_ocr_image
from .sanitize import MarkdownTooLarge, is_safe_image_name, sanitize_markdown

log = logging.getLogger(__name__)

MAX_IMAGES = 64
MAX_BLOCKS = 4000
MAX_BLOCK_CONTENT = 64 * 1024
MAX_BLOCKS_TEXT = 2 * 1024 * 1024
"""Characters of block text kept per page (a dense page has ~10k): without it, 4000 blocks of
64 KiB would write ~256 MiB of ocr/<key>.json for a single page."""
MAX_NUMBER_STRINGS = 8
_MAX_BASE64_LENGTH = (MAX_OCR_IMAGE_BYTES + 2) // 3 * 4 + 1024
_SHORT_TEXT = re.compile(r"[^\x20-\x7e\u00a0-\u024f]")
_NOT_IDENTIFIER = re.compile(r"[^A-Za-z0-9 ._+-]")
_LEADING_NUMBER = re.compile(r"\s*([0-9]{1,4})\b")
_TRAILING_NUMBER = re.compile(r"\b([0-9]{1,4})\s*$")


class OcrResultError(ValueError):
    """The sandbox response is not acceptable."""


class _Block(TypedDict):
    label: str
    content: str
    bbox: list[float] | None
    order: int | None


class _ImageFile(TypedDict):
    name: str
    file: str


class _RejectedImage(TypedDict):
    name: str | None
    reason: str


class _Preprocessing(TypedDict):
    angle: float | None
    unwarped: bool


class RawOcrResult(TypedDict):
    key: str
    request_id: str | None
    width: int | None
    height: int | None
    engine: dict[str, str | None]
    timings: dict[str, float | None]
    preprocess: _Preprocessing | None
    page_continuation: dict[str, bool] | None
    page_numbers: list[str]
    images: list[_ImageFile]
    rejected_images: list[_RejectedImage]
    blocks: list[_Block]


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


def _valid_text(value: str) -> str:
    """The string with lone surrogates replaced: JSON can carry them, UTF-8 files cannot."""
    return value.encode("utf-8", "replace").decode("utf-8")


def _short_text(value: object, limit: int = 64) -> str | None:
    """A short printable string (engine names, labels...), or None."""
    if not isinstance(value, str):
        return None
    cleaned = _SHORT_TEXT.sub("", value).strip()[:limit]
    return cleaned or None


def _identifier(value: object, limit: int = 64) -> str | None:
    """An engine or model name, or None. It is written into document.md (front
    matter ``source``), where markup or a URL must not get through."""
    if not isinstance(value, str):
        return None
    cleaned = _NOT_IDENTIFIER.sub("", value).strip()[:limit]
    return cleaned or None


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _dimension(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 100_000 else None


def _blocks(value: object) -> list[_Block]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_BLOCKS:
        raise OcrResultError("invalid blocks")
    blocks: list[_Block] = []
    text_length = 0
    for item in value:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox")
        coordinates = [_finite_number(v) for v in bbox] if isinstance(bbox, list) and len(bbox) == 4 else []
        finite_coordinates = [coordinate for coordinate in coordinates if coordinate is not None]
        order = item.get("order")
        content = item.get("content")
        text = _valid_text(content[:MAX_BLOCK_CONTENT]) if isinstance(content, str) else ""
        text_length += len(text)
        if text_length > MAX_BLOCKS_TEXT:
            raise OcrResultError("blocks too large")
        blocks.append(
            {
                "label": _short_text(item.get("label")) or "unknown",
                "content": text,
                "bbox": [round(coordinate, 1) for coordinate in finite_coordinates]
                if len(finite_coordinates) == 4
                else None,
                "order": order if isinstance(order, int) and not isinstance(order, bool) else None,
            }
        )
    return blocks


def _page_number_strings(response: dict[str, object], blocks: list[_Block]) -> list[str]:
    """Contents of page-number blocks, falling back to numbers starting or ending a header/footer."""
    reported = response.get("page_numbers")
    if isinstance(reported, list):
        numbers = [_valid_text(v.strip()[:32]) for v in reported if isinstance(v, str) and v.strip()]
    else:
        numbers = [b["content"].strip()[:32] for b in blocks if b["label"] == "number" and b["content"].strip()]
    if not numbers:
        for block in blocks:
            if block["label"] in ("header", "footer"):
                text = block["content"].strip()[:200]
                match = _LEADING_NUMBER.match(text) or _TRAILING_NUMBER.search(text)
                if match:
                    numbers.append(match[1])
    return numbers[:MAX_NUMBER_STRINGS]


def _decode_images(value: object, key: str) -> tuple[list[OutputImage], dict[str, str], list[_RejectedImage]]:
    """Re-encode the illustrations; return them, the name → file mapping and the rejects."""
    if value is None:
        value = []
    if not isinstance(value, list):
        raise OcrResultError("invalid images")
    if len(value) > MAX_IMAGES:
        raise OcrResultError(f"more than {MAX_IMAGES} images")
    outputs: list[OutputImage] = []
    files: dict[str, str] = {}
    rejected: list[_RejectedImage] = []
    for item in value:
        name = item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not is_safe_image_name(name) or name in files:
            rejected.append({"name": _short_text(name, 128), "reason": "invalid or duplicate name"})
            continue
        payload = item.get("data_b64")
        try:
            if not isinstance(payload, str) or len(payload) > _MAX_BASE64_LENGTH:
                raise ImageRejected("missing or oversized data")
            data = base64.b64decode(payload, validate=True)
            jpeg = reencode_ocr_image(data)
        except (binascii.Error, ImageRejected) as exc:
            log.warning("page %s: illustration %s rejected: %s", key, name, exc)
            rejected.append({"name": name, "reason": str(exc)[:200]})
            continue
        filename = f"{key}_{len(outputs) + 1}.jpg"
        outputs.append(OutputImage(filename, jpeg))
        files[name] = filename
    return outputs, files, rejected


def build_page_output(response: object, key: str) -> PageOcrOutput:
    """Validate a parse response for the page `key` and prepare its files."""
    if not isinstance(response, dict):
        raise OcrResultError("response is not a JSON object")
    markdown = response.get("markdown")
    if not isinstance(markdown, str):
        raise OcrResultError("markdown missing")

    images, files, rejected = _decode_images(response.get("images"), key)

    def resolve(reference: str) -> str | None:
        name = reference.removeprefix("imgs/")
        if reference.startswith("imgs/") and name in files:
            return f"../images/{files[name]}"
        return None

    try:
        sanitized = sanitize_markdown(markdown, resolve)
    except MarkdownTooLarge as exc:
        raise OcrResultError(str(exc)) from exc

    blocks = _blocks(response.get("blocks"))
    numbers = _page_number_strings(response, blocks)
    engine_value = response.get("engine")
    engine_info = engine_value if isinstance(engine_value, dict) else {}
    engine = {k: _identifier(engine_info.get(k)) for k in ("name", "pipeline_version", "model", "backend")}
    timings_value = response.get("timings")
    timings_info = timings_value if isinstance(timings_value, dict) else {}
    timings = {k: _finite_number(timings_info.get(k)) for k in ("queue_s", "load_s", "infer_s")}
    continuation = response.get("page_continuation")
    preprocess = response.get("preprocess")

    raw: RawOcrResult = {
        "key": key,
        "request_id": _short_text(response.get("request_id"), 128),
        "width": _dimension(response.get("width")),
        "height": _dimension(response.get("height")),
        "engine": engine,
        "timings": timings,
        "preprocess": {
            "angle": _finite_number(preprocess.get("angle")),
            "unwarped": preprocess.get("unwarped") is True,
        }
        if isinstance(preprocess, dict)
        else None,
        "page_continuation": {
            name: continuation.get(name) is True for name in ("starts_mid_paragraph", "ends_mid_paragraph")
        }
        if isinstance(continuation, dict)
        else None,
        "page_numbers": numbers,
        "images": [{"name": name, "file": f"images/{filename}"} for name, filename in files.items()],
        "rejected_images": rejected,
        "blocks": blocks,
    }
    return PageOcrOutput(
        markdown=sanitized,
        images=tuple(images),
        detected_numbers=tuple(numbers),
        engine=engine["model"] or engine["name"] or "OCR",
        duration_s=timings["infer_s"],
        raw=raw,
    )
