"""The worker that parses pages for the supervisor (ocr/scanmylib_ocr/worker.py), with an engine of the tests.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import contextlib
import functools
import io
import logging
import os
import unittest
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from unittest import mock

from scanmylib_ocr import protocol, worker
from scanmylib_ocr.engines.base import EngineSpec, PageEngine, PageOptions, PageResult
from scanmylib_ocr.protocol import Channel

if TYPE_CHECKING:
    from scanmylib_ocr.config import Settings

JOB_ID = "job-1"
LIMIT_BYTES = 1024
ENGINE_NAME = "recording-engine"
MISSING_LIBRARY_MESSAGE = "libGL.so.1: cannot open shared object file"


class HugeResultEngine(PageEngine):
    def import_libraries(self) -> None:
        pass

    def load(self) -> None:
        pass

    def parse(self, image_path: str, options: PageOptions) -> PageResult:
        return {
            "width": 1000,
            "height": 1400,
            "markdown": "x" * 4 * LIMIT_BYTES,
            "images": [],
            "blocks": [],
            "page_numbers": [],
            "page_continuation": None,
            "preprocess": {},
        }


class RecordingEngine(PageEngine):
    def __init__(self, import_error: ImportError | None = None) -> None:
        self.calls: list[str] = []
        self._import_error = import_error

    def import_libraries(self) -> None:
        self.calls.append("import_libraries")
        if self._import_error is not None:
            raise self._import_error

    def load(self) -> None:
        self.calls.append("load")

    def parse(self, image_path: str, options: PageOptions) -> PageResult:
        raise NotImplementedError


class RecordingSpec(EngineSpec):
    name = ENGINE_NAME
    model = "recording-model"

    def __init__(self, engine: RecordingEngine) -> None:
        self.engine = engine

    def worker_command(self, settings: Settings) -> list[str]:
        raise NotImplementedError

    def describe(self, settings: Settings) -> dict[str, Any]:
        return {"name": self.name}

    def create_engine(self, settings: Settings) -> PageEngine:
        return self.engine


def use_engine(test: unittest.TestCase, engine: RecordingEngine) -> None:
    environment_patcher = mock.patch.dict(os.environ, {"OCR_ENGINE": ENGINE_NAME})
    environment_patcher.start()
    test.addCleanup(environment_patcher.stop)
    spec_patcher = mock.patch.object(worker, "get_spec", return_value=RecordingSpec(engine))
    spec_patcher.start()
    test.addCleanup(spec_patcher.stop)


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


def receive_reply(channel: Channel) -> dict[str, Any]:
    reply = channel.receive()
    if reply is None:
        raise EOFError("the worker closed the protocol pipe without a reply")
    return reply


class TheServeFunctionWhenAResultIsLargerThanTheProtocolLimit(unittest.TestCase):
    def setUp(self) -> None:
        to_worker_read_end, to_worker_write_end = os.pipe()
        from_worker_read_end, from_worker_write_end = os.pipe()
        worker_channel = Channel(to_worker_read_end, from_worker_write_end)
        self.addCleanup(worker_channel.close)
        supervisor_channel = Channel(from_worker_read_end, to_worker_write_end)
        self.addCleanup(supervisor_channel.close)
        limit_patcher = mock.patch.object(protocol, "MAX_MESSAGE_BYTES", LIMIT_BYTES)
        limit_patcher.start()
        self.addCleanup(limit_patcher.stop)
        supervisor_channel.send({"op": "parse", "id": JOB_ID, "image_path": "page.jpg"})
        supervisor_channel.send({"op": "shutdown"})
        with record_logs("scanmylib_ocr.worker", logging.ERROR) as records:
            worker.serve(worker_channel, HugeResultEngine())
        self.error_messages = [record.getMessage() for record in records]
        worker_channel.close()
        self.reply = receive_reply(supervisor_channel)

    def test_should_answer_the_page_with_a_processing_failure_so_that_the_supervisor_never_waits_for_it(self) -> None:
        self.assertEqual(
            (self.reply["id"], self.reply["ok"], self.reply["error"]), (JOB_ID, False, protocol.PROCESSING_FAILED)
        )

    def test_should_say_that_the_result_is_larger_than_the_limit(self) -> None:
        self.assertIn(f"larger than {LIMIT_BYTES}", self.reply["detail"])

    def test_should_log_that_it_cannot_send_the_result(self) -> None:
        self.assertIn(f"cannot send the result of page {JOB_ID}", self.error_messages)


class TheMainFunctionWhenAskedToCheckTheEnvironment(unittest.TestCase):
    def setUp(self) -> None:
        engine = RecordingEngine()
        use_engine(self, engine)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.exit_status = worker.main(["--check"])
        self.output = output.getvalue()
        self.calls = list(engine.calls)

    def test_should_succeed(self) -> None:
        self.assertEqual(self.exit_status, 0)

    def test_should_import_the_engine_s_libraries_without_loading_its_models(self) -> None:
        self.assertEqual(self.calls, ["import_libraries"])

    def test_should_say_which_engine_it_checked(self) -> None:
        self.assertEqual(self.output, f"ok: the {ENGINE_NAME} engine's libraries import\n")


class TheMainFunctionWhenALibraryOfTheEngineDoesNotImport(unittest.TestCase):
    def setUp(self) -> None:
        use_engine(self, RecordingEngine(import_error=ImportError(MISSING_LIBRARY_MESSAGE)))
        self.act = functools.partial(worker.main, ["--check"])

    def test_should_fail_with_the_error_that_names_the_library(self) -> None:
        self.assertRaisesRegex(ImportError, "libGL", self.act)


if __name__ == "__main__":
    unittest.main()
