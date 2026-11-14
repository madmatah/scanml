"""Keeping a process's /proc entries from the other processes of the sandbox, which run as the same user.

Such a process could otherwise open ``/proc/<pid>/fd/2`` of the container's init or of the supervisor, which hold the
container's output, and write to ``docker logs`` past the escape of the supervisor's relay. A process that is not
dumpable has its /proc entries owned by root, and the kernel refuses to open its descriptors to anyone but itself. A
program that it executes becomes dumpable again: the processes that it starts never hold that output.
"""

from __future__ import annotations

import ctypes
import os

_PR_SET_DUMPABLE = 4  # include/uapi/linux/prctl.h
_NOT_DUMPABLE = 0


def stop_being_dumpable() -> None:
    c_library = ctypes.CDLL(None, use_errno=True)
    if c_library.prctl(_PR_SET_DUMPABLE, _NOT_DUMPABLE, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, f"prctl(PR_SET_DUMPABLE, 0): {os.strerror(error_number)}")
