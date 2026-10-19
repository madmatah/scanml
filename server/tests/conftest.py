"""Fixtures: a fake OCR sandbox on a real Unix socket."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scanmylib.config import Settings
from scanmylib.devtools.fake_ocr import FakeOcrServer
from support import locate_socket, make_settings, serving_fake_ocr, temporary_socket_directory


@pytest.fixture
def socket_dir() -> Iterator[Path]:
    with temporary_socket_directory() as path:
        yield path


@pytest.fixture
def fake_ocr(socket_dir: Path) -> Iterator[FakeOcrServer]:
    with serving_fake_ocr(locate_socket(socket_dir)) as server:
        yield server


@pytest.fixture
def settings(tmp_path: Path, socket_dir: Path) -> Settings:
    return make_settings(tmp_path, socket_dir)
