"""The status route (GET /api/status): what it reports of the OCR sandbox, from the sandbox's /health."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from scanmylib import __version__
from support import AUTH, build_client, preparing_settings, running_api


@dataclass(frozen=True)
class UnreachableSandbox:
    ocr_status: dict[str, Any]
    socket_path: Path


@dataclass(frozen=True)
class StatusAnswer:
    status: int
    ocr_status: dict[str, Any]


class TestTheStatusRoute:
    class TestTheGetMethod:
        class TestWhenNoSandboxListensOnItsSocket:
            @pytest.fixture(scope="class")
            @classmethod
            def unreachable_sandbox(cls, tmp_path_factory: pytest.TempPathFactory) -> UnreachableSandbox:
                with preparing_settings(tmp_path_factory.mktemp("api")) as settings, build_client(settings) as client:
                    return UnreachableSandbox(
                        client.get("/api/status", headers=AUTH).json()["ocr"], settings.ocr_socket
                    )

            def test_should_report_it_unreachable_for_its_missing_socket(
                self, unreachable_sandbox: UnreachableSandbox
            ) -> None:
                assert unreachable_sandbox.ocr_status == {
                    "reachable": False,
                    "state": "unreachable",
                    "backend": None,
                    "last_error": f"socket {unreachable_sandbox.socket_path} absent",
                    "gpu": None,
                }

        class TestWhenTheSandboxAnswers:
            @pytest.fixture(scope="class")
            @classmethod
            def status(cls, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
                with running_api(tmp_path_factory.mktemp("api")) as api:
                    status: dict[str, Any] = api.client.get("/api/status", headers=AUTH).json()
                    return status

            def test_should_report_its_engine(self, status: dict[str, Any]) -> None:
                assert status["ocr"] == {
                    "reachable": True,
                    "state": "idle",
                    "backend": "fake",
                    "last_error": None,
                    "gpu": None,
                }

            def test_should_report_the_version_of_the_api(self, status: dict[str, Any]) -> None:
                assert status["version"] == __version__

        class TestWhenTheSandboxAnswersWithFieldsOfOtherTypes:
            @pytest.fixture(scope="class")
            @classmethod
            def status_answer(cls, tmp_path_factory: pytest.TempPathFactory) -> StatusAnswer:
                with running_api(tmp_path_factory.mktemp("api")) as api:
                    api.fake_ocr.status_body = json.dumps(
                        {
                            "engine": {"state": 1, "backend": {"a": 1}, "last_error": "x\ud800\n" + "y" * 5000},
                            "gpu": {"name": ["x"], "memory_used_mb": "lots", "memory_total_mb": 24576, "extra": "z"},
                        }
                    ).encode()
                    response = api.client.get("/api/status", headers=AUTH)
                    return StatusAnswer(response.status_code, response.json()["ocr"])

            def test_should_answer_ok(self, status_answer: StatusAnswer) -> None:
                assert status_answer.status == 200

            def test_should_relay_only_its_typed_and_bounded_fields_since_the_phone_reads_them_as_strings(
                self, status_answer: StatusAnswer
            ) -> None:
                assert status_answer.ocr_status == {
                    "reachable": True,
                    "state": None,
                    "backend": None,
                    "last_error": ("x? " + "y" * 5000)[:1000],
                    "gpu": {"name": None, "memory_used_mb": None, "memory_total_mb": 24576},
                }

        class TestWhenTheSandboxAnswersWithAnUnusableHealth:
            @pytest.fixture(
                scope="class",
                params=[
                    b"[" * 50_000,
                    b'{"engine": {"state": "error", "last_error": "' + b"A" * (1024 * 1024) + b'"}}',
                ],
                ids=["deeply-nested", "oversized"],
            )
            @classmethod
            def status_answer(
                cls, request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
            ) -> StatusAnswer:
                with running_api(tmp_path_factory.mktemp("api")) as api:
                    api.fake_ocr.status_body = request.param
                    response = api.client.get("/api/status", headers=AUTH)
                    return StatusAnswer(response.status_code, response.json()["ocr"])

            def test_should_answer_ok(self, status_answer: StatusAnswer) -> None:
                assert status_answer.status == 200

            def test_should_report_it_unreachable(self, status_answer: StatusAnswer) -> None:
                assert (status_answer.ocr_status["reachable"], status_answer.ocr_status["state"]) == (
                    False,
                    "unreachable",
                )

            def test_should_bound_its_error_to_300_characters(self, status_answer: StatusAnswer) -> None:
                assert len(status_answer.ocr_status["last_error"]) <= 300
