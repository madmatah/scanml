"""The fake sandbox (devtools/fake_ocr.py) follows docs/OCR_SANDBOX.md."""

from __future__ import annotations

import contextlib
import io
import socket
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from scanmylib.devtools.fake_ocr import FakeOcrServer, ParseResponse, canned_page, check_health, image_size
from scanmylib.devtools.fake_ocr import main as fake_ocr_main
from support import jpeg, locate_socket, serving_fake_ocr, temporary_socket_directory, wait_for

IMAGE_SIZE = (321, 123)
REQUEST_ID = "abc"
FAILURE_STATUS = 400
#: Above the bound of `wait_for`, so that a held parse never outlasts its client.
HELD_PARSE_TIMEOUT_SECONDS = 60.0


def encode_image(image_format: str, **options: object) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA" if image_format == "PNG" else "RGB", IMAGE_SIZE).save(buffer, image_format, **options)
    return buffer.getvalue()


@dataclass(frozen=True)
class NumberingConvention:
    width: int
    height: int
    page_numbers: list[str]


@dataclass(frozen=True)
class CannedNumbering:
    convention: NumberingConvention
    page: ParseResponse


@dataclass(frozen=True)
class ProtocolSession:
    health_at_start: dict[str, Any]
    load_answer: dict[str, Any]
    parse_status: int
    parse_answer: dict[str, Any]
    health_after_parse: dict[str, Any]
    unsupported_type_status: int
    undecodable_image_answer: dict[str, Any]
    unload_answer: dict[str, Any]


@dataclass(frozen=True)
class HeldParse:
    answers_while_held: list[int]
    status_once_released: int


@dataclass(frozen=True)
class HealthProbes:
    is_healthy_while_serving: bool
    is_healthy_once_stopped: bool


@dataclass(frozen=True)
class StaleSocketReplacement:
    is_answering_once_started: bool
    is_socket_left_once_stopped: bool


@pytest.fixture(scope="module")
def protocol_session() -> ProtocolSession:
    with (
        temporary_socket_directory() as socket_directory,
        serving_fake_ocr(locate_socket(socket_directory)) as fake_ocr,
    ):
        transport = httpx.HTTPTransport(uds=str(fake_ocr.socket_path))
        with httpx.Client(transport=transport, base_url="http://ocr") as sandbox:
            health_at_start = sandbox.get("/health").json()
            load_answer = sandbox.post("/v1/load").json()
            parsed = sandbox.post(
                f"/v1/parse?request_id={REQUEST_ID}", content=jpeg(1200, 1042), headers={"Content-Type": "image/jpeg"}
            )
            health_after_parse = sandbox.get("/health").json()
            unsupported_type = sandbox.post("/v1/parse", content=b"x", headers={"Content-Type": "image/gif"})
            undecodable_image = sandbox.post("/v1/parse", content=b"x", headers={"Content-Type": "image/jpeg"})
            unload_answer = sandbox.post("/v1/unload").json()
    return ProtocolSession(
        health_at_start=health_at_start,
        load_answer=load_answer,
        parse_status=parsed.status_code,
        parse_answer=parsed.json(),
        health_after_parse=health_after_parse,
        unsupported_type_status=unsupported_type.status_code,
        undecodable_image_answer=undecodable_image.json(),
        unload_answer=unload_answer,
    )


def hold_a_parse(fake_ocr: FakeOcrServer) -> HeldParse:
    answer_statuses: list[int] = []
    transport = httpx.HTTPTransport(uds=str(fake_ocr.socket_path))
    with httpx.Client(transport=transport, base_url="http://ocr", timeout=HELD_PARSE_TIMEOUT_SECONDS) as sandbox:
        fake_ocr.parses_released.clear()
        poster = threading.Thread(
            target=lambda: answer_statuses.append(
                sandbox.post("/v1/parse", content=jpeg(*IMAGE_SIZE), headers={"Content-Type": "image/jpeg"}).status_code
            )
        )
        poster.start()
        try:
            wait_for(lambda: fake_ocr.requests)
            answers_while_held = list(answer_statuses)
        finally:
            fake_ocr.parses_released.set()
            poster.join()
    return HeldParse(answers_while_held, answer_statuses[0])


@pytest.fixture(scope="module")
def health_probes() -> HealthProbes:
    with temporary_socket_directory() as socket_directory:
        socket_path = locate_socket(socket_directory)
        with serving_fake_ocr(socket_path):
            is_healthy_while_serving = check_health(socket_path)
        is_healthy_once_stopped = check_health(socket_path)
    return HealthProbes(is_healthy_while_serving, is_healthy_once_stopped)


@pytest.fixture(scope="module")
def stale_socket_replacement() -> StaleSocketReplacement:
    with temporary_socket_directory() as socket_directory:
        socket_path = locate_socket(socket_directory)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stale:
            stale.bind(str(socket_path))  # the file stays after close, with nobody listening
        with serving_fake_ocr(socket_path):
            is_answering_once_started = check_health(socket_path)
        is_socket_left_once_stopped = socket_path.exists()
    return StaleSocketReplacement(is_answering_once_started, is_socket_left_once_stopped)


class TestTheFakeOcrSandbox:
    class TestTheImageSizeFunction:
        class TestWhenTheImageIsOfAnAcceptedFormat:
            @pytest.fixture(
                params=[
                    jpeg(*IMAGE_SIZE),
                    encode_image("JPEG", progressive=True),
                    encode_image("PNG"),
                    encode_image("WEBP", quality=80),
                    encode_image("WEBP", lossless=True),
                    encode_image("WEBP", exif=b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x00"),
                ],
                ids=["a-jpeg", "a-progressive-jpeg", "a-png", "a-lossy-webp", "a-lossless-webp", "an-extended-webp"],
            )
            def size(self, request: pytest.FixtureRequest) -> tuple[int, int] | None:
                return image_size(request.param)

            def test_should_read_its_size_from_its_header(self, size: tuple[int, int] | None) -> None:
                assert size == IMAGE_SIZE

        class TestWhenTheDataIsNotAnImage:
            @pytest.fixture(params=[b"not an image", b"\xff\xd8\x00"], ids=["not-an-image", "a-jpeg-cut-short"])
            def size(self, request: pytest.FixtureRequest) -> tuple[int, int] | None:
                return image_size(request.param)

            def test_should_find_no_size(self, size: tuple[int, int] | None) -> None:
                assert size is None

    class TestTheCannedPageFunction:
        class TestWhenTheImageSizeFollowsANumberingConvention:
            @pytest.fixture(
                params=[
                    NumberingConvention(1200, 1042, ["42"]),
                    NumberingConvention(1201, 1042, ["42", "43"]),
                    NumberingConvention(1202, 1012, ["xii"]),
                    NumberingConvention(1203, 1042, []),
                    NumberingConvention(1204, 1042, []),
                    NumberingConvention(1200, 2000, []),
                ],
                ids=[
                    "the-height-past-1000-as-the-page-number",
                    "a-two-page-spread-for-a-width-ending-in-1",
                    "a-roman-numeral-for-a-width-ending-in-2",
                    "the-number-in-the-running-header-for-a-width-ending-in-3",
                    "no-number-for-a-width-ending-in-4",
                    "no-number-for-a-height-ending-in-000",
                ],
            )
            def canned_numbering(self, request: pytest.FixtureRequest) -> CannedNumbering:
                convention: NumberingConvention = request.param
                return CannedNumbering(convention, canned_page(convention.width, convention.height, "r"))

            def test_should_find_the_page_numbers_of_its_convention(self, canned_numbering: CannedNumbering) -> None:
                assert canned_numbering.page["page_numbers"] == canned_numbering.convention.page_numbers

            def test_should_hold_one_illustration(self, canned_numbering: CannedNumbering) -> None:
                assert canned_numbering.page["markdown"].count("imgs/") == 1

    class TestTheHealthRoute:
        class TestWhenTheSandboxHasJustStarted:
            def test_should_answer_ok(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.health_at_start["status"] == "ok"

            def test_should_report_an_idle_engine(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.health_at_start["engine"]["state"] == "idle"

        class TestWhenAPageWasParsed:
            def test_should_count_it_as_processed(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.health_after_parse["processed"] == 1

    class TestTheLoadRoute:
        class TestWhenTheEngineIsIdle:
            def test_should_answer_that_it_is_starting(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.load_answer == {"state": "starting"}

    class TestTheParseRoute:
        class TestWhenAJpegIsSent:
            def test_should_answer_ok(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.parse_status == 200

            def test_should_answer_with_the_id_of_the_request(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.parse_answer["request_id"] == REQUEST_ID

        class TestWhenAnUnsupportedTypeIsSent:
            def test_should_refuse_it_as_an_unsupported_media_type(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.unsupported_type_status == 415

        class TestWhenTheImageCannotBeDecoded:
            def test_should_answer_that_it_is_a_bad_image(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.undecodable_image_answer["error"] == "bad_image"

        class TestWhenTheParsesAreHeld:
            @pytest.fixture(scope="class")
            @classmethod
            def held_parse(cls) -> HeldParse:
                with (
                    temporary_socket_directory() as socket_directory,
                    serving_fake_ocr(locate_socket(socket_directory)) as fake_ocr,
                ):
                    return hold_a_parse(fake_ocr)

            def test_should_answer_none_until_they_are_released(self, held_parse: HeldParse) -> None:
                assert held_parse.answers_while_held == []

            def test_should_answer_the_page_once_released(self, held_parse: HeldParse) -> None:
                assert held_parse.status_once_released == 200

        class TestWhenTheParsesAreHeldAndTheNextOneFails:
            @pytest.fixture(scope="class")
            @classmethod
            def held_parse(cls) -> HeldParse:
                with (
                    temporary_socket_directory() as socket_directory,
                    serving_fake_ocr(locate_socket(socket_directory)) as fake_ocr,
                ):
                    fake_ocr.fail_next(FAILURE_STATUS)
                    return hold_a_parse(fake_ocr)

            def test_should_hold_the_failure_too(self, held_parse: HeldParse) -> None:
                assert held_parse.answers_while_held == []

            def test_should_answer_the_failure_with_its_status_once_released(self, held_parse: HeldParse) -> None:
                assert held_parse.status_once_released == FAILURE_STATUS

    class TestTheUnloadRoute:
        class TestWhenTheEngineIsLoaded:
            def test_should_answer_that_it_is_idle(self, protocol_session: ProtocolSession) -> None:
                assert protocol_session.unload_answer == {"state": "idle"}

    class TestTheCheckHealthFunction:
        class TestWhenASandboxAnswers:
            def test_should_find_it_healthy(self, health_probes: HealthProbes) -> None:
                assert health_probes.is_healthy_while_serving is True

            class TestWhenItHasStopped:
                def test_should_find_no_sandbox(self, health_probes: HealthProbes) -> None:
                    assert health_probes.is_healthy_once_stopped is False

        class TestWhenNoSocketIsThere:
            @pytest.fixture
            def is_healthy(self, socket_dir: Path) -> bool:
                return check_health(socket_dir / "missing.sock")

            def test_should_find_no_sandbox(self, is_healthy: bool) -> None:
                assert is_healthy is False

    class TestTheStartMethod:
        class TestWhenASandboxAnswersOnItsSocket:
            @pytest.fixture
            def start(self, fake_ocr: FakeOcrServer) -> Callable[[], None]:
                return FakeOcrServer(fake_ocr.socket_path).start

            def test_should_refuse_to_replace_it(self, start: Callable[[], None]) -> None:
                with pytest.raises(RuntimeError, match="served by another process"):
                    start()

        class TestWhenAStaleSocketIsOnItsPath:
            def test_should_replace_it_and_answer_on_it(self, stale_socket_replacement: StaleSocketReplacement) -> None:
                assert stale_socket_replacement.is_answering_once_started is True

        class TestWhenAFileThatIsNotASocketIsOnItsPath:
            TEXT_IN_PLACE_OF_THE_SOCKET = "not a socket"

            @pytest.fixture
            def start(self, socket_dir: Path) -> Callable[[], None]:
                path = locate_socket(socket_dir)
                path.write_text(self.TEXT_IN_PLACE_OF_THE_SOCKET)
                return FakeOcrServer(path).start

            def test_should_refuse_to_replace_it(self, start: Callable[[], None]) -> None:
                with pytest.raises(RuntimeError, match="not a socket"):
                    start()

            class TestWhenItHasRefused:
                @pytest.fixture
                def kept_text(self, start: Callable[[], None], socket_dir: Path) -> str:
                    with contextlib.suppress(RuntimeError):
                        start()
                    return locate_socket(socket_dir).read_text()

                def test_should_leave_the_file_as_it_was(self, kept_text: str) -> None:
                    situation = TestTheFakeOcrSandbox.TestTheStartMethod.TestWhenAFileThatIsNotASocketIsOnItsPath
                    assert kept_text == situation.TEXT_IN_PLACE_OF_THE_SOCKET

    class TestTheStopMethod:
        class TestWhenItsSandboxReplacedAStaleSocket:
            def test_should_remove_the_socket_it_bound(self, stale_socket_replacement: StaleSocketReplacement) -> None:
                assert stale_socket_replacement.is_socket_left_once_stopped is False

        class TestWhenItsStartWasRefusedForASocketThatAnswers:
            @pytest.fixture(scope="class")
            @classmethod
            def is_healthy(cls) -> bool:
                with (
                    temporary_socket_directory() as socket_directory,
                    serving_fake_ocr(locate_socket(socket_directory)) as fake_ocr,
                ):
                    intruder = FakeOcrServer(fake_ocr.socket_path)
                    with contextlib.suppress(RuntimeError):
                        intruder.start()
                    intruder.stop()
                    return check_health(fake_ocr.socket_path)

            def test_should_leave_the_socket_to_the_sandbox_that_answers_on_it(self, is_healthy: bool) -> None:
                assert is_healthy is True

    class TestTheCommandLine:
        class TestWhenItRunsInTheProductionStack:
            PRODUCTION_PROJECT = "scanmylib"

            @pytest.fixture
            def run(self, monkeypatch: pytest.MonkeyPatch, socket_dir: Path) -> Callable[[], None]:
                monkeypatch.setenv("SCANMYLIB_PROJECT", self.PRODUCTION_PROJECT)
                monkeypatch.setattr(sys, "argv", ["fake_ocr", "--socket", str(locate_socket(socket_dir))])
                return fake_ocr_main

            def test_should_refuse_to_run_saying_that_production_runs_the_real_sandbox(
                self, run: Callable[[], None], caplog: pytest.LogCaptureFixture
            ) -> None:
                with pytest.raises(SystemExit, match=r"^1$"):
                    run()
                assert "refusing to run in the production stack" in caplog.text

            class TestWhenItHasExited:
                @pytest.fixture
                def is_socket_left(self, run: Callable[[], None], socket_dir: Path) -> bool:
                    with contextlib.suppress(SystemExit):
                        run()
                    return locate_socket(socket_dir).exists()

                def test_should_leave_no_socket(self, is_socket_left: bool) -> None:
                    assert is_socket_left is False

        class TestWhenASandboxAnswersOnItsSocket:
            DEVELOPMENT_PROJECT = "scanmylib-dev"

            @pytest.fixture
            def run(self, monkeypatch: pytest.MonkeyPatch, fake_ocr: FakeOcrServer) -> Callable[[], None]:
                monkeypatch.setenv("SCANMYLIB_PROJECT", self.DEVELOPMENT_PROJECT)
                monkeypatch.setattr(sys, "argv", ["fake_ocr", "--socket", str(fake_ocr.socket_path)])
                return fake_ocr_main

            def test_should_refuse_to_run_saying_that_another_process_serves_the_socket(
                self, run: Callable[[], None], caplog: pytest.LogCaptureFixture
            ) -> None:
                with pytest.raises(SystemExit, match=r"^1$"):
                    run()
                assert "served by another process" in caplog.text

            class TestWhenItHasExited:
                @pytest.fixture
                def is_healthy(self, run: Callable[[], None], fake_ocr: FakeOcrServer) -> bool:
                    with contextlib.suppress(SystemExit):
                        run()
                    return check_health(fake_ocr.socket_path)

                def test_should_leave_the_sandbox_answering(self, is_healthy: bool) -> None:
                    assert is_healthy is True
