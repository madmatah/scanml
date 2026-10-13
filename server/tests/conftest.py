"""Fixtures: a fake OCR sandbox on a real Unix socket and the app wired to it."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from support import TOKEN

from scanmylib.app import create_app
from scanmylib.config import Settings
from scanmylib.devtools.fake_ocr import FakeOcrServer


@pytest.fixture
def socket_dir():
    # Unix socket paths are limited to ~107 bytes: pytest's tmp_path can be longer.
    path = Path(tempfile.mkdtemp(prefix="sml-", dir="/tmp"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def fake_ocr(socket_dir):
    server = FakeOcrServer(socket_dir / "ocr.sock")
    server.start()
    yield server
    server.stop()


@pytest.fixture
def settings(tmp_path, socket_dir) -> Settings:
    return Settings(
        library_dir=tmp_path / "library",
        library_host_path="/home/user/Documents/ScanMyLib",
        state_dir=tmp_path / "state",
        ocr_socket=socket_dir / "ocr.sock",
        public_url="http://192.168.1.10:8765",
        apk_path=tmp_path / "app" / "scanmylib.apk",
        web_dir=tmp_path / "web",
        token=TOKEN,
        assemble_delay_s=0.05,
        ocr_retry_max_s=0.2,
    )


@pytest.fixture
def client(settings, fake_ocr):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def library_dir(settings) -> Path:
    return settings.library_dir
