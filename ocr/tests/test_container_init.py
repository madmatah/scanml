"""The init of the ocr container (ocr/scanmylib_ocr/container_init.py), run on commands that are scripts of a few lines.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import contextlib
import errno
import functools
import io
import os
import signal
import subprocess
import sys
import textwrap
import unittest
from collections.abc import Callable
from typing import IO, ClassVar, cast
from unittest import mock

import scanmylib_ocr
from scanmylib_ocr import container_init
from scanmylib_ocr.container_init import COMMAND_NOT_STARTED_EXIT_CODE, main, wait_for_command_exit

PACKAGE_PARENT_DIRECTORY = os.path.dirname(os.path.dirname(scanmylib_ocr.__file__))
# An upper bound for the init to end: reaching it means the test is broken, not slow.
EXIT_TIMEOUT_SECONDS = 10.0
READY_LINE = "ready"

COMMAND_EXIT_CODE = 3
EXITING = f"raise SystemExit({COMMAND_EXIT_CODE})\n"
KILLING_ITSELF = "import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n"
KILLED_EXIT_CODE = 128 + signal.SIGKILL

STOPPED_LINE = "stopped by SIGTERM"
STOPPING_ON_SIGTERM = textwrap.dedent(
    f"""
    import signal, sys, time
    def stop(received_signal, _frame):
        print(f"stopped by {{signal.Signals(received_signal).name}}", flush=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    print({READY_LINE!r}, flush=True)
    time.sleep(60)
    """
)
RUNNING = f"import time\nprint({READY_LINE!r}, flush=True)\ntime.sleep(60)\n"

COMMAND_PROCESS_ID = 100
FIRST_ORPHAN_PROCESS_ID = 200
SECOND_ORPHAN_PROCESS_ID = 300
EXITED_WITH_COMMAND_EXIT_CODE = COMMAND_EXIT_CODE << 8
USAGE_EXIT_CODE = 2
MISSING_COMMAND = "/nonexistent/scanmylib-supervisor"
REFUSED_PRCTL = OSError(errno.EPERM, "prctl(PR_SET_DUMPABLE, 0): Operation not permitted")


def start_init(script: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "scanmylib_ocr.container_init", sys.executable, "-c", script],
        cwd=PACKAGE_PARENT_DIRECTORY,
        stdout=subprocess.PIPE,
        text=True,
    )


def read_line(init: subprocess.Popen[str]) -> str:
    return cast(IO[str], init.stdout).readline().strip()


def stop_init(init: subprocess.Popen[str]) -> None:
    # Killed, the init would leave its command running, which holds the output that communicate() reads to its end.
    init.terminate()
    init.communicate(timeout=EXIT_TIMEOUT_SECONDS)


def build_waits(wait_results: list[tuple[int, int]]) -> tuple[Callable[[], tuple[int, int]], list[tuple[int, int]]]:
    remaining = list(wait_results)
    return lambda: remaining.pop(0), remaining


class TheMainFunctionWhenItsCommandExits(unittest.TestCase):
    exit_code: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        init = start_init(EXITING)
        cls.addClassCleanup(stop_init, init)
        init.communicate(timeout=EXIT_TIMEOUT_SECONDS)
        cls.exit_code = init.returncode

    def test_should_exit_with_its_command_s_exit_code_so_that_docker_reports_the_supervisor_s(self) -> None:
        self.assertEqual(self.exit_code, COMMAND_EXIT_CODE)


class TheMainFunctionWhenItsCommandIsKilledByASignal(unittest.TestCase):
    exit_code: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        init = start_init(KILLING_ITSELF)
        cls.addClassCleanup(stop_init, init)
        init.communicate(timeout=EXIT_TIMEOUT_SECONDS)
        cls.exit_code = init.returncode

    def test_should_exit_with_128_plus_the_signal_as_a_shell_reports_it(self) -> None:
        self.assertEqual(self.exit_code, KILLED_EXIT_CODE)


class TheMainFunctionWhenTheContainerIsStopped(unittest.TestCase):
    output: ClassVar[str]
    exit_code: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        init = start_init(STOPPING_ON_SIGTERM)
        cls.addClassCleanup(stop_init, init)
        ready_line = read_line(init)
        init.send_signal(signal.SIGTERM)
        remaining_output, _ = init.communicate(timeout=EXIT_TIMEOUT_SECONDS)
        cls.output = ready_line + "\n" + remaining_output
        cls.exit_code = init.returncode

    def test_should_pass_the_stop_to_its_command_so_that_the_supervisor_stops_the_engine_cleanly(self) -> None:
        self.assertIn(STOPPED_LINE, self.output)

    def test_should_exit_as_its_command_does(self) -> None:
        self.assertEqual(self.exit_code, 0)


@unittest.skipIf(os.geteuid() == 0, "root opens the descriptors of any process")
class TheMainFunctionWhenItsCommandRuns(unittest.TestCase):
    output_path: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        init = start_init(RUNNING)
        cls.addClassCleanup(stop_init, init)
        read_line(init)
        cls.output_path = f"/proc/{init.pid}/fd/1"

    def setUp(self) -> None:
        self.open_init_output = functools.partial(os.open, self.output_path, os.O_WRONLY | os.O_NONBLOCK)

    def test_should_keep_its_output_from_the_other_processes_of_its_user_so_that_none_writes_to_docker_logs(
        self,
    ) -> None:
        self.assertRaises(PermissionError, self.open_init_output)


class TheMainFunctionWhenGivenNoCommand(unittest.TestCase):
    exit_code: ClassVar[int]
    error_output: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        error_output = io.StringIO()
        with contextlib.redirect_stderr(error_output):
            cls.exit_code = main([])
        cls.error_output = error_output.getvalue()

    def test_should_fail_with_its_usage(self) -> None:
        self.assertEqual((self.exit_code, self.error_output.startswith("usage: ")), (USAGE_EXIT_CODE, True))


class TheMainFunctionWhenItsCommandCannotStart(unittest.TestCase):
    exit_code: ClassVar[int]
    error_output: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        init = subprocess.Popen(
            [sys.executable, "-m", "scanmylib_ocr.container_init", MISSING_COMMAND],
            cwd=PACKAGE_PARENT_DIRECTORY,
            stderr=subprocess.PIPE,
            text=True,
        )
        cls.addClassCleanup(init.kill)
        _, cls.error_output = init.communicate(timeout=EXIT_TIMEOUT_SECONDS)
        cls.exit_code = init.returncode

    def test_should_fail_and_say_which_command_it_could_not_start(self) -> None:
        self.assertEqual(
            (self.exit_code, f"cannot start {MISSING_COMMAND}" in self.error_output),
            (COMMAND_NOT_STARTED_EXIT_CODE, True),
        )


class TheMainFunctionWhenItCannotStopBeingDumpable(unittest.TestCase):
    exit_code: ClassVar[int]
    spawn: ClassVar[mock.MagicMock]

    @classmethod
    def setUpClass(cls) -> None:
        error_output = io.StringIO()
        with (
            mock.patch.object(container_init, "stop_being_dumpable", side_effect=REFUSED_PRCTL),
            mock.patch.object(os, "posix_spawnp") as spawn,
            contextlib.redirect_stderr(error_output),
        ):
            cls.exit_code = main([MISSING_COMMAND])
        cls.spawn = spawn

    def test_should_start_nothing_so_that_no_process_of_the_sandbox_can_reach_the_container_s_output(self) -> None:
        self.assertEqual((self.exit_code, self.spawn.call_count), (COMMAND_NOT_STARTED_EXIT_CODE, 0))


class TheWaitForCommandExitFunctionWhenOrphansExitBeforeItsCommand(unittest.TestCase):
    exit_code: ClassVar[int]
    waits_left: ClassVar[list[tuple[int, int]]]

    @classmethod
    def setUpClass(cls) -> None:
        wait_for_any_child, cls.waits_left = build_waits(
            [
                (FIRST_ORPHAN_PROCESS_ID, 0),
                (SECOND_ORPHAN_PROCESS_ID, 0),
                (COMMAND_PROCESS_ID, EXITED_WITH_COMMAND_EXIT_CODE),
            ]
        )
        cls.exit_code = wait_for_command_exit(COMMAND_PROCESS_ID, wait_for_any_child)

    def test_should_reap_each_of_them_so_that_no_zombie_fills_the_container_s_process_limit(self) -> None:
        self.assertEqual(self.waits_left, [])

    def test_should_return_its_command_s_exit_code(self) -> None:
        self.assertEqual(self.exit_code, COMMAND_EXIT_CODE)


if __name__ == "__main__":
    unittest.main()
