"""Helpers shared by the tests: images, uploads, the api on a fake OCR sandbox, waiting for the OCR loop."""

from __future__ import annotations

import io
import shutil
import struct
import tempfile
import time
import uuid
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
from fastapi.testclient import TestClient
from PIL import Image

from scanmylib.app import create_app
from scanmylib.config import Settings
from scanmylib.devtools.fake_ocr import FakeOcrServer

TOKEN = "test-token-0123456789abcdefghijklmnopqrstuvwxyz"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def new_id() -> str:
    return str(uuid.uuid4())


def jpeg(
    width: int = 1200,
    height: int = 1042,
    *,
    orientation: int | None = None,
    color: tuple[int, int, int] = (235, 232, 220),
) -> bytes:
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


def encoded(image: Image.Image, fmt: str, **options: object) -> bytes:
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


@dataclass(frozen=True)
class RunningApi:
    client: TestClient
    fake_ocr: FakeOcrServer
    settings: Settings


def locate_socket(socket_directory: Path) -> Path:
    return socket_directory / "ocr.sock"


def make_settings(directory: Path, socket_directory: Path, *, token: str | None = TOKEN) -> Settings:
    return Settings(
        library_dir=directory / "library",
        library_host_path="/home/user/Documents/ScanMyLib",
        state_dir=directory / "state",
        ocr_socket=locate_socket(socket_directory),
        public_url="http://192.168.1.10:8765",
        apk_path=directory / "app" / "scanmylib.apk",
        web_dir=directory / "web",
        token=token,
        assemble_delay_s=0.05,
        ocr_retry_max_s=0.2,
    )


@contextmanager
def temporary_socket_directory() -> Iterator[Path]:
    # Unix socket paths are limited to ~107 bytes: pytest's tmp_path can be longer.
    path = Path(tempfile.mkdtemp(prefix="sml-", dir="/tmp"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def serving_fake_ocr(socket_path: Path) -> Iterator[FakeOcrServer]:
    server = FakeOcrServer(socket_path)
    server.start()
    try:
        yield server
    finally:
        server.stop()


@contextmanager
def preparing_settings(directory: Path, *, token: str | None = TOKEN) -> Iterator[Settings]:
    with temporary_socket_directory() as socket_directory:
        yield make_settings(directory, socket_directory, token=token)


def build_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@contextmanager
def running_api(directory: Path) -> Iterator[RunningApi]:
    with (
        preparing_settings(directory) as settings,
        serving_fake_ocr(settings.ocr_socket) as fake_ocr,
        build_client(settings) as client,
    ):
        yield RunningApi(client, fake_ocr, settings)


def create_document(client: TestClient, title: str = "Sample Café Guide", **fields: object) -> str:
    document_id = new_id()
    client.put(f"/api/documents/{document_id}", json={"title": title, **fields}, headers=AUTH).raise_for_status()
    return document_id


def upload(
    client: TestClient,
    document_id: str,
    image: bytes,
    *,
    page_id: str | None = None,
    session_id: str | None = None,
    seq: int | None = None,
    captured_at: str | None = None,
    hint: int | None = None,
    headers: dict[str, str] | None = None,
) -> httpx2.Response:
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


def wait_for[Outcome](
    condition: Callable[[], Outcome | None], timeout_seconds: float = 20.0, interval_seconds: float = 0.05
) -> Outcome:
    deadline = time.monotonic() + timeout_seconds
    while True:
        outcome = condition()
        if outcome:
            return outcome
        if time.monotonic() > deadline:
            raise TimeoutError(f"condition not met in {timeout_seconds} seconds")
        time.sleep(interval_seconds)


def read_until[Reading](
    read: Callable[[], Reading],
    is_reached: Callable[[Reading], bool],
    timeout_seconds: float = 20.0,
    interval_seconds: float = 0.05,
) -> Reading:
    # The last reading comes back on a timeout too, so that the test, which reads it, is the one that fails.
    deadline = time.monotonic() + timeout_seconds
    reading = read()
    while not is_reached(reading) and time.monotonic() < deadline:
        time.sleep(interval_seconds)
        reading = read()
    return reading


def wait_until_processed(client: TestClient, document_id: str, timeout_seconds: float = 20.0) -> dict[str, Any]:
    """Wait until no page of the document is queued or processing; return the document."""

    def settled() -> dict[str, Any] | None:
        document: dict[str, Any] = client.get(f"/api/documents/{document_id}", headers=AUTH).json()
        stats = document["stats"]
        return document if stats["queued"] == 0 and stats["processing"] == 0 else None

    return wait_for(settled, timeout_seconds)


@dataclass(frozen=True)
class Answer:
    status: int
    body: Any


def capture_answer(response: httpx2.Response) -> Answer:
    return Answer(response.status_code, response.json())
