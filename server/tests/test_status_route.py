"""The status route (GET /api/status): what it reports of the OCR sandbox, from the sandbox's /health."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest

from scanmylib import __version__
from support import AUTH, build_client, preparing_settings, running_api


@dataclass(frozen=True)
class GuardedHealth:
    rule: str
    health: Mapping[str, object]
    relayed_ocr_status: Mapping[str, object]


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

        class TestWhenTheSandboxReportsItsGpu:
            REPORTED_HEALTH_BODY = (
                b'{"engine":{"state":"ready","backend":"vllm","last_error":null},'
                b'"gpu":{"name":"Example GPU","memory_used_mb":4410,"memory_total_mb":24576.5}}'
            )
            RELAYED_OCR_MEMBER = (
                '"ocr":{"reachable":true,"state":"ready","backend":"vllm","last_error":null,'
                '"gpu":{"name":"Example GPU","memory_used_mb":4410,"memory_total_mb":24576.5}}'
            )

            @pytest.fixture(scope="class")
            @classmethod
            def status_text(cls, tmp_path_factory: pytest.TempPathFactory) -> str:
                with running_api(tmp_path_factory.mktemp("api")) as api:
                    api.fake_ocr.status_body = cls.REPORTED_HEALTH_BODY
                    return api.client.get("/api/status", headers=AUTH).text

            def test_should_relay_its_fields_in_order_with_each_number_as_the_sandbox_sent_it(
                self, status_text: str
            ) -> None:
                assert self.RELAYED_OCR_MEMBER in status_text

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

        class TestWhenTheSandboxAnswersWithValuesOutOfTheirBounds:
            STATE_AND_BACKEND_MAX_CHARACTERS = 32
            GPU_NAME_MAX_CHARACTERS = 128
            OVERLONG_TEXT = "x" * (GPU_NAME_MAX_CHARACTERS + 1)
            READY_ENGINE: ClassVar[Mapping[str, object]] = {"state": "ready", "backend": "vllm", "last_error": None}
            REPORTED_GPU: ClassVar[Mapping[str, object]] = {
                "name": "Example GPU",
                "memory_used_mb": 4410,
                "memory_total_mb": 24576,
            }
            RELAYED_GPU: ClassVar[Mapping[str, object]] = REPORTED_GPU
            RELAYED_READY_ENGINE: ClassVar[Mapping[str, object]] = {"reachable": True, **READY_ENGINE, "gpu": None}
            GUARDED_HEALTHS = (
                GuardedHealth(
                    "a memory in use that is NaN is relayed as null, since JSON has no NaN",
                    {"engine": READY_ENGINE, "gpu": {**REPORTED_GPU, "memory_used_mb": math.nan}},
                    {**RELAYED_READY_ENGINE, "gpu": {**RELAYED_GPU, "memory_used_mb": None}},
                ),
                GuardedHealth(
                    "a total memory that is infinite is relayed as null, since JSON has no Infinity",
                    {"engine": READY_ENGINE, "gpu": {**REPORTED_GPU, "memory_total_mb": math.inf}},
                    {**RELAYED_READY_ENGINE, "gpu": {**RELAYED_GPU, "memory_total_mb": None}},
                ),
                GuardedHealth(
                    "a memory in use that is a boolean is relayed as null, though Python counts it as an integer",
                    {"engine": READY_ENGINE, "gpu": {**REPORTED_GPU, "memory_used_mb": True}},
                    {**RELAYED_READY_ENGINE, "gpu": {**RELAYED_GPU, "memory_used_mb": None}},
                ),
                GuardedHealth(
                    "a state is cut to its bound, so that the sandbox cannot flood the status that the api relays",
                    {"engine": {**READY_ENGINE, "state": OVERLONG_TEXT}},
                    {**RELAYED_READY_ENGINE, "state": OVERLONG_TEXT[:STATE_AND_BACKEND_MAX_CHARACTERS]},
                ),
                GuardedHealth(
                    "a backend is cut to its bound, so that the sandbox cannot flood the status that the api relays",
                    {"engine": {**READY_ENGINE, "backend": OVERLONG_TEXT}},
                    {**RELAYED_READY_ENGINE, "backend": OVERLONG_TEXT[:STATE_AND_BACKEND_MAX_CHARACTERS]},
                ),
                GuardedHealth(
                    "a GPU name is cut to its bound, so that the sandbox cannot flood the status that the api relays",
                    {"engine": READY_ENGINE, "gpu": {**REPORTED_GPU, "name": OVERLONG_TEXT}},
                    {**RELAYED_READY_ENGINE, "gpu": {**RELAYED_GPU, "name": OVERLONG_TEXT[:GPU_NAME_MAX_CHARACTERS]}},
                ),
                GuardedHealth(
                    "an engine that is not an object relays none of its fields",
                    {"engine": [READY_ENGINE]},
                    {**RELAYED_READY_ENGINE, "state": None, "backend": None},
                ),
                GuardedHealth(
                    "a GPU that is not an object is relayed as null",
                    {"engine": READY_ENGINE, "gpu": [REPORTED_GPU]},
                    RELAYED_READY_ENGINE,
                ),
                GuardedHealth(
                    "an empty state is relayed as null, since an empty text says no more than a missing one",
                    {"engine": {**READY_ENGINE, "state": ""}},
                    {**RELAYED_READY_ENGINE, "state": None},
                ),
            )

            @pytest.fixture(scope="class")
            @classmethod
            def relayed_ocr_statuses(cls, tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
                relayed_ocr_statuses: dict[str, dict[str, Any]] = {}
                with running_api(tmp_path_factory.mktemp("api")) as api:
                    for guarded_health in cls.GUARDED_HEALTHS:
                        api.fake_ocr.status_body = json.dumps(guarded_health.health).encode()
                        relayed_ocr_statuses[guarded_health.rule] = api.client.get("/api/status", headers=AUTH).json()[
                            "ocr"
                        ]
                return relayed_ocr_statuses

            def test_should_relay_each_field_only_within_its_guard(
                self, relayed_ocr_statuses: dict[str, dict[str, Any]]
            ) -> None:
                mismatches = {
                    guarded_health.rule: relayed_ocr_statuses.get(guarded_health.rule)
                    for guarded_health in self.GUARDED_HEALTHS
                    if relayed_ocr_statuses.get(guarded_health.rule) != guarded_health.relayed_ocr_status
                }
                assert (mismatches, len(relayed_ocr_statuses)) == ({}, len(self.GUARDED_HEALTHS))

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
