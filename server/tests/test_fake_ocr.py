"""The fake sandbox (devtools/fake_ocr.py) follows docs/OCR_SANDBOX.md."""

from __future__ import annotations

import io
import socket
import sys

import httpx
import pytest
from PIL import Image
from support import jpeg

from scanmylib.devtools.fake_ocr import FakeOcrServer, canned_page, check_health, image_size
from scanmylib.devtools.fake_ocr import main as fake_ocr_main


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
    [
        ((1200, 1042), ["42"]),
        ((1201, 1042), ["42", "43"]),
        ((1202, 1012), ["xii"]),
        ((1203, 1042), []),
        ((1204, 1042), []),
        ((1200, 2000), []),
    ],
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
        parsed = sandbox.post(
            "/v1/parse?request_id=abc", content=jpeg(1200, 1042), headers={"Content-Type": "image/jpeg"}
        )
        assert parsed.status_code == 200 and parsed.json()["request_id"] == "abc"
        assert sandbox.get("/health").json()["processed"] == 1
        assert sandbox.post("/v1/parse", content=b"x", headers={"Content-Type": "image/gif"}).status_code == 415
        assert (
            sandbox.post("/v1/parse", content=b"x", headers={"Content-Type": "image/jpeg"}).json()["error"]
            == "bad_image"
        )
        assert sandbox.post("/v1/unload").json() == {"state": "idle"}


def test_health_probe(fake_ocr, socket_dir):
    assert check_health(fake_ocr.socket_path)
    assert not check_health(socket_dir / "missing.sock")
    fake_ocr.stop()
    assert not check_health(fake_ocr.socket_path)


def test_never_replaces_a_socket_that_answers(fake_ocr):
    intruder = FakeOcrServer(fake_ocr.socket_path)
    with pytest.raises(RuntimeError, match="served by another process"):
        intruder.start()
    intruder.stop()  # leaves the socket it did not create
    assert check_health(fake_ocr.socket_path)


def test_replaces_a_stale_socket(socket_dir):
    path = socket_dir / "ocr.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
        stale.bind(str(path))  # the file stays after close, with nobody listening
    server = FakeOcrServer(path)
    server.start()
    try:
        assert check_health(path)
    finally:
        server.stop()
    assert not path.exists()


def test_never_replaces_a_file_that_is_not_a_socket(socket_dir):
    path = socket_dir / "ocr.sock"
    path.write_text("not a socket")
    with pytest.raises(RuntimeError, match="not a socket"):
        FakeOcrServer(path).start()
    assert path.read_text() == "not a socket"


def run_command_line(monkeypatch, socket_path, project):
    monkeypatch.setenv("SCANMYLIB_PROJECT", project)
    monkeypatch.setattr(sys, "argv", ["fake_ocr", "--socket", str(socket_path)])
    with pytest.raises(SystemExit) as exit_info:
        fake_ocr_main()
    return exit_info.value.code


def test_never_runs_in_the_production_stack(monkeypatch, socket_dir):
    assert run_command_line(monkeypatch, socket_dir / "ocr.sock", "scanmylib") == 1
    assert not (socket_dir / "ocr.sock").exists()


def test_command_line_leaves_a_sandbox_that_answers(monkeypatch, fake_ocr):
    assert run_command_line(monkeypatch, fake_ocr.socket_path, "scanmylib-dev") == 1
    assert check_health(fake_ocr.socket_path)
