"""Helpers shared by the tests: images, uploads, waiting for the OCR loop."""

from __future__ import annotations

import io
import struct
import time
import uuid
import zlib
from collections.abc import Callable
from typing import Any

from PIL import Image

TOKEN = "test-token-0123456789abcdefghijklmnopqrstuvwxyz"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def new_id() -> str:
    return str(uuid.uuid4())


def jpeg(width: int = 1200, height: int = 1042, *, orientation: int | None = None, color=(235, 232, 220)) -> bytes:
    """A JPEG; with the fake OCR, its height mod 1000 is the page number (see fake_ocr)."""
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    if orientation is None:
        image.save(buffer, "JPEG", quality=85)
    else:
        exif = Image.Exif()
        exif[0x0112] = orientation
        image.save(buffer, "JPEG", quality=85, exif=exif.tobytes())
    return buffer.getvalue()


def png(width: int, height: int, mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height)).save(buffer, "PNG")
    return buffer.getvalue()


def encoded(image: Image.Image, fmt: str, **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 48, 8, 2, 0, 0, 0))
_PNG_PIXELS = zlib.compress(b"".join(b"\x00" + b"\x80" * (64 * 3) for _ in range(48)))

#: Corrupt PNGs that Pillow reports with assorted exception types.
CORRUPT_PNGS = {
    # IHDR shorter than 13 bytes (ValueError when opened).
    "truncated-header": b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", b"\x00\x00\x00\x10"),
    # Pixel data that is not a zlib stream (OSError while decoding).
    "corrupt-pixels": _PNG_HEADER + _png_chunk(b"IDAT", b"not a zlib stream") + _png_chunk(b"IEND", b""),
    # Pixel data continued in a chunk with an invalid type (SyntaxError while decoding).
    "invalid-chunk": _PNG_HEADER
    + _png_chunk(b"IDAT", _PNG_PIXELS[:10])
    + b"\x00\x00\x00\x08\x00\x01\x02\x03"
    + _PNG_PIXELS[10:],
}
#: An EXIF block that is not TIFF data: Pillow raises when it is read.
BROKEN_EXIF = b"Exif\x00\x00GARBAGE, NOT TIFF"


def mpo(width: int, height: int) -> bytes:
    """A multi-picture JPEG (phone photo with a depth map or an HDR gain map)."""
    return encoded(
        Image.new("RGB", (width, height), (235, 232, 220)),
        "MPO",
        save_all=True,
        append_images=[Image.new("RGB", (width // 4, height // 4))],
    )


def page_image(number: int, variant: int = 0) -> bytes:
    """Scan that the fake OCR reads as page `number` (variant: see fake_ocr)."""
    return jpeg(1200 + variant, 1000 + number)


def create_document(client, title: str = "Sample Café Guide", **fields: Any) -> str:
    document_id = new_id()
    response = client.put(f"/api/documents/{document_id}", json={"title": title, **fields}, headers=AUTH)
    assert response.status_code == 201, response.text
    return document_id


def upload(
    client,
    document_id: str,
    image: bytes,
    *,
    page_id: str | None = None,
    session_id: str | None = None,
    seq: int | None = None,
    captured_at: str | None = None,
    hint: int | None = None,
    headers: dict | None = None,
):
    data = {"page_id": page_id or new_id()}
    if session_id is not None:
        data["session_id"] = session_id
    if seq is not None:
        data["seq"] = str(seq)
    if captured_at is not None:
        data["captured_at"] = captured_at
    if hint is not None:
        data["page_number_hint"] = str(hint)
    return client.post(
        f"/api/documents/{document_id}/pages",
        files={"file": ("scan.jpg", image, "image/jpeg")},
        data=data,
        headers=AUTH if headers is None else headers,
    )


def wait_for(condition: Callable[[], Any], timeout: float = 20.0, interval: float = 0.05) -> Any:
    """Poll until `condition()` is truthy; return its value."""
    deadline = time.monotonic() + timeout
    while True:
        value = condition()
        if value:
            return value
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(interval)


def wait_until_processed(client, document_id: str, timeout: float = 20.0) -> dict:
    """Wait until no page of the document is queued or processing; return the document."""

    def settled():
        document = client.get(f"/api/documents/{document_id}", headers=AUTH).json()
        stats = document["stats"]
        return document if stats["queued"] == 0 and stats["processing"] == 0 else None

    return wait_for(settled, timeout)
