"""The supervisor of the OCR sandbox (ocr/scanmylib_ocr/supervisor.py): its HTTP API on a Unix socket, served with the
engine manager, over a fake engine runtime.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import os
import socket
import tempfile
import threading
import time
import unittest
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, ClassVar

from scanmylib_ocr.client import request_json
from scanmylib_ocr.config import Settings
from scanmylib_ocr.engines import get_spec
from scanmylib_ocr.gpu import GpuMonitor
from scanmylib_ocr.manager import EngineManager
from scanmylib_ocr.protocol import BAD_IMAGE
from scanmylib_ocr.runtime import EngineFailure, EngineStartError
from scanmylib_ocr.supervisor import MAX_BODY_BYTES, Supervisor, UnixHTTPServer, read_manifest

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MANIFEST = {"model": {"repo": "PaddlePaddle/PaddleOCR-VL-1.6", "revision": "test"}}
TAG_BYTES = 8
IDLE_UNLOAD_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 10.0
SHUTDOWN_TIMEOUT_SECONDS = 5.0
# An upper bound for a test's signal or a state of the engine: reaching it means the test is broken, not slow.
SIGNAL_TIMEOUT_SECONDS = 10.0
START_ERROR = "vllm exited with code 1: CUDA out of memory"


class Signals:
    """Lets a test hold the fake engine at precise points instead of guessing durations."""

    def __init__(self) -> None:
        self.page_started = threading.Event()
        self.release_pages = threading.Event()
        self.allow_start = threading.Event()
        self.allow_start.set()


class FakeRuntime:
    """The supervisor hands a runtime only the image of a page, so the last bytes of the image name what the fake does
    with the page."""

    def __init__(self, events: list[str], signals: Signals, start_error: str | None) -> None:
        self.events = events
        self.signals = signals
        self.start_error = start_error
        self.is_running = False

    def start(self) -> None:
        self.events.append("start")
        self.signals.allow_start.wait(SIGNAL_TIMEOUT_SECONDS)
        if self.start_error:
            raise EngineStartError(self.start_error)
        self.is_running = True

    def stop(self) -> None:
        self.events.append("stop")
        self.is_running = False

    def interrupt(self) -> None:
        self.is_running = False

    def alive(self) -> bool:
        return self.is_running

    def describe_failure(self) -> str:
        return "fake engine stopped"

    def parse(self, job_id: str, image_path: str, options: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        with open(image_path, "rb") as image_file:
            image = image_file.read()
        tag = image[-TAG_BYTES:].rstrip(b"\x00").decode() or "page"
        self.events.append(f"parse:{tag}")
        if tag.startswith("slow"):
            self.signals.page_started.set()
            self.signals.release_pages.wait(SIGNAL_TIMEOUT_SECONDS)
        if tag == "crash":
            self.is_running = False
            raise EngineFailure("worker stopped while processing the page")
        if tag == "garbage":
            return {"id": job_id, "ok": False, "error": BAD_IMAGE, "detail": "cannot decode"}
        result = {
            "width": 100,
            "height": 200,
            "markdown": f"# {tag}",
            "images": [],
            "blocks": [{"label": "number", "content": "42", "bbox": [0, 0, 1, 1], "order": None}],
            "page_numbers": ["42"],
            "page_continuation": None,
            "preprocess": {"angle": 0, "unwarped": bool(options.get("unwarp"))},
        }
        return {"id": job_id, "ok": True, "result": result, "infer_s": 0.01}


@dataclass(frozen=True)
class RunningSupervisor:
    socket_path: str
    events: list[str]
    signals: Signals


@dataclass(frozen=True)
class CrashSequence:
    failure: tuple[int, str]
    health_after_the_crash: dict[str, Any]
    logged_errors_after_the_crash: list[str]
    next_page_status: int
    events_after_the_next_page: list[str]


class LogRecorder(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextlib.contextmanager
def record_logs(logger_name: str, level: int) -> Iterator[list[logging.LogRecord]]:
    logger = logging.getLogger(logger_name)
    recorder = LogRecorder()
    previous_handlers, previous_level, previous_propagate = logger.handlers, logger.level, logger.propagate
    logger.handlers = [recorder]
    logger.setLevel(level)
    logger.propagate = False
    try:
        yield recorder.records
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def make_sandbox_directory(register_cleanup: Callable[[Callable[[], object]], None]) -> str:
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-supervisor-")
    register_cleanup(directory.cleanup)
    with open(os.path.join(directory.name, "MANIFEST.json"), "w") as manifest:
        json.dump(MANIFEST, manifest)
    return directory.name


def build_settings(sandbox_directory: str, idle_unload_seconds: float = IDLE_UNLOAD_SECONDS) -> Settings:
    return replace(
        Settings.from_env({}),
        socket_path=os.path.join(sandbox_directory, "ocr.sock"),
        work_dir=sandbox_directory,
        idle_unload_s=idle_unload_seconds,
        sandbox_dir=sandbox_directory,
    )


def start_supervisor(
    register_cleanup: Callable[[Callable[[], object]], None],
    idle_unload_seconds: float = IDLE_UNLOAD_SECONDS,
    start_error: str | None = None,
) -> RunningSupervisor:
    settings = build_settings(make_sandbox_directory(register_cleanup), idle_unload_seconds)
    events: list[str] = []
    signals = Signals()
    spec = get_spec(settings.engine)
    manager = EngineManager(settings, spec, runtime_factory=lambda: FakeRuntime(events, signals, start_error))
    server = UnixHTTPServer(settings.socket_path, Supervisor(settings, spec, manager, GpuMonitor()))
    register_cleanup(server.server_close)
    manager.start()
    register_cleanup(functools.partial(manager.shutdown, SHUTDOWN_TIMEOUT_SECONDS))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    register_cleanup(server.shutdown)
    # Never leave a slow page or a start blocked behind a failed hook.
    register_cleanup(signals.release_pages.set)
    register_cleanup(signals.allow_start.set)
    return RunningSupervisor(settings.socket_path, events, signals)


def tag_image(tag: str, image: bytes = JPEG) -> bytes:
    return image + tag.encode().ljust(TAG_BYTES, b"\x00")


def send_request(
    socket_path: str, method: str, path: str, body: bytes | None = None, content_type: str = "image/jpeg"
) -> tuple[int, Any]:
    headers = {"Content-Type": content_type} if body is not None else {}
    return request_json(socket_path, method, path, body=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)


def send_page(socket_path: str, tag: str, query: str = "") -> tuple[int, Any]:
    return send_request(socket_path, "POST", f"/v1/parse?request_id={tag}{query}", tag_image(tag))


def send_page_in_the_background(socket_path: str, tag: str, statuses: dict[str, int]) -> threading.Thread:
    thread = threading.Thread(target=lambda: statuses.update({tag: send_page(socket_path, tag)[0]}))
    thread.start()
    return thread


def read_health(socket_path: str) -> dict[str, Any]:
    health: dict[str, Any] = send_request(socket_path, "GET", "/health")[1]
    return health


def wait_for_health(socket_path: str, is_reached: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    deadline_seconds = time.monotonic() + SIGNAL_TIMEOUT_SECONDS
    health = read_health(socket_path)
    while not is_reached(health) and time.monotonic() < deadline_seconds:
        time.sleep(0.01)
        health = read_health(socket_path)
    return health


def wait_until_the_health_shows(
    socket_path: str, is_reached: Callable[[dict[str, Any]], bool], awaited_moment: str
) -> None:
    health = wait_for_health(socket_path, is_reached)
    if not is_reached(health):
        raise TimeoutError(f"{awaited_moment} never came: {health}")


def is_engine_ready(health: dict[str, Any]) -> bool:
    state: str = health["engine"]["state"]
    return state == "ready"


def is_engine_idle(health: dict[str, Any]) -> bool:
    state: str = health["engine"]["state"]
    return state == "idle"


def wait_until_the_engine_holds_a_slow_page(signals: Signals) -> None:
    if not signals.page_started.wait(SIGNAL_TIMEOUT_SECONDS):
        raise TimeoutError("the slow page never reached the engine")


def send_headers_of_a_body_over_the_limit(socket_path: str) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(REQUEST_TIMEOUT_SECONDS)
        client.connect(socket_path)
        client.sendall(
            b"POST /v1/parse HTTP/1.1\r\nHost: ocr\r\nContent-Type: image/jpeg\r\n"
            + f"Content-Length: {MAX_BODY_BYTES + 1}\r\n\r\n".encode()
        )
        # The answer may arrive in several reads; the server closes the connection after it.
        response = b""
        while chunk := client.recv(4096):
            response += chunk
    return response


class TheParseRouteWhenTheEngineReadsThePage(unittest.TestCase):
    request_id: ClassVar[str] = "p1"
    status: ClassVar[int]
    page: ClassVar[dict[str, Any]]
    events: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        cls.status, cls.page = send_page(supervisor.socket_path, cls.request_id, "&unwarp=1")
        cls.events = list(supervisor.events)

    def test_should_answer_200(self) -> None:
        self.assertEqual(self.status, 200)

    def test_should_return_the_request_id_it_was_given(self) -> None:
        self.assertEqual(self.page["request_id"], self.request_id)

    def test_should_return_what_the_engine_read(self) -> None:
        self.assertEqual(self.page["page_numbers"], ["42"])

    def test_should_hand_the_options_of_the_page_to_the_engine(self) -> None:
        self.assertTrue(self.page["preprocess"]["unwarped"])

    def test_should_name_the_engine_and_its_backend(self) -> None:
        self.assertEqual((self.page["engine"]["name"], self.page["engine"]["backend"]), ("paddleocr-vl", "vllm"))

    def test_should_report_the_time_spent_in_the_queue_loading_the_engine_and_reading_the_page(self) -> None:
        self.assertEqual(set(self.page["timings"]), {"queue_s", "load_s", "infer_s"})

    def test_should_start_the_engine_then_hand_it_the_page(self) -> None:
        self.assertEqual(self.events, ["start", f"parse:{self.request_id}"])


class TheParseRouteWhenTwoPagesFollowEachOther(unittest.TestCase):
    statuses: ClassVar[list[int]]
    events: ClassVar[list[str]]
    health: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        cls.statuses = [send_page(supervisor.socket_path, "a")[0], send_page(supervisor.socket_path, "b")[0]]
        cls.events = list(supervisor.events)
        cls.health = read_health(supervisor.socket_path)

    def test_should_answer_both(self) -> None:
        self.assertEqual(self.statuses, [200, 200])

    def test_should_start_the_engine_only_once(self) -> None:
        self.assertEqual(self.events.count("start"), 1)

    def test_should_keep_the_engine_ready_for_the_next_page(self) -> None:
        self.assertEqual(self.health["engine"]["state"], "ready")

    def test_should_count_the_pages_it_processed(self) -> None:
        self.assertEqual(self.health["processed"], 2)


class TheParseRouteWhenPagesArriveWhileTheEngineReadsOne(unittest.TestCase):
    statuses: ClassVar[dict[str, int]]
    queue_length_after_the_second_page: ClassVar[int]
    queue_length_after_the_third_page: ClassVar[int]
    events: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        statuses: dict[str, int] = {}
        first_page_request = send_page_in_the_background(supervisor.socket_path, "slow1", statuses)
        wait_until_the_engine_holds_a_slow_page(supervisor.signals)
        second_page_request = send_page_in_the_background(supervisor.socket_path, "slow2", statuses)
        cls.queue_length_after_the_second_page = wait_for_health(
            supervisor.socket_path, lambda health: health["queue"] == 1
        )["queue"]
        third_page_request = send_page_in_the_background(supervisor.socket_path, "slow3", statuses)
        cls.queue_length_after_the_third_page = wait_for_health(
            supervisor.socket_path, lambda health: health["queue"] == 2
        )["queue"]
        supervisor.signals.release_pages.set()
        for page_request in (first_page_request, second_page_request, third_page_request):
            page_request.join()
        cls.statuses = dict(statuses)
        cls.events = list(supervisor.events)

    def test_should_queue_them(self) -> None:
        self.assertEqual((self.queue_length_after_the_second_page, self.queue_length_after_the_third_page), (1, 2))

    def test_should_answer_every_page(self) -> None:
        self.assertEqual(self.statuses, {"slow1": 200, "slow2": 200, "slow3": 200})

    def test_should_hand_them_to_the_engine_one_at_a_time_in_arrival_order(self) -> None:
        parsed_pages = [event for event in self.events if event.startswith("parse")]
        self.assertEqual(parsed_pages, ["parse:slow1", "parse:slow2", "parse:slow3"])


class TheParseRouteWhenTheContentTypeIsNotAnImage(unittest.TestCase):
    refusal: ClassVar[tuple[int, str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        status, body = send_request(supervisor.socket_path, "POST", "/v1/parse", JPEG, content_type="text/plain")
        cls.refusal = (status, body["error"])

    def test_should_refuse_the_page_as_an_unsupported_type(self) -> None:
        self.assertEqual(self.refusal, (415, "unsupported_type"))


class TheParseRouteWhenTheBodyIsNotAnImage(unittest.TestCase):
    refusal: ClassVar[tuple[int, str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        status, body = send_request(supervisor.socket_path, "POST", "/v1/parse", b"not an image at all")
        cls.refusal = (status, body["error"])

    def test_should_refuse_the_page_as_a_bad_image(self) -> None:
        self.assertEqual(self.refusal, (400, "bad_image"))


class TheParseRouteWhenAnOptionIsNeitherOnNorOff(unittest.TestCase):
    refusal: ClassVar[tuple[int, str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        status, body = send_request(supervisor.socket_path, "POST", "/v1/parse?unwarp=maybe", JPEG)
        cls.refusal = (status, body["error"])

    def test_should_refuse_the_page_as_a_bad_request(self) -> None:
        self.assertEqual(self.refusal, (400, "bad_request"))


class TheParseRouteWhenTheContentTypeHasParameters(unittest.TestCase):
    status: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        png_page = tag_image("png", PNG)
        cls.status, _ = send_request(
            supervisor.socket_path, "POST", "/v1/parse", png_page, content_type="image/png; charset=binary"
        )

    def test_should_read_the_page_by_its_media_type(self) -> None:
        self.assertEqual(self.status, 200)


class TheParseRouteWhenTheBodyIsLargerThanItsLimit(unittest.TestCase):
    response: ClassVar[bytes]
    events: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        cls.response = send_headers_of_a_body_over_the_limit(supervisor.socket_path)
        cls.events = list(supervisor.events)

    def test_should_answer_413_before_reading_the_body(self) -> None:
        self.assertTrue(self.response.startswith(b"HTTP/1.1 413"), self.response)

    def test_should_name_the_error_too_large(self) -> None:
        self.assertIn(b'"too_large"', self.response)

    def test_should_leave_the_engine_alone(self) -> None:
        self.assertEqual(self.events, [])


class TheParseRouteWhenTheEngineCannotDecodeTheImage(unittest.TestCase):
    refusal: ClassVar[tuple[int, str]]
    logged_warnings: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        with record_logs("scanmylib_ocr", logging.WARNING) as records:
            status, body = send_page(supervisor.socket_path, "garbage")
        cls.refusal = (status, body["error"])
        cls.logged_warnings = [record.getMessage() for record in records]

    def test_should_refuse_the_page_as_a_bad_image(self) -> None:
        self.assertEqual(self.refusal, (400, "bad_image"))

    def test_should_log_why_the_engine_refused_the_page(self) -> None:
        self.assertEqual(self.logged_warnings, ["request garbage failed: bad_image: cannot decode"])


def setUpModule() -> None:
    supervisor = start_supervisor(unittest.addModuleCleanup)
    with record_logs("scanmylib_ocr", logging.WARNING) as records:
        status, body = send_page(supervisor.socket_path, "crash")
    logged_errors_after_the_crash = [record.getMessage() for record in records]
    health_after_the_crash = wait_for_health(supervisor.socket_path, is_engine_idle)
    next_page_status, _ = send_page(supervisor.socket_path, "after")
    _TheParseRouteWhenTheEngineCrashesDuringAPage.crash_sequence = CrashSequence(
        failure=(status, body.get("error")),
        health_after_the_crash=health_after_the_crash,
        logged_errors_after_the_crash=logged_errors_after_the_crash,
        next_page_status=next_page_status,
        events_after_the_next_page=list(supervisor.events),
    )


class _TheParseRouteWhenTheEngineCrashesDuringAPage(unittest.TestCase):
    crash_sequence: ClassVar[CrashSequence]


class TheParseRouteWhenTheEngineCrashesDuringAPage(_TheParseRouteWhenTheEngineCrashesDuringAPage):
    def test_should_answer_500_saying_that_the_processing_failed(self) -> None:
        self.assertEqual(self.crash_sequence.failure, (500, "processing_failed"))

    def test_should_stop_the_engine(self) -> None:
        self.assertEqual(self.crash_sequence.health_after_the_crash["engine"]["state"], "idle")

    def test_should_report_the_crash_as_the_last_error_of_the_engine(self) -> None:
        self.assertIn("worker stopped", self.crash_sequence.health_after_the_crash["engine"]["last_error"])

    def test_should_log_the_failure_of_the_page(self) -> None:
        self.assertEqual(
            self.crash_sequence.logged_errors_after_the_crash,
            ["request crash failed: worker stopped while processing the page"],
        )


class TheParseRouteWhenTheEngineCrashesDuringAPageWhenTheNextPageArrives(_TheParseRouteWhenTheEngineCrashesDuringAPage):
    def test_should_read_it(self) -> None:
        self.assertEqual(self.crash_sequence.next_page_status, 200)

    def test_should_start_a_new_engine_for_it(self) -> None:
        self.assertEqual(
            self.crash_sequence.events_after_the_next_page, ["start", "parse:crash", "stop", "start", "parse:after"]
        )


class TheParseRouteWhenTheEngineFailsToStart(unittest.TestCase):
    health_with_a_page_waiting: ClassVar[dict[str, Any]]
    replies: ClassVar[list[tuple[int, Any]]]
    events: ClassVar[list[str]]
    health: ClassVar[dict[str, Any]]
    logged_errors: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup, start_error=START_ERROR)
        supervisor.signals.allow_start.clear()
        replies: list[tuple[int, Any]] = []
        with record_logs("scanmylib_ocr", logging.WARNING) as records:
            first_page_request = threading.Thread(target=lambda: replies.append(send_page(supervisor.socket_path, "a")))
            first_page_request.start()
            wait_until_the_health_shows(
                supervisor.socket_path,
                lambda health: health["engine"]["state"] == "starting",
                "the start of the engine",
            )
            second_page_request = threading.Thread(
                target=lambda: replies.append(send_page(supervisor.socket_path, "b"))
            )
            second_page_request.start()
            cls.health_with_a_page_waiting = wait_for_health(
                supervisor.socket_path, lambda health: health["queue"] == 1
            )
            supervisor.signals.allow_start.set()
            first_page_request.join()
            second_page_request.join()
        cls.logged_errors = [record.getMessage() for record in records]
        cls.replies = list(replies)
        cls.events = list(supervisor.events)
        cls.health = read_health(supervisor.socket_path)

    def test_should_keep_a_page_that_arrives_during_the_start_waiting_for_it(self) -> None:
        self.assertEqual(
            (self.health_with_a_page_waiting["engine"]["state"], self.health_with_a_page_waiting["queue"]),
            ("starting", 1),
        )

    def test_should_answer_503_to_every_waiting_page(self) -> None:
        self.assertEqual([status for status, _ in self.replies], [503, 503])

    def test_should_say_that_the_engine_is_unavailable(self) -> None:
        self.assertEqual([body["error"] for _, body in self.replies], ["engine_unavailable", "engine_unavailable"])

    def test_should_give_every_page_the_reason_of_the_failure(self) -> None:
        without_the_reason = [body["detail"] for _, body in self.replies if "CUDA out of memory" not in body["detail"]]
        self.assertEqual(len(self.replies), 2)
        self.assertEqual(without_the_reason, [])

    def test_should_try_to_start_the_engine_once_for_both_pages(self) -> None:
        self.assertEqual(self.events, ["start"])

    def test_should_report_the_engine_in_error(self) -> None:
        self.assertEqual(self.health["engine"]["state"], "error")

    def test_should_report_the_failure_as_the_last_error_of_the_engine(self) -> None:
        self.assertIn("CUDA out of memory", self.health["engine"]["last_error"])

    def test_should_log_the_failure_once_however_many_pages_wait(self) -> None:
        self.assertEqual(self.logged_errors, [f"engine failed to start: {START_ERROR}"])


class TheHealthRouteWhenNoPageWasSentYet(unittest.TestCase):
    status: ClassVar[int]
    health: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        cls.status, cls.health = send_request(supervisor.socket_path, "GET", "/health")

    def test_should_answer_200(self) -> None:
        self.assertEqual(self.status, 200)

    def test_should_report_the_engine_idle_since_it_starts_only_for_a_page(self) -> None:
        self.assertEqual(self.health["engine"]["state"], "idle")

    def test_should_report_the_versions_of_the_manifest_of_the_sandbox(self) -> None:
        self.assertEqual(self.health["versions"], MANIFEST)


class TheHealthRouteWhenTheEngineIsReadingAPage(unittest.TestCase):
    status: ClassVar[int]
    health: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        page_request = threading.Thread(target=send_page, args=(supervisor.socket_path, "slow"))
        page_request.start()
        wait_until_the_engine_holds_a_slow_page(supervisor.signals)
        cls.status, cls.health = send_request(supervisor.socket_path, "GET", "/health")
        supervisor.signals.release_pages.set()
        page_request.join()

    def test_should_answer_without_waiting_for_the_page(self) -> None:
        self.assertEqual(self.status, 200)

    def test_should_report_the_engine_busy(self) -> None:
        self.assertTrue(self.health["busy"])

    def test_should_report_the_engine_ready(self) -> None:
        self.assertEqual(self.health["engine"]["state"], "ready")


class TheHealthRouteWhenTheEngineHasReadAPage(unittest.TestCase):
    health: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        send_page(supervisor.socket_path, "p")
        cls.health = wait_for_health(supervisor.socket_path, lambda health: not health["busy"])

    def test_should_report_the_engine_free(self) -> None:
        self.assertFalse(self.health["busy"])


class TheLoadRouteWhenTheEngineIsIdle(unittest.TestCase):
    reply: ClassVar[tuple[int, Any]]
    health: ClassVar[dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        cls.reply = send_request(supervisor.socket_path, "POST", "/v1/load")
        cls.health = wait_for_health(supervisor.socket_path, is_engine_ready)

    def test_should_answer_202_while_the_engine_starts(self) -> None:
        self.assertEqual(self.reply, (202, {"state": "starting"}))

    def test_should_start_the_engine_in_the_background(self) -> None:
        self.assertEqual(self.health["engine"]["state"], "ready")


class TheLoadRouteWhenTheEngineIsReady(unittest.TestCase):
    reply: ClassVar[tuple[int, Any]]
    events: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        send_request(supervisor.socket_path, "POST", "/v1/load")
        wait_until_the_health_shows(supervisor.socket_path, is_engine_ready, "a ready engine")
        cls.reply = send_request(supervisor.socket_path, "POST", "/v1/load")
        cls.events = list(supervisor.events)

    def test_should_answer_200_ready(self) -> None:
        self.assertEqual(self.reply, (200, {"state": "ready"}))

    def test_should_not_start_the_engine_again(self) -> None:
        self.assertEqual(self.events, ["start"])


class TheUnloadRouteWhenTheEngineIsReady(unittest.TestCase):
    reply: ClassVar[tuple[int, Any]]
    health: ClassVar[dict[str, Any]]
    events: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        send_request(supervisor.socket_path, "POST", "/v1/load")
        wait_until_the_health_shows(supervisor.socket_path, is_engine_ready, "a ready engine")
        cls.reply = send_request(supervisor.socket_path, "POST", "/v1/unload")
        cls.health = read_health(supervisor.socket_path)
        cls.events = list(supervisor.events)

    def test_should_answer_200_idle(self) -> None:
        self.assertEqual(self.reply, (200, {"state": "idle"}))

    def test_should_stop_the_engine_before_it_answers(self) -> None:
        self.assertEqual(self.health["engine"]["state"], "idle")

    def test_should_stop_the_engine_it_started(self) -> None:
        self.assertEqual(self.events, ["start", "stop"])


class TheUnloadRouteWhenTheEngineIsReadingAPage(unittest.TestCase):
    unload_grace_seconds: ClassVar[float] = 0.3
    is_unload_waiting: ClassVar[bool]
    unload_replies: ClassVar[list[tuple[int, Any]]]
    page_statuses: ClassVar[dict[str, int]]
    events: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        page_statuses: dict[str, int] = {}
        page_request = send_page_in_the_background(supervisor.socket_path, "slow", page_statuses)
        wait_until_the_engine_holds_a_slow_page(supervisor.signals)
        unload_replies: list[tuple[int, Any]] = []
        unload_request = threading.Thread(
            target=lambda: unload_replies.append(send_request(supervisor.socket_path, "POST", "/v1/unload"))
        )
        unload_request.start()
        unload_request.join(cls.unload_grace_seconds)
        cls.is_unload_waiting = unload_request.is_alive()
        supervisor.signals.release_pages.set()
        unload_request.join()
        page_request.join()
        cls.unload_replies = list(unload_replies)
        cls.page_statuses = dict(page_statuses)
        cls.events = list(supervisor.events)

    def test_should_wait_for_the_page_in_the_engine(self) -> None:
        self.assertTrue(self.is_unload_waiting, "unload returned while a page was still in the engine")

    def test_should_answer_200_idle_once_the_engine_stopped(self) -> None:
        self.assertEqual(self.unload_replies, [(200, {"state": "idle"})])

    def test_should_let_the_engine_finish_the_page(self) -> None:
        self.assertEqual(self.page_statuses, {"slow": 200})

    def test_should_stop_the_engine_after_the_page(self) -> None:
        self.assertEqual(self.events, ["start", "parse:slow", "stop"])


class WhenNoPageArrivesForTheIdleDelay(unittest.TestCase):
    status: ClassVar[int]
    health_after_the_delay: ClassVar[dict[str, Any]]
    events: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        idle_unload_seconds = 0.5
        supervisor = start_supervisor(cls.addClassCleanup, idle_unload_seconds=idle_unload_seconds)
        cls.status, _ = send_page(supervisor.socket_path, "p")
        cls.health_after_the_delay = wait_for_health(supervisor.socket_path, is_engine_idle)
        cls.events = list(supervisor.events)

    def test_should_read_the_page_first(self) -> None:
        self.assertEqual(self.status, 200)

    def test_should_stop_the_engine_once_the_delay_has_passed_so_that_it_holds_no_gpu_memory_while_idle(self) -> None:
        self.assertEqual(self.health_after_the_delay["engine"]["state"], "idle")

    def test_should_stop_the_engine_after_the_page(self) -> None:
        self.assertEqual(self.events, ["start", "parse:p", "stop"])


class WhenARequestMatchesNoRoute(unittest.TestCase):
    status: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        supervisor = start_supervisor(cls.addClassCleanup)
        cls.status, _ = send_request(supervisor.socket_path, "GET", "/nowhere")

    def test_should_answer_404(self) -> None:
        self.assertEqual(self.status, 404)


class TheReadManifestFunctionWhenTheManifestIsMissing(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="scanmylib-manifest-")
        self.addCleanup(directory.cleanup)
        with record_logs("scanmylib_ocr", logging.WARNING) as records:
            self.versions = read_manifest(replace(Settings.from_env({}), sandbox_dir=directory.name))
        self.warnings = [record.getMessage() for record in records]

    def test_should_report_no_versions(self) -> None:
        self.assertEqual(self.versions, {})

    def test_should_warn_that_it_cannot_read_the_manifest(self) -> None:
        warnings_without_their_cause = [warning.partition(":")[0] for warning in self.warnings]
        self.assertEqual(warnings_without_their_cause, ["cannot read the sandbox manifest"])


class TheReadManifestFunctionWhenTheManifestIsNotAJsonObject(unittest.TestCase):
    contents: ClassVar[Mapping[str, object]] = MappingProxyType(
        {"a list": ["model"], "a string": "model", "null": None}
    )

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="scanmylib-manifest-")
        self.addCleanup(directory.cleanup)
        settings = replace(Settings.from_env({}), sandbox_dir=directory.name)
        self.versions: dict[str, dict[str, Any]] = {}
        self.warnings: dict[str, list[str]] = {}
        for content_name, content in self.contents.items():
            with open(os.path.join(directory.name, "MANIFEST.json"), "w") as manifest:
                json.dump(content, manifest)
            with record_logs("scanmylib_ocr", logging.WARNING) as records:
                self.versions[content_name] = read_manifest(settings)
            self.warnings[content_name] = [record.getMessage() for record in records]

    def test_should_report_no_versions_so_that_health_never_shows_what_is_not_a_manifest(self) -> None:
        self.assertEqual(len(self.versions), len(self.contents))
        for content_name, versions in self.versions.items():
            with self.subTest(content_name):
                self.assertEqual(versions, {})

    def test_should_warn_that_the_manifest_is_not_a_json_object(self) -> None:
        self.assertEqual(len(self.warnings), len(self.contents))
        for content_name, warnings in self.warnings.items():
            with self.subTest(content_name):
                self.assertEqual(warnings, ["the sandbox manifest is not a JSON object"])


class TheReadManifestFunctionWhenTheManifestIsAJsonObject(unittest.TestCase):
    def setUp(self) -> None:
        sandbox_directory = make_sandbox_directory(self.addCleanup)
        self.versions = read_manifest(replace(Settings.from_env({}), sandbox_dir=sandbox_directory))

    def test_should_report_it_as_the_versions_of_the_sandbox(self) -> None:
        self.assertEqual(self.versions, MANIFEST)


def build_idle_supervisor(settings: Settings) -> Supervisor:
    spec = get_spec(settings.engine)
    return Supervisor(settings, spec, EngineManager(settings, spec), GpuMonitor())


class TheUnixHttpServerConstructorWhenTheSocketIsFree(unittest.TestCase):
    def setUp(self) -> None:
        settings = build_settings(make_sandbox_directory(self.addCleanup))
        server = UnixHTTPServer(settings.socket_path, build_idle_supervisor(settings))
        self.addCleanup(server.server_close)
        self.socket_permissions = os.stat(settings.socket_path).st_mode & 0o777

    def test_should_let_only_the_owner_and_its_group_read_and_write_the_socket(self) -> None:
        self.assertEqual(self.socket_permissions, 0o660)


class _TheUnixHttpServerConstructorWhenAnotherServerServesTheSocket(unittest.TestCase):
    def setUp(self) -> None:
        settings = build_settings(make_sandbox_directory(self.addCleanup))
        self.socket_path = settings.socket_path
        supervisor = build_idle_supervisor(settings)
        server = UnixHTTPServer(self.socket_path, supervisor)
        self.addCleanup(server.server_close)
        self.serve_the_same_socket = functools.partial(UnixHTTPServer, self.socket_path, supervisor)


class TheUnixHttpServerConstructorWhenAnotherServerServesTheSocket(
    _TheUnixHttpServerConstructorWhenAnotherServerServesTheSocket
):
    def test_should_refuse_to_serve_it_too_so_that_no_server_can_take_it_over(self) -> None:
        self.assertRaisesRegex(RuntimeError, "is served by another process", self.serve_the_same_socket)


class TheUnixHttpServerConstructorWhenAnotherServerServesTheSocketWhenTheSecondServerIsRefused(
    _TheUnixHttpServerConstructorWhenAnotherServerServesTheSocket
):
    def setUp(self) -> None:
        super().setUp()
        with suppress(RuntimeError):
            self.serve_the_same_socket()
        self.does_socket_exist = os.path.exists(self.socket_path)

    def test_should_leave_the_socket_of_the_other_server_in_place(self) -> None:
        self.assertTrue(self.does_socket_exist)


class TheServerCloseMethodWhenTheServerServesTheSocket(unittest.TestCase):
    def setUp(self) -> None:
        settings = build_settings(make_sandbox_directory(self.addCleanup))
        server = UnixHTTPServer(settings.socket_path, build_idle_supervisor(settings))
        server.server_close()
        self.does_socket_exist = os.path.exists(settings.socket_path)

    def test_should_remove_the_socket(self) -> None:
        self.assertFalse(self.does_socket_exist)


if __name__ == "__main__":
    unittest.main()
