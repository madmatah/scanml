"""OCR loop behavior (docs/API.md "Behavior notes") against the fake sandbox."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scanmylib.devtools import fake_ocr
from scanmylib.devtools.fake_ocr import ParseResponse, canned_page
from scanmylib.domain.pages import MAX_OCR_RETRIES
from scanmylib.storage import TRASH_DIR, LibraryFiles
from support import (
    AUTH,
    RunningApi,
    build_client,
    create_document,
    jpeg,
    page_image,
    preparing_settings,
    read_until,
    running_api,
    serving_fake_ocr,
    upload,
    wait_for,
    wait_until_processed,
)

QUEUED_PAGE_NUMBER = 8
TURNED_PAGE_NUMBER = 204
TURNED_SCAN_SIZE_PIXELS = (1500, 1000 + TURNED_PAGE_NUMBER)
SIDEWAYS_SCAN_SIZE_PIXELS = (TURNED_SCAN_SIZE_PIXELS[1], TURNED_SCAN_SIZE_PIXELS[0])
QUARTER_TURN_DEGREES = 90
REPROCESSED_PAGE_NUMBER = 7
REPROCESSED_SCAN_SIZE_PIXELS = (1200, 1000 + REPROCESSED_PAGE_NUMBER)
REFUSAL_STATUS = 400
READ_PAGE_NUMBER = 3


def read_page(client: TestClient, page_id: str) -> dict[str, Any]:
    page: dict[str, Any] = client.get(f"/api/pages/{page_id}", headers=AUTH).json()
    return page


def build_page_without_markdown(width: int, height: int, request_id: str | None) -> ParseResponse:
    page = canned_page(width, height, request_id)
    del page["markdown"]
    return page


def build_page_without_timings(width: int, height: int, request_id: str | None) -> ParseResponse:
    return {**canned_page(width, height, request_id), "timings": None}


def build_page_inferred_in(inference_seconds: float) -> Callable[[int, int, str | None], ParseResponse]:
    def build_page(width: int, height: int, request_id: str | None) -> ParseResponse:
        return {**canned_page(width, height, request_id), "timings": {"infer_s": inference_seconds}}

    return build_page


def process_one_page(api: RunningApi) -> dict[str, Any]:
    document_id = create_document(api.client)
    page = upload(api.client, document_id, page_image(READ_PAGE_NUMBER)).json()
    wait_until_processed(api.client, document_id)
    return read_page(api.client, page["id"])


@dataclass(frozen=True)
class PageChangedDuringItsOcr:
    page: dict[str, Any]
    request_sizes_pixels: list[tuple[int, int]]
    trashed_names: list[str]


def capture_page_changed_during_its_ocr(api: RunningApi, page_id: str) -> PageChangedDuringItsOcr:
    return PageChangedDuringItsOcr(
        page=read_page(api.client, page_id),
        request_sizes_pixels=[(request["width"], request["height"]) for request in api.fake_ocr.requests],
        trashed_names=sorted(path.name for path in (api.settings.library_dir / TRASH_DIR).iterdir()),
    )


@dataclass(frozen=True)
class SandboxStartedLate:
    status_while_down: str
    page_once_started: dict[str, Any]


@dataclass(frozen=True)
class FailingPage:
    page: dict[str, Any]
    error_count: int
    parse_request_count: int
    reprocessed_page: dict[str, Any]


@dataclass(frozen=True)
class RetriedPage:
    status: str
    parse_request_count: int


@dataclass(frozen=True)
class PageFailedWithoutRetry:
    page: dict[str, Any]
    parse_request_count: int


@dataclass(frozen=True)
class EngineLoads:
    before_work: int
    once_work_is_queued: int


@pytest.fixture(scope="module")
def sandbox_started_late(tmp_path_factory: pytest.TempPathFactory) -> SandboxStartedLate:
    with preparing_settings(tmp_path_factory.mktemp("api")) as settings, build_client(settings) as client:
        document_id = create_document(client)
        page = upload(client, document_id, page_image(QUEUED_PAGE_NUMBER)).json()
        status_while_down = read_until(
            lambda: str(read_page(client, page["id"])["status"]), lambda status: status == "queued"
        )
        with serving_fake_ocr(settings.ocr_socket):
            document = wait_until_processed(client, document_id)
    return SandboxStartedLate(status_while_down, document["pages"][0])


@pytest.fixture(scope="module")
def failing_page(tmp_path_factory: pytest.TempPathFactory) -> FailingPage:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        api.fake_ocr.fail_next(500, MAX_OCR_RETRIES + 1)
        document_id = create_document(api.client)
        page = upload(api.client, document_id, page_image(5)).json()
        document = wait_until_processed(api.client, document_id)
        parse_request_count = len(api.fake_ocr.requests)
        api.client.post(f"/api/pages/{page['id']}/reprocess", headers=AUTH)
        wait_until_processed(api.client, document_id)
        return FailingPage(
            page=document["pages"][0],
            error_count=document["stats"]["error"],
            parse_request_count=parse_request_count,
            reprocessed_page=read_page(api.client, page["id"]),
        )


class TestTheOcrLoop:
    class TestWhenTheSandboxIsDown:
        def test_should_keep_an_uploaded_page_queued(self, sandbox_started_late: SandboxStartedLate) -> None:
            assert sandbox_started_late.status_while_down == "queued"

        class TestWhenTheSandboxStarts:
            def test_should_process_the_page(self, sandbox_started_late: SandboxStartedLate) -> None:
                assert sandbox_started_late.page_once_started["status"] == "done"

            def test_should_read_its_number(self, sandbox_started_late: SandboxStartedLate) -> None:
                assert sandbox_started_late.page_once_started["number"] == QUEUED_PAGE_NUMBER

    class TestWhenTheEngineIsUnavailable:
        @pytest.fixture(scope="class")
        @classmethod
        def retried_page(cls, tmp_path_factory: pytest.TempPathFactory) -> RetriedPage:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                api.fake_ocr.fail_next(503, MAX_OCR_RETRIES + 3)
                document_id = create_document(api.client)
                page = upload(api.client, document_id, page_image(5)).json()
                wait_until_processed(api.client, document_id, timeout_seconds=30.0)
                return RetriedPage(read_page(api.client, page["id"])["status"], len(api.fake_ocr.requests))

        def test_should_retry_the_page_without_counting_failures_until_it_is_read(
            self, retried_page: RetriedPage
        ) -> None:
            assert retried_page.status == "done"

        def test_should_send_the_page_again_after_each_refusal(self, retried_page: RetriedPage) -> None:
            assert retried_page.parse_request_count == MAX_OCR_RETRIES + 4

    class TestWhenProcessingFailsMoreTimesThanItsRetriesAllow:
        def test_should_report_the_page_in_error(self, failing_page: FailingPage) -> None:
            assert failing_page.page["status"] == "error"

        def test_should_say_why_it_failed(self, failing_page: FailingPage) -> None:
            assert failing_page.page["error"].startswith("OCR failed: HTTP 500 (processing_failed: simulated failure)")

        def test_should_send_the_page_once_and_retry_it_as_many_times_as_allowed(
            self, failing_page: FailingPage
        ) -> None:
            assert failing_page.parse_request_count == MAX_OCR_RETRIES + 1

        def test_should_count_the_error_in_the_document(self, failing_page: FailingPage) -> None:
            assert failing_page.error_count == 1

        def test_should_leave_the_page_out_of_the_document(self, failing_page: FailingPage) -> None:
            assert failing_page.page["in_document"] is False

        class TestWhenThePageIsReprocessed:
            def test_should_read_it(self, failing_page: FailingPage) -> None:
                assert failing_page.reprocessed_page["status"] == "done"

            def test_should_clear_its_error(self, failing_page: FailingPage) -> None:
                assert failing_page.reprocessed_page["error"] is None

    class TestWhenProcessingFailsTransiently:
        @pytest.fixture(scope="class")
        @classmethod
        def retried_page(cls, tmp_path_factory: pytest.TempPathFactory) -> RetriedPage:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                api.fake_ocr.fail_next(500, 2)
                document_id = create_document(api.client)
                upload(api.client, document_id, page_image(6))
                document = wait_until_processed(api.client, document_id)
                return RetriedPage(document["pages"][0]["status"], len(api.fake_ocr.requests))

        def test_should_read_the_page_once_retried(self, retried_page: RetriedPage) -> None:
            assert retried_page.status == "done"

        def test_should_retry_it_after_each_failure(self, retried_page: RetriedPage) -> None:
            assert retried_page.parse_request_count == 3

    class TestWhenTheSandboxRefusesThePage:
        @pytest.fixture(scope="class")
        @classmethod
        def refused_page(cls, tmp_path_factory: pytest.TempPathFactory) -> PageFailedWithoutRetry:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                api.fake_ocr.fail_next(REFUSAL_STATUS)
                page = process_one_page(api)
                return PageFailedWithoutRetry(page, len(api.fake_ocr.requests))

        def test_should_report_the_page_in_error_with_the_reason_of_the_sandbox(
            self, refused_page: PageFailedWithoutRetry
        ) -> None:
            assert (refused_page.page["status"], refused_page.page["error"]) == (
                "error",
                f"Image refused by the OCR: HTTP {REFUSAL_STATUS} (processing_failed: simulated failure)",
            )

        def test_should_send_it_only_once_since_retrying_cannot_help(
            self, refused_page: PageFailedWithoutRetry
        ) -> None:
            assert refused_page.parse_request_count == 1

    class TestWhenTheSandboxAnswersWithAnUnusableResult:
        @pytest.fixture(scope="class")
        @classmethod
        def page_with_unusable_result(cls, tmp_path_factory: pytest.TempPathFactory) -> PageFailedWithoutRetry:
            with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
                patch.setattr(fake_ocr, "canned_page", build_page_without_markdown)
                page = process_one_page(api)
                return PageFailedWithoutRetry(page, len(api.fake_ocr.requests))

        def test_should_report_the_page_in_error_with_what_is_wrong_in_the_result(
            self, page_with_unusable_result: PageFailedWithoutRetry
        ) -> None:
            page = page_with_unusable_result.page
            assert (page["status"], page["error"]) == ("error", "Invalid OCR result: markdown missing")

        def test_should_send_it_only_once_since_reading_it_again_would_give_the_same_answer(
            self, page_with_unusable_result: PageFailedWithoutRetry
        ) -> None:
            assert page_with_unusable_result.parse_request_count == 1

    class TestWhenTheSandboxReportsTheTimeOfItsInference:
        REPORTED_INFERENCE_SECONDS = 1.25

        @pytest.fixture(scope="class")
        @classmethod
        def recorded_duration_seconds(cls, tmp_path_factory: pytest.TempPathFactory) -> float:
            with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
                patch.setattr(fake_ocr, "canned_page", build_page_inferred_in(cls.REPORTED_INFERENCE_SECONDS))
                page = process_one_page(api)
                return float(page["ocr"]["duration_s"])

        def test_should_record_that_time_as_the_duration_of_the_page(self, recorded_duration_seconds: float) -> None:
            assert recorded_duration_seconds == pytest.approx(self.REPORTED_INFERENCE_SECONDS)

    class TestWhenTheSandboxReportsNoTimeOfItsInference:
        PARSE_DELAY_SECONDS = 0.2

        @pytest.fixture(scope="class")
        @classmethod
        def recorded_duration_seconds(cls, tmp_path_factory: pytest.TempPathFactory) -> float:
            with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
                patch.setattr(fake_ocr, "canned_page", build_page_without_timings)
                api.fake_ocr.delay = cls.PARSE_DELAY_SECONDS
                page = process_one_page(api)
                return float(page["ocr"]["duration_s"])

        def test_should_record_the_time_the_api_waited_for_its_answer(self, recorded_duration_seconds: float) -> None:
            assert recorded_duration_seconds >= self.PARSE_DELAY_SECONDS

    class TestWhenSeveralPagesAreQueued:
        UPLOADED_NUMBERS = (30, 10, 20)

        @pytest.fixture(scope="class")
        @classmethod
        def processed_numbers(cls, tmp_path_factory: pytest.TempPathFactory) -> list[int]:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                for number in cls.UPLOADED_NUMBERS:
                    upload(api.client, document_id, page_image(number))
                wait_until_processed(api.client, document_id)
                return [request["height"] - 1000 for request in api.fake_ocr.requests]

        def test_should_process_them_in_upload_order(self, processed_numbers: list[int]) -> None:
            assert processed_numbers == list(self.UPLOADED_NUMBERS)

    class TestWhenTheApiStopsWhileAPageIsProcessed:
        @pytest.fixture(scope="class")
        @classmethod
        def status_after_restart(cls, tmp_path_factory: pytest.TempPathFactory) -> str:
            with (
                preparing_settings(tmp_path_factory.mktemp("api")) as settings,
                serving_fake_ocr(settings.ocr_socket) as fake_ocr,
            ):
                fake_ocr.delay = 3.0
                with build_client(settings) as client:
                    document_id = create_document(client)
                    page = upload(client, document_id, page_image(9)).json()
                    wait_for(lambda: read_page(client, page["id"])["status"] == "processing")
                fake_ocr.delay = 0.0
                with build_client(settings) as client:
                    document = wait_until_processed(client, document_id)
            return str(document["pages"][0]["status"])

        def test_should_queue_the_page_again_on_restart_and_process_it(self, status_after_restart: str) -> None:
            assert status_after_restart == "done"

    class TestWhenWorkIsQueued:
        @pytest.fixture(scope="class")
        @classmethod
        def engine_loads(cls, tmp_path_factory: pytest.TempPathFactory) -> EngineLoads:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                before_work = api.fake_ocr.load_requests
                upload(api.client, document_id, page_image(1))
                once_work_is_queued = read_until(lambda: api.fake_ocr.load_requests, lambda count: count >= 1)
                wait_until_processed(api.client, document_id)
            return EngineLoads(before_work, once_work_is_queued)

        def test_should_ask_the_sandbox_to_load_its_engine_once_work_is_queued_and_not_before(
            self, engine_loads: EngineLoads
        ) -> None:
            assert (engine_loads.before_work, engine_loads.once_work_is_queued) == (0, 1)

    class TestWhenAPageIsRotatedWhileTheSandboxReadsIt:
        @pytest.fixture(scope="class")
        @classmethod
        def rotated_page(cls, tmp_path_factory: pytest.TempPathFactory) -> PageChangedDuringItsOcr:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                api.fake_ocr.parses_released.clear()
                try:
                    page = upload(api.client, document_id, jpeg(*SIDEWAYS_SCAN_SIZE_PIXELS)).json()
                    wait_for(lambda: api.fake_ocr.requests)
                    api.client.patch(f"/api/pages/{page['id']}", json={"rotation": QUARTER_TURN_DEGREES}, headers=AUTH)
                finally:
                    api.fake_ocr.parses_released.set()
                wait_until_processed(api.client, document_id)
                return capture_page_changed_during_its_ocr(api, page["id"])

        def test_should_drop_the_late_result_before_storing_any_of_it(
            self, rotated_page: PageChangedDuringItsOcr
        ) -> None:
            assert rotated_page.trashed_names == []

        def test_should_read_the_page_again_once_turned(self, rotated_page: PageChangedDuringItsOcr) -> None:
            assert (rotated_page.page["status"], rotated_page.page["number"]) == ("done", TURNED_PAGE_NUMBER)

        def test_should_send_it_again_turned(self, rotated_page: PageChangedDuringItsOcr) -> None:
            assert rotated_page.request_sizes_pixels == [SIDEWAYS_SCAN_SIZE_PIXELS, TURNED_SCAN_SIZE_PIXELS]

    class TestWhenAPageIsReprocessedWhileTheSandboxReadsIt:
        @pytest.fixture(scope="class")
        @classmethod
        def reprocessed_page(cls, tmp_path_factory: pytest.TempPathFactory) -> PageChangedDuringItsOcr:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                api.fake_ocr.parses_released.clear()
                try:
                    page = upload(api.client, document_id, page_image(REPROCESSED_PAGE_NUMBER)).json()
                    wait_for(lambda: api.fake_ocr.requests)
                    api.client.post(f"/api/pages/{page['id']}/reprocess", headers=AUTH)
                finally:
                    api.fake_ocr.parses_released.set()
                wait_until_processed(api.client, document_id)
                return capture_page_changed_during_its_ocr(api, page["id"])

        def test_should_drop_the_late_result_before_storing_any_of_it(
            self, reprocessed_page: PageChangedDuringItsOcr
        ) -> None:
            assert reprocessed_page.trashed_names == []

        def test_should_send_it_again(self, reprocessed_page: PageChangedDuringItsOcr) -> None:
            assert reprocessed_page.request_sizes_pixels == [REPROCESSED_SCAN_SIZE_PIXELS, REPROCESSED_SCAN_SIZE_PIXELS]

        def test_should_end_up_read_with_its_number(self, reprocessed_page: PageChangedDuringItsOcr) -> None:
            assert (reprocessed_page.page["status"], reprocessed_page.page["number"]) == (
                "done",
                REPROCESSED_PAGE_NUMBER,
            )

    class TestWhenAPageIsRotatedWhileItsResultIsStored:
        @pytest.fixture(scope="class")
        @classmethod
        def rotated_page(cls, tmp_path_factory: pytest.TempPathFactory) -> PageChangedDuringItsOcr:
            writes: list[str] = []
            writes_released = threading.Event()
            write_page_outputs = LibraryFiles.write_page_outputs

            def held_write_page_outputs(
                self: LibraryFiles,
                slug: str,
                key: str,
                markdown: str,
                images: Sequence[tuple[str, bytes]],
                raw: Mapping[str, object],
            ) -> None:
                writes.append(key)
                writes_released.wait()
                write_page_outputs(self, slug, key, markdown, images, raw)

            with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
                patch.setattr(LibraryFiles, "write_page_outputs", held_write_page_outputs)
                document_id = create_document(api.client)
                try:
                    page = upload(api.client, document_id, jpeg(*SIDEWAYS_SCAN_SIZE_PIXELS)).json()
                    wait_for(lambda: writes)
                    api.client.patch(f"/api/pages/{page['id']}", json={"rotation": QUARTER_TURN_DEGREES}, headers=AUTH)
                finally:
                    writes_released.set()
                wait_until_processed(api.client, document_id)
                return capture_page_changed_during_its_ocr(api, page["id"])

        def test_should_read_the_page_again_once_turned_instead_of_keeping_the_late_result(
            self, rotated_page: PageChangedDuringItsOcr
        ) -> None:
            assert (rotated_page.page["status"], rotated_page.page["number"]) == ("done", TURNED_PAGE_NUMBER)

        def test_should_send_it_again_turned(self, rotated_page: PageChangedDuringItsOcr) -> None:
            assert rotated_page.request_sizes_pixels == [SIDEWAYS_SCAN_SIZE_PIXELS, TURNED_SCAN_SIZE_PIXELS]

    class TestWhenAPageIsRotatedWhileTheSandboxRefusesIt:
        @pytest.fixture(scope="class")
        @classmethod
        def rotated_page(cls, tmp_path_factory: pytest.TempPathFactory) -> PageChangedDuringItsOcr:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                api.fake_ocr.fail_next(REFUSAL_STATUS)
                api.fake_ocr.parses_released.clear()
                try:
                    page = upload(api.client, document_id, jpeg(*SIDEWAYS_SCAN_SIZE_PIXELS)).json()
                    wait_for(lambda: api.fake_ocr.requests)
                    api.client.patch(f"/api/pages/{page['id']}", json={"rotation": QUARTER_TURN_DEGREES}, headers=AUTH)
                finally:
                    api.fake_ocr.parses_released.set()
                wait_until_processed(api.client, document_id)
                return capture_page_changed_during_its_ocr(api, page["id"])

        def test_should_read_the_page_again_once_turned_instead_of_leaving_it_in_error(
            self, rotated_page: PageChangedDuringItsOcr
        ) -> None:
            page = rotated_page.page
            assert (page["status"], page["error"], page["number"]) == ("done", None, TURNED_PAGE_NUMBER)

        def test_should_send_it_again_turned(self, rotated_page: PageChangedDuringItsOcr) -> None:
            assert rotated_page.request_sizes_pixels == [SIDEWAYS_SCAN_SIZE_PIXELS, TURNED_SCAN_SIZE_PIXELS]
