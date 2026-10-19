"""The client of the OCR sandbox (scanmylib/ocr_client.py), against the fake sandbox on a real Unix socket."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from scanmylib.devtools.fake_ocr import FakeOcrServer
from scanmylib.ocr_client import OcrClient, OcrUnavailable


class TestTheOcrClient:
    class TestTheLoadMethod:
        class TestWhenTheSandboxAnswersWithAnOversizedBody:
            PARSE_TIMEOUT_SECONDS = 10
            #: Larger than the 64 KiB that the client reads of a /v1/load answer.
            OVERSIZED_ANSWER = b"x" * (1024 * 1024)

            @pytest.fixture
            def load(self, fake_ocr: FakeOcrServer) -> Callable[[], Coroutine[Any, Any, None]]:
                fake_ocr.status_body = self.OVERSIZED_ANSWER

                async def load_through_a_new_client() -> None:
                    sandbox = OcrClient(fake_ocr.socket_path, self.PARSE_TIMEOUT_SECONDS)
                    try:
                        await sandbox.load()
                    finally:
                        await sandbox.aclose()

                return load_through_a_new_client

            def test_should_refuse_it_as_larger_than_an_answer_may_be(
                self, load: Callable[[], Coroutine[Any, Any, None]]
            ) -> None:
                with pytest.raises(OcrUnavailable, match="larger than"):
                    asyncio.run(load())
