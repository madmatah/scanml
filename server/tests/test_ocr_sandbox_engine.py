"""The OCR engine over the sandbox's protocol (adapters/ocr_sandbox/engine.py), against the fake sandbox on a real Unix
socket."""

from __future__ import annotations

import asyncio

import pytest

from scanmylib.adapters.ocr_sandbox.client import OcrClient
from scanmylib.adapters.ocr_sandbox.engine import SandboxOcrEngine
from scanmylib.application.ocr_engine import EngineStatus, GpuStatus
from scanmylib.devtools.fake_ocr import FakeOcrServer


class TestTheSandboxOcrEngine:
    class TestTheReadStatusMethod:
        class TestWhenTheSandboxReportsMemoriesThatAreNotFiniteNumbers:
            PARSE_TIMEOUT_SECONDS = 10
            HEALTH_BODY = (
                b'{"engine":{"state":"ready","backend":"vllm","last_error":null},'
                b'"gpu":{"name":"Example GPU","memory_used_mb":NaN,"memory_total_mb":Infinity}}'
            )

            @pytest.fixture
            def gpu_status(self, fake_ocr: FakeOcrServer) -> GpuStatus | None:
                fake_ocr.status_body = self.HEALTH_BODY

                async def read_status_through_a_new_client() -> EngineStatus:
                    client = OcrClient(fake_ocr.socket_path, self.PARSE_TIMEOUT_SECONDS)
                    try:
                        return await SandboxOcrEngine(client).read_status()
                    finally:
                        await client.aclose()

                return asyncio.run(read_status_through_a_new_client()).gpu

            def test_should_report_neither_memory_since_json_has_no_nan_and_no_infinity(
                self, gpu_status: GpuStatus | None
            ) -> None:
                assert gpu_status == GpuStatus(
                    name="Example GPU", memory_used_mebibytes=None, memory_total_mebibytes=None
                )
