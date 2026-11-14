"""Docker's own init (``init: true``) holds the container's output too, and is dumpable: a process of the sandbox, which
runs as the same user, could open its descriptors in /proc and write to ``docker logs`` past the escape of the
supervisor's relay, so the ``ocr`` container runs this one, which stops being dumpable before it starts anything.
Standard library only: it runs with the image's ``python3``, as the supervisor does.

Usage (the container's command): ``python3 -m scanmylib_ocr.container_init COMMAND [ARGUMENT...]``
"""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Callable
from types import FrameType

from .adapters.dumpable import stop_being_dumpable

FORWARDED_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT, signal.SIGUSR1, signal.SIGUSR2)
COMMAND_NOT_STARTED_EXIT_CODE = 127
SIGNAL_EXIT_CODE_BASE = 128
USAGE_EXIT_CODE = 2


def wait_for_command_exit(
    command_process_id: int, wait_for_any_child: Callable[[], tuple[int, int]] = lambda: os.waitpid(-1, 0)
) -> int:
    """Process 1 inherits every orphan of the container, which stays a zombie until it is reaped."""
    while True:
        child_process_id, wait_status = wait_for_any_child()
        if child_process_id == command_process_id:
            exit_code = os.waitstatus_to_exitcode(wait_status)
            return exit_code if exit_code >= 0 else SIGNAL_EXIT_CODE_BASE - exit_code


def main(command: list[str]) -> int:
    if not command:
        print("usage: python3 -m scanmylib_ocr.container_init COMMAND [ARGUMENT...]", file=sys.stderr)
        return USAGE_EXIT_CODE
    try:
        stop_being_dumpable()
    except OSError as exc:
        print(f"container_init: {exc.strerror}", file=sys.stderr)
        return COMMAND_NOT_STARTED_EXIT_CODE
    # Blocked until the handlers know the command's pid, so that a stop that comes meanwhile reaches it.
    signal.pthread_sigmask(signal.SIG_BLOCK, FORWARDED_SIGNALS)
    try:
        command_process_id = os.posix_spawnp(command[0], command, os.environ, setsigmask=())
    except OSError as exc:
        print(f"container_init: cannot start {command[0]}: {exc.strerror}", file=sys.stderr)
        return COMMAND_NOT_STARTED_EXIT_CODE

    def forward(received_signal: int, _frame: FrameType | None) -> None:
        try:
            os.kill(command_process_id, received_signal)
        except ProcessLookupError:
            pass

    for forwarded_signal in FORWARDED_SIGNALS:
        signal.signal(forwarded_signal, forward)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, FORWARDED_SIGNALS)
    return wait_for_command_exit(command_process_id)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
