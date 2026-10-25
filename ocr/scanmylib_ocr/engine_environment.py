"""The check that the engine's environment imports its libraries.

``/health`` answers while the engine is idle, so nothing else runs the engine's environment before the first page.
Standard library only: it runs with the image's ``python3``, as the supervisor does.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from .config import Settings
from .engines import get_spec
from .engines.base import EngineSpec
from .printable_text import cut_escaped
from .runtime import ChildProcess

CHECK_TIMEOUT_SECONDS = 300.0
STOP_GRACE_SECONDS = 5.0
PRINTED_TAIL_LINES = 50
PRINTED_LINE_CHARACTERS = 500


@dataclass(frozen=True)
class EnvironmentCheck:
    has_passed: bool
    output: str


def check_engine_environment(
    settings: Settings, spec: EngineSpec, timeout_seconds: float = CHECK_TIMEOUT_SECONDS
) -> EnvironmentCheck:
    # An empty CUDA_VISIBLE_DEVICES hides the GPU, so that a check never takes it from other work.
    worker = ChildProcess(
        "worker-check", [*spec.worker_command(settings), "--check"], {**os.environ, "CUDA_VISIBLE_DEVICES": ""}
    )
    try:
        has_finished = worker.wait(timeout_seconds)
        exit_status = worker.returncode
    finally:
        worker.stop(STOP_GRACE_SECONDS)
    lines = [cut_escaped(line, PRINTED_LINE_CHARACTERS) for line in worker.output_tail()[-PRINTED_TAIL_LINES:]]
    if not has_finished:
        lines.append(f"the worker did not finish within {timeout_seconds:g} s")
    return EnvironmentCheck(has_passed=has_finished and exit_status == 0, output="".join(f"{line}\n" for line in lines))


def main() -> int:
    settings = Settings.from_env()
    check = check_engine_environment(settings, get_spec(settings.engine))
    print(check.output, end="")
    return 0 if check.has_passed else 1


if __name__ == "__main__":
    sys.exit(main())
