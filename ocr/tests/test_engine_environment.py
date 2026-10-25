"""The check that the engine's environment imports its libraries (ocr/scanmylib_ocr/engine_environment.py), with fake
workers that are scripts of a few lines.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import re
import signal
import sys
import textwrap
import time
import unittest
from dataclasses import replace
from typing import Any, ClassVar
from unittest import mock

from scanmylib_ocr import engine_environment
from scanmylib_ocr.config import Settings
from scanmylib_ocr.engine_environment import (
    PRINTED_LINE_CHARACTERS,
    PRINTED_TAIL_LINES,
    EnvironmentCheck,
    check_engine_environment,
)
from scanmylib_ocr.engines.base import EngineSpec, PageEngine

REPORTING = textwrap.dedent(
    """
    import os, sys
    print(sys.argv[1:])
    print(repr(os.environ.get("CUDA_VISIBLE_DEVICES")))
    """
)
HIDDEN_GPU_LINE = repr("")

MISSING_LIBRARY = 'raise ImportError("libGL.so.1: cannot open shared object file")\n'

# The child stays off the worker's output, so that only the stop of the whole process group can end it in time. The
# detached process leaves the group and keeps the output open, as a process that a library starts could.
NEVER_FINISHES = textwrap.dedent(
    """
    import subprocess, time
    child = subprocess.Popen(["sleep", "60"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    detached = subprocess.Popen(["sleep", "90"], start_new_session=True)
    print(f"child process {child.pid}", flush=True)
    print(f"detached process {detached.pid}", flush=True)
    time.sleep(60)
    """
)

EXTRA_LINE_COUNT = 10
LONG_OUTPUT = textwrap.dedent(
    f"""
    for number in range({PRINTED_TAIL_LINES + EXTRA_LINE_COUNT - 1}):
        print(f"line {{number}}")
    print("x" * {PRINTED_LINE_CHARACTERS * 2})
    """
)

TERMINAL_CONTROLS = ("\N{ESCAPE}]52;c;", "\t", "\x9b", "\N{RIGHT-TO-LEFT OVERRIDE}", "\\x1b")
ESCAPED_TERMINAL_CONTROLS = "\\x1b]52;c;\\x09\\x9b\\u202e\\x5cx1b"
PRINTING_TERMINAL_CONTROLS = f"print({''.join(TERMINAL_CONTROLS)!r})\n"

ESCAPED_CONTROL = "\\x1b"
ESCAPE_LENGTH_CHARACTERS = len(ESCAPED_CONTROL)
LEADING_COUNT_THAT_PUTS_THE_CUT_INSIDE_AN_ESCAPE = (
    PRINTED_LINE_CHARACTERS - ESCAPE_LENGTH_CHARACTERS // 2
) % ESCAPE_LENGTH_CHARACTERS
CUT_LINE_OF_TERMINAL_CONTROLS = "x" * LEADING_COUNT_THAT_PUTS_THE_CUT_INSIDE_AN_ESCAPE + ESCAPED_CONTROL * (
    (PRINTED_LINE_CHARACTERS - LEADING_COUNT_THAT_PUTS_THE_CUT_INSIDE_AN_ESCAPE) // ESCAPE_LENGTH_CHARACTERS
)
PRINTING_A_LONG_LINE_OF_TERMINAL_CONTROLS = (
    f'print("x" * {LEADING_COUNT_THAT_PUTS_THE_CUT_INSIDE_AN_ESCAPE} + chr(0x1b) * {PRINTED_LINE_CHARACTERS})\n'
)

LIBRARIES_IMPORT_LINE = "ok: the fake engine's libraries import"
LIBRARIES_IMPORT = f"print({LIBRARIES_IMPORT_LINE!r})\n"

SETTINGS = replace(Settings.from_env({}), backend="native")
SHORT_TIMEOUT_SECONDS = 10.0
RETURN_BOUND_SECONDS = 45.0
WAIT_TIMEOUT_SECONDS = 5.0
_PROCESS_LINE = re.compile(r"^(child|detached) process (\d+)$", re.MULTILINE)


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


def is_process_gone(process_id: int) -> bool:
    # A zombie has exited already: only the init of `docker run --init` has yet to reap it.
    try:
        with open(f"/proc/{process_id}/stat") as stat:
            return stat.read().split(")")[-1].split()[0] == "Z"
    except (FileNotFoundError, ProcessLookupError):
        return True


def wait_until_gone(process_id: int) -> bool:
    deadline_seconds = time.monotonic() + WAIT_TIMEOUT_SECONDS
    while not is_process_gone(process_id) and time.monotonic() < deadline_seconds:
        time.sleep(0.05)
    return is_process_gone(process_id)


def read_process_ids(output: str) -> dict[str, int]:
    return {match.group(1): int(match.group(2)) for match in _PROCESS_LINE.finditer(output)}


def kill_if_running(process_id: int) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.kill(process_id, signal.SIGKILL)


def run_main(test: unittest.TestCase, spec: EngineSpec) -> tuple[int, str]:
    spec_patcher = mock.patch.object(engine_environment, "get_spec", return_value=spec)
    spec_patcher.start()
    test.addCleanup(spec_patcher.stop)
    # The check's own process starts with no logging configured: so does each run here, whatever an earlier one left.
    root_logger = logging.getLogger()
    test.addCleanup(setattr, root_logger, "handlers", root_logger.handlers)
    test.addCleanup(root_logger.setLevel, root_logger.level)
    root_logger.handlers = []
    root_logger.setLevel(logging.WARNING)
    output = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        exit_status = engine_environment.main()
    return exit_status, output.getvalue()


class TheCheckEngineEnvironmentFunctionWhenTheWorkerImportsItsLibraries(unittest.TestCase):
    def setUp(self) -> None:
        self.check = check_engine_environment(SETTINGS, ScriptSpec(REPORTING))

    def test_should_pass(self) -> None:
        self.assertTrue(self.check.has_passed, self.check.output)

    def test_should_run_the_worker_in_its_check_mode(self) -> None:
        self.assertIn("['--check']", self.check.output.splitlines())

    def test_should_hide_the_gpu_so_that_the_check_never_takes_it_from_other_work(self) -> None:
        self.assertIn(HIDDEN_GPU_LINE, self.check.output.splitlines())


class TheCheckEngineEnvironmentFunctionWhenALibraryDoesNotImport(unittest.TestCase):
    def setUp(self) -> None:
        self.check = check_engine_environment(SETTINGS, ScriptSpec(MISSING_LIBRARY))

    def test_should_not_pass(self) -> None:
        self.assertFalse(self.check.has_passed)

    def test_should_show_the_error_of_the_worker(self) -> None:
        self.assertIn("ImportError: libGL.so.1", self.check.output)


class TheCheckEngineEnvironmentFunctionWhenTheWorkerNeverFinishes(unittest.TestCase):
    check: ClassVar[EnvironmentCheck]
    elapsed_seconds: ClassVar[float]
    is_child_process_gone: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        started_at_seconds = time.monotonic()
        cls.check = check_engine_environment(SETTINGS, ScriptSpec(NEVER_FINISHES), SHORT_TIMEOUT_SECONDS)
        cls.elapsed_seconds = time.monotonic() - started_at_seconds
        process_ids = read_process_ids(cls.check.output)
        cls.addClassCleanup(kill_if_running, process_ids["detached"])
        cls.is_child_process_gone = wait_until_gone(process_ids["child"])

    def test_should_not_pass(self) -> None:
        self.assertFalse(self.check.has_passed)

    def test_should_end_its_output_with_a_line_that_says_the_worker_did_not_finish_in_time(self) -> None:
        self.assertEqual(
            self.check.output.splitlines()[-1], f"the worker did not finish within {SHORT_TIMEOUT_SECONDS:g} s"
        )

    def test_should_stop_the_processes_the_worker_started_so_that_none_outlives_the_check(self) -> None:
        self.assertTrue(self.is_child_process_gone)

    def test_should_return_even_when_a_process_that_left_the_group_keeps_its_output_open(self) -> None:
        self.assertLess(self.elapsed_seconds, RETURN_BOUND_SECONDS)


class TheCheckEngineEnvironmentFunctionWhenTheWorkerPrintsMoreThanItsTail(unittest.TestCase):
    def setUp(self) -> None:
        self.lines = check_engine_environment(SETTINGS, ScriptSpec(LONG_OUTPUT)).output.splitlines()

    def test_should_keep_only_the_last_lines(self) -> None:
        self.assertEqual(len(self.lines), PRINTED_TAIL_LINES)
        self.assertEqual(self.lines[0], f"line {EXTRA_LINE_COUNT}")

    def test_should_cut_a_long_line(self) -> None:
        self.assertEqual(len(self.lines[-1]), PRINTED_LINE_CHARACTERS)


class TheCheckEngineEnvironmentFunctionWhenTheWorkerPrintsTerminalControls(unittest.TestCase):
    def setUp(self) -> None:
        self.output = check_engine_environment(SETTINGS, ScriptSpec(PRINTING_TERMINAL_CONTROLS)).output

    def test_should_escape_them_since_the_operator_runs_the_check_in_a_terminal(self) -> None:
        self.assertEqual(self.output, f"{ESCAPED_TERMINAL_CONTROLS}\n")


class TheCheckEngineEnvironmentFunctionWhenTheWorkerPrintsALongLineOfTerminalControls(unittest.TestCase):
    def setUp(self) -> None:
        self.output = check_engine_environment(SETTINGS, ScriptSpec(PRINTING_A_LONG_LINE_OF_TERMINAL_CONTROLS)).output

    def test_should_cut_it_between_two_escapes_so_that_none_reads_as_other_characters(self) -> None:
        self.assertEqual(self.output, f"{CUT_LINE_OF_TERMINAL_CONTROLS}\n")


class TheMainFunctionWhenTheCheckPasses(unittest.TestCase):
    def setUp(self) -> None:
        self.exit_status, self.output = run_main(self, ScriptSpec(LIBRARIES_IMPORT))

    def test_should_succeed(self) -> None:
        self.assertEqual(self.exit_status, 0)

    def test_should_print_each_line_of_the_worker_once(self) -> None:
        self.assertEqual(self.output.count(LIBRARIES_IMPORT_LINE), 1, self.output)


class TheMainFunctionWhenTheCheckFails(unittest.TestCase):
    def setUp(self) -> None:
        self.exit_status, self.output = run_main(self, ScriptSpec(MISSING_LIBRARY))

    def test_should_fail(self) -> None:
        self.assertEqual(self.exit_status, 1)

    def test_should_print_what_the_worker_printed(self) -> None:
        self.assertIn("ImportError: libGL.so.1", self.output)


if __name__ == "__main__":
    unittest.main()
