"""EngineRuntime tests with scripted fake workers (stdlib only, no GPU).

They check what the GPU engine relies on: protocol messages survive arbitrary
output on stdout/stderr, a dead or silent worker is detected, and stopping
the engine kills the worker's whole process group (where VRAM is held).
Run with ``docker run --init ...`` so that orphaned test processes get reaped.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
import time
import unittest
from dataclasses import replace
from typing import Any
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

WITH_GRANDCHILD = PRELUDE + textwrap.dedent(
    """
    grandchild = subprocess.Popen(["sleep", "60"])
    channel.send({"event": "ready"})
    message = channel.receive()
    channel.send({"id": message["id"], "ok": True, "result": {"pid": grandchild.pid}})
    channel.receive()
    time.sleep(60)  # ignores the shutdown request, like a hung worker
    """
)


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


def process_gone(pid: int) -> bool:
    """True when ``pid`` no longer runs (exited, possibly not yet reaped)."""
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().split(")")[-1].split()[0] == "Z"
    except FileNotFoundError:
        return True


class RuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = replace(Settings.from_env({}), backend="native", work_dir=self.tmp.name, start_timeout_s=5.0)
        self.runtime: EngineRuntime | None = None

    def tearDown(self) -> None:
        if self.runtime is not None:
            self.runtime.stop()
        self.tmp.cleanup()

    def start(self, script: str, settings: Settings | None = None) -> EngineRuntime:
        self.runtime = EngineRuntime(self.settings if settings is None else settings, ScriptSpec(script))
        self.runtime.start()
        return self.runtime

    def test_messages_survive_output_noise(self) -> None:
        runtime = self.start(NOISY_ECHO)
        reply = runtime.parse("job-1", "page.jpg", {"unwarp": True}, timeout_s=5)
        self.assertEqual(reply, {"id": "job-1", "ok": True, "result": {"echo": {"unwarp": True}}})
        self.assertTrue(runtime.alive())

    def test_worker_dying_during_a_page_is_reported(self) -> None:
        runtime = self.start(NOISY_ECHO)
        with self.assertRaises(EngineFailure) as failure:
            runtime.parse("job-1", "exit", {}, timeout_s=5)
        self.assertIn("worker", str(failure.exception))
        time.sleep(0.2)
        self.assertFalse(runtime.alive())

    def test_fatal_load_error_fails_the_start(self) -> None:
        with self.assertRaisesRegex(EngineStartError, "no GPU found"):
            self.start(FATAL)

    def test_start_error_reports_the_root_cause(self) -> None:
        with self.assertRaises(EngineStartError) as failure:
            self.start(CRASH_WITH_ROOT_CAUSE)
        message = str(failure.exception)
        self.assertIn("exited with code 1", message)
        self.assertIn("ValueError: 0.28 GiB KV cache is needed", message)

    def test_start_times_out(self) -> None:
        started = time.monotonic()
        with self.assertRaisesRegex(EngineStartError, "worker not ready"):
            self.start(NEVER_READY, replace(self.settings, start_timeout_s=1.0))
        self.assertLess(time.monotonic() - started, 15)

    def test_silent_worker_times_out(self) -> None:
        runtime = self.start(SILENT)
        with self.assertRaisesRegex(EngineFailure, "no result"):
            runtime.parse("job-1", "page.jpg", {}, timeout_s=0.5)

    def test_stop_kills_the_whole_process_group(self) -> None:
        runtime = self.start(WITH_GRANDCHILD)
        pid = runtime.parse("job-1", "page.jpg", {}, timeout_s=5)["result"]["pid"]
        self.assertFalse(process_gone(pid))
        runtime.stop()  # the worker ignores the shutdown request: SIGTERM, then SIGKILL
        self.runtime = None
        deadline = time.monotonic() + 5
        while not process_gone(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(process_gone(pid))

    def test_an_endless_result_line_fails_the_page_without_waiting_for_the_timeout(self) -> None:
        with mock.patch.object(protocol, "MAX_MESSAGE_BYTES", 1 << 20):
            runtime = self.start(ENDLESS_RESULT_LINE)
            started = time.monotonic()
            with self.assertRaisesRegex(EngineFailure, "larger than"):
                runtime.parse("job-1", "page.jpg", {}, timeout_s=30)
        self.assertLess(time.monotonic() - started, 10)

    def test_an_endless_output_line_is_relayed_in_bounded_pieces(self) -> None:
        with mock.patch.object(runtime_module, "MAX_OUTPUT_LINE_BYTES", 4096), self.assertLogs("worker") as logs:
            self.start(ENDLESS_OUTPUT_LINE)  # the line never ends while the worker runs
            deadline = time.monotonic() + 5
            while sum(len(record.getMessage()) for record in logs.records) < 1 << 20 and time.monotonic() < deadline:
                time.sleep(0.05)
        pieces = [record.getMessage() for record in logs.records]
        self.assertEqual(sum(map(len, pieces)), 1 << 20)
        self.assertLessEqual(max(map(len, pieces)), 4096)


if __name__ == "__main__":
    unittest.main()
