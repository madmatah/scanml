"""The runtime of a loaded engine (ocr/scanmylib_ocr/runtime.py), with fake workers that are scripts of a few lines.

The gate runs them under `docker run --init`, which reaps the processes they leave orphaned.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import re
import sys
import textwrap
import time
import unittest
from collections.abc import Callable, Iterator
from contextlib import suppress
from dataclasses import replace
from typing import Any, ClassVar
from unittest import mock

from scanmylib_ocr import protocol
from scanmylib_ocr import runtime as runtime_module
from scanmylib_ocr.config import Settings
from scanmylib_ocr.engines.base import EngineSpec, PageEngine
from scanmylib_ocr.runtime import EngineFailure, EngineRuntime, EngineStartError

PRELUDE = textwrap.dedent(
    """
    import os, subprocess, sys, time
    from scanmylib_ocr.protocol import PROTOCOL_FDS_ENV, Channel
    channel = Channel(*(int(fd) for fd in os.environ[PROTOCOL_FDS_ENV].split(",")))
    """
)

NOISY_ECHO = PRELUDE + textwrap.dedent(
    """
    print('{"id": "forged", "ok": true}')          # looks like a protocol message
    os.write(1, b"C-level noise without newline")
    print("noise on stderr", file=sys.stderr)
    channel.send({"event": "ready"})
    while (message := channel.receive()) is not None and message.get("op") != "shutdown":
        print("more noise", flush=True)
        if message["image_path"] == "exit":
            sys.exit(3)
        channel.send({"id": message["id"], "ok": True, "result": {"echo": message["options"]}})
    """
)

FATAL = PRELUDE + 'channel.send({"event": "fatal", "detail": "no GPU found"})\nsys.exit(1)\n'

# What a failed vLLM start looks like: the root cause, a long traceback, then a generic error.
CRASH_WITH_ROOT_CAUSE = PRELUDE + textwrap.dedent(
    """
    print("(EngineCore pid=7) ERROR [core.py:1433] ValueError: 0.28 GiB KV cache is needed", flush=True)
    for line in range(60):
        print(f'  File "engine.py", line {line}, in start', flush=True)
    print("RuntimeError: Engine core initialization failed. See root cause above.", flush=True)
    sys.exit(1)
    """
)

SILENT = PRELUDE + 'channel.send({"event": "ready"})\ntime.sleep(60)\n'

NEVER_READY = PRELUDE + "time.sleep(60)\n"

# Endless output without a newline, on the protocol pipe or on stdout.
ENDLESS_RESULT_LINE = PRELUDE + textwrap.dedent(
    """
    channel.send({"event": "ready"})
    channel.receive()
    channel._writer.write(b'{"id": "job-1", "ok": true, "result": "' + b"x" * (4 << 20))
    channel._writer.flush()
    time.sleep(60)
    """
)

ENDLESS_OUTPUT_LINE = PRELUDE + textwrap.dedent(
    """
    sys.stdout.buffer.write(b"x" * (1 << 20))
    sys.stdout.flush()
    channel.send({"event": "ready"})
    channel.receive()  # the shutdown request
    """
)

WITH_CHILD_PROCESS = PRELUDE + textwrap.dedent(
    """
    child = subprocess.Popen(["sleep", "60"])
    channel.send({"event": "ready"})
    message = channel.receive()
    channel.send({"id": message["id"], "ok": True, "result": {"child_process_id": child.pid}})
    channel.receive()
    time.sleep(60)  # ignores the shutdown request, like a hung worker
    """
)

SETTINGS = replace(Settings.from_env({}), backend="native", start_timeout_s=5.0)
JOB_ID = "job-1"
PAGE_PATH = "page.jpg"
PAGE_THE_WORKER_DIES_ON = "exit"
REPLY_TIMEOUT_SECONDS = 5.0
OUTPUT_LINE_BYTES = 1 << 20
OUTPUT_PIECE_LIMIT_BYTES = 4096
RESULT_LINE_LIMIT_BYTES = 1 << 20
WAIT_TIMEOUT_SECONDS = 5.0


class ScriptSpec(EngineSpec):
    name = "fake"
    model = "fake"
    backends = ("native",)

    def __init__(self, script: str) -> None:
        self.script = script

    def worker_command(self, settings: Settings) -> list[str]:
        return [sys.executable, "-c", self.script]

    def describe(self, settings: Settings) -> dict[str, Any]:
        return {"name": self.name}

    def create_engine(self, settings: Settings) -> PageEngine:
        raise NotImplementedError


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


def is_process_gone(process_id: int) -> bool:
    # A zombie has exited already: only the init of `docker run --init` has yet to reap it.
    try:
        with open(f"/proc/{process_id}/stat") as stat:
            return stat.read().split(")")[-1].split()[0] == "Z"
    except FileNotFoundError:
        return True


def wait_until_gone(process_id: int) -> bool:
    deadline_seconds = time.monotonic() + WAIT_TIMEOUT_SECONDS
    while not is_process_gone(process_id) and time.monotonic() < deadline_seconds:
        time.sleep(0.05)
    return is_process_gone(process_id)


def wait_until_relayed(records: list[logging.LogRecord], size_bytes: int) -> None:
    deadline_seconds = time.monotonic() + WAIT_TIMEOUT_SECONDS
    while sum(len(record.getMessage()) for record in records) < size_bytes and time.monotonic() < deadline_seconds:
        time.sleep(0.05)


def measure_seconds(act: Callable[[], object], expected_failure: type[Exception]) -> float:
    started_at_seconds = time.monotonic()
    with suppress(expected_failure):
        act()
    return time.monotonic() - started_at_seconds


class TheParseMethodWhenTheWorkerPrintsNoise(unittest.TestCase):
    reply: ClassVar[dict[str, Any]]
    is_alive_after_the_page: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        runtime = EngineRuntime(SETTINGS, ScriptSpec(NOISY_ECHO))
        cls.addClassCleanup(runtime.stop)
        runtime.start()
        cls.reply = runtime.parse(JOB_ID, PAGE_PATH, {"unwarp": True}, timeout_s=REPLY_TIMEOUT_SECONDS)
        cls.is_alive_after_the_page = runtime.alive()

    def test_should_return_the_reply_of_the_worker_untouched_so_that_no_output_can_forge_a_message(self) -> None:
        self.assertEqual(self.reply, {"id": JOB_ID, "ok": True, "result": {"echo": {"unwarp": True}}})

    def test_should_keep_the_worker_running(self) -> None:
        self.assertTrue(self.is_alive_after_the_page)


class TheParseMethodWhenTheWorkerDiesDuringAPage(unittest.TestCase):
    def setUp(self) -> None:
        runtime = EngineRuntime(SETTINGS, ScriptSpec(NOISY_ECHO))
        self.addCleanup(runtime.stop)
        runtime.start()
        self.parse_the_page = functools.partial(
            runtime.parse, JOB_ID, PAGE_THE_WORKER_DIES_ON, {}, timeout_s=REPLY_TIMEOUT_SECONDS
        )

    def test_should_fail_saying_that_the_worker_stopped(self) -> None:
        self.assertRaisesRegex(EngineFailure, "worker stopped while processing the page", self.parse_the_page)


class TheAliveMethodWhenTheWorkerDiedDuringAPage(unittest.TestCase):
    def setUp(self) -> None:
        runtime = EngineRuntime(SETTINGS, ScriptSpec(NOISY_ECHO))
        self.addCleanup(runtime.stop)
        runtime.start()
        with suppress(EngineFailure):
            runtime.parse(JOB_ID, PAGE_THE_WORKER_DIES_ON, {}, timeout_s=REPLY_TIMEOUT_SECONDS)
        self.is_alive = runtime.alive()

    def test_should_report_the_engine_dead(self) -> None:
        self.assertFalse(self.is_alive)


class TheStartMethodWhenTheWorkerCannotLoadTheEngine(unittest.TestCase):
    def setUp(self) -> None:
        runtime = EngineRuntime(SETTINGS, ScriptSpec(FATAL))
        self.addCleanup(runtime.stop)
        self.start_the_engine = runtime.start

    def test_should_fail_with_the_reason_of_the_worker(self) -> None:
        self.assertRaisesRegex(
            EngineStartError, "worker failed to load the engine: no GPU found", self.start_the_engine
        )


class TheStartMethodWhenTheWorkerExitsAfterPrintingTheRootCause(unittest.TestCase):
    def setUp(self) -> None:
        runtime = EngineRuntime(SETTINGS, ScriptSpec(CRASH_WITH_ROOT_CAUSE))
        self.addCleanup(runtime.stop)
        self.start_the_engine = runtime.start

    def test_should_fail_with_the_exit_code_of_the_worker(self) -> None:
        self.assertRaisesRegex(EngineStartError, "worker exited with code 1", self.start_the_engine)

    def test_should_quote_the_root_cause_printed_before_the_generic_error(self) -> None:
        self.assertRaisesRegex(
            EngineStartError, re.escape("ValueError: 0.28 GiB KV cache is needed"), self.start_the_engine
        )


class _TheStartMethodWhenTheWorkerIsNeverReady(unittest.TestCase):
    def setUp(self) -> None:
        start_timeout_seconds = 1.0
        runtime = EngineRuntime(replace(SETTINGS, start_timeout_s=start_timeout_seconds), ScriptSpec(NEVER_READY))
        self.addCleanup(runtime.stop)
        self.start_the_engine = runtime.start


class TheStartMethodWhenTheWorkerIsNeverReady(_TheStartMethodWhenTheWorkerIsNeverReady):
    def test_should_fail_once_its_timeout_has_passed(self) -> None:
        self.assertRaisesRegex(EngineStartError, "worker not ready after 1 s", self.start_the_engine)


class TheStartMethodWhenTheWorkerIsNeverReadyWhenTheStartFails(_TheStartMethodWhenTheWorkerIsNeverReady):
    def setUp(self) -> None:
        super().setUp()
        self.start_seconds = measure_seconds(self.start_the_engine, EngineStartError)

    def test_should_give_up_without_waiting_for_the_worker_to_exit(self) -> None:
        long_before_the_worker_exits_seconds = 15
        self.assertLess(self.start_seconds, long_before_the_worker_exits_seconds)


class TheParseMethodWhenTheWorkerNeverAnswers(unittest.TestCase):
    def setUp(self) -> None:
        runtime = EngineRuntime(SETTINGS, ScriptSpec(SILENT))
        self.addCleanup(runtime.stop)
        runtime.start()
        reply_timeout_seconds = 0.5
        self.parse_the_page = functools.partial(runtime.parse, JOB_ID, PAGE_PATH, {}, timeout_s=reply_timeout_seconds)

    def test_should_fail_once_its_timeout_has_passed(self) -> None:
        self.assertRaisesRegex(EngineFailure, "no result from the worker", self.parse_the_page)


class _TheParseMethodWhenTheWorkerSendsAnEndlessResultLine(unittest.TestCase):
    def setUp(self) -> None:
        limit_patcher = mock.patch.object(protocol, "MAX_MESSAGE_BYTES", RESULT_LINE_LIMIT_BYTES)
        limit_patcher.start()
        self.addCleanup(limit_patcher.stop)
        runtime = EngineRuntime(SETTINGS, ScriptSpec(ENDLESS_RESULT_LINE))
        self.addCleanup(runtime.stop)
        runtime.start()
        self.logged_records = self.enterContext(record_logs("scanmylib_ocr", logging.WARNING))
        reply_timeout_seconds = 30.0
        self.parse_the_page = functools.partial(runtime.parse, JOB_ID, PAGE_PATH, {}, timeout_s=reply_timeout_seconds)


class TheParseMethodWhenTheWorkerSendsAnEndlessResultLine(_TheParseMethodWhenTheWorkerSendsAnEndlessResultLine):
    def test_should_fail_saying_that_the_result_is_larger_than_the_limit(self) -> None:
        self.assertRaisesRegex(EngineFailure, f"larger than {RESULT_LINE_LIMIT_BYTES}", self.parse_the_page)


class TheParseMethodWhenTheWorkerSendsAnEndlessResultLineWhenThePageFails(
    _TheParseMethodWhenTheWorkerSendsAnEndlessResultLine
):
    def setUp(self) -> None:
        super().setUp()
        self.parse_seconds = measure_seconds(self.parse_the_page, EngineFailure)
        self.logged_errors = [record.getMessage() for record in self.logged_records]

    def test_should_fail_the_page_without_waiting_for_its_timeout(self) -> None:
        long_before_the_timeout_seconds = 10
        self.assertLess(self.parse_seconds, long_before_the_timeout_seconds)

    def test_should_log_that_the_worker_broke_the_protocol(self) -> None:
        self.assertEqual(
            self.logged_errors,
            [f"invalid message from the worker: protocol message larger than {RESULT_LINE_LIMIT_BYTES} bytes"],
        )


class TheStopMethodWhenAHungWorkerHasStartedAProcess(unittest.TestCase):
    is_child_running_before_the_stop: ClassVar[bool]
    is_child_gone_after_the_stop: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        runtime = EngineRuntime(SETTINGS, ScriptSpec(WITH_CHILD_PROCESS))
        cls.addClassCleanup(runtime.stop)
        runtime.start()
        reply = runtime.parse(JOB_ID, PAGE_PATH, {}, timeout_s=REPLY_TIMEOUT_SECONDS)
        child_process_id = reply["result"]["child_process_id"]
        cls.is_child_running_before_the_stop = not is_process_gone(child_process_id)
        runtime.stop()
        cls.is_child_gone_after_the_stop = wait_until_gone(child_process_id)

    def test_should_leave_the_process_of_the_worker_running_until_then(self) -> None:
        self.assertTrue(self.is_child_running_before_the_stop)

    def test_should_kill_it_too_since_the_whole_process_group_holds_the_gpu_memory(self) -> None:
        self.assertTrue(self.is_child_gone_after_the_stop)


class WhenTheWorkerPrintsAnEndlessLine(unittest.TestCase):
    piece_sizes_bytes: ClassVar[list[int]]

    @classmethod
    def setUpClass(cls) -> None:
        with (
            mock.patch.object(runtime_module, "MAX_OUTPUT_LINE_BYTES", OUTPUT_PIECE_LIMIT_BYTES),
            record_logs("worker", logging.INFO) as records,
        ):
            runtime = EngineRuntime(SETTINGS, ScriptSpec(ENDLESS_OUTPUT_LINE))
            cls.addClassCleanup(runtime.stop)
            runtime.start()
            wait_until_relayed(records, OUTPUT_LINE_BYTES)
            cls.piece_sizes_bytes = [len(record.getMessage()) for record in records]

    def test_should_relay_the_whole_line(self) -> None:
        self.assertEqual(sum(self.piece_sizes_bytes), OUTPUT_LINE_BYTES)

    def test_should_relay_it_in_pieces_no_longer_than_the_limit_so_that_the_supervisor_never_holds_it_whole(
        self,
    ) -> None:
        oversized_pieces = [size for size in self.piece_sizes_bytes if size > OUTPUT_PIECE_LIMIT_BYTES]
        self.assertNotEqual(self.piece_sizes_bytes, [])
        self.assertEqual(oversized_pieces, [])


if __name__ == "__main__":
    unittest.main()
