"""The fake sandbox (devtools/fake_ocr.py) follows docs/OCR_SANDBOX.md."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image
from support import jpeg

from scanmylib.devtools.fake_ocr import canned_page, image_size


def encoded(fmt: str, size=(321, 123), **options) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA" if fmt == "PNG" else "RGB", size).save(buffer, fmt, **options)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "data",
    [
        jpeg(321, 123),
        encoded("JPEG", progressive=True),
        encoded("PNG"),
        encoded("WEBP", quality=80),
        encoded("WEBP", lossless=True),
        encoded("WEBP", exif=b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x00"),
    ],
)
def test_image_size_from_headers(data):
    assert image_size(data) == (321, 123)


def test_image_size_of_garbage():
    assert image_size(b"not an image") is None
    assert image_size(b"\xff\xd8\x00") is None


@pytest.mark.parametrize(
    ("size", "numbers"),
    [((1200, 1042), ["42"]), ((1201, 1042), ["42", "43"]), ((1202, 1012), ["xii"]),
     ((1203, 1042), []), ((1204, 1042), []), ((1200, 2000), [])],
)
def test_page_number_conventions(size, numbers):
    page = canned_page(*size, "r")
    assert page["page_numbers"] == numbers
    assert page["markdown"].count("imgs/") == 1


def test_protocol_over_the_unix_socket(fake_ocr):
    transport = httpx.HTTPTransport(uds=str(fake_ocr.socket_path))
    with httpx.Client(transport=transport, base_url="http://ocr") as sandbox:
        health = sandbox.get("/health").json()
        assert health["status"] == "ok" and health["engine"]["state"] == "idle"
        assert sandbox.post("/v1/load").json() == {"state": "starting"}
        parsed = sandbox.post("/v1/parse?request_id=abc", content=jpeg(1200, 1042), headers={"Content-Type": "image/jpeg"})
        assert parsed.status_code == 200 and parsed.json()["request_id"] == "abc"
        assert sandbox.get("/health").json()["processed"] == 1
        assert sandbox.post("/v1/parse", content=b"x", headers={"Content-Type": "image/gif"}).status_code == 415
        assert sandbox.post("/v1/parse", content=b"x", headers={"Content-Type": "image/jpeg"}).json()["error"] == "bad_image"
        assert sandbox.post("/v1/unload").json() == {"state": "idle"}
