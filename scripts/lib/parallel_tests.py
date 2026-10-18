"""Runs the unittest tests of a directory in parallel processes, for scripts/check.sh.

The tests of the scripts spend their time starting processes, one after the other on a single core: shared out between
processes, one per core, they take the time of the slowest share. Each share runs in a process of its own, as
`python3 -m unittest` would run its tests. A run fails when a share fails, or when unittest reports fewer tests than the
share was given, so that a share that stops early never passes.

Standard library only:
    python3 scripts/lib/parallel_tests.py DIRECTORY
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import unittest
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# The summary that unittest writes last to its stderr; the tests' own output may hold lines of the same form.
_RAN_LINE = re.compile(r"^Ran (\d+) tests? in ", re.MULTILINE)
_SKIPPED_FIELD = re.compile(r"\bskipped=(\d+)")
_NO_TESTS_EXIT_CODE = 5


@dataclass(frozen=True)
class _ShareRun:
    test_ids: tuple[str, ...]
    exit_code: int
    printed: str
    report: str

    @property
    def run_count(self) -> int:
        counts = _RAN_LINE.findall(self.report)
        return int(counts[-1]) if counts else 0

    @property
    def skipped_count(self) -> int:
        counts = _SKIPPED_FIELD.findall(self.report)
        return int(counts[-1]) if counts else 0


class _DiscoveryFailed(ImportError):
    pass


def _iterate_tests(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _iterate_tests(test)
        elif isinstance(test, unittest.TestCase):
            yield test


def _list_test_ids(directory: Path) -> list[str]:
    loader = unittest.TestLoader()
    suite = loader.discover(str(directory), top_level_dir=str(directory))
    if loader.errors:
        # The loader keeps each import's traceback as text, where typeshed types the list as exceptions:
        # https://github.com/python/typeshed/blob/main/stdlib/unittest/loader.pyi
        raise _DiscoveryFailed("\n".join(str(error) for error in loader.errors))
    return [test.id() for test in _iterate_tests(suite)]


def share_out(test_ids: Sequence[str], process_count: int) -> list[tuple[str, ...]]:
    share_count = max(1, min(process_count, len(test_ids)))
    return [tuple(test_ids[index::share_count]) for index in range(share_count)]


def _run_share(directory: Path, test_ids: tuple[str, ...]) -> _ShareRun:
    unittest_run = subprocess.run(
        [sys.executable, "-m", "unittest", *test_ids],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    return _ShareRun(test_ids, unittest_run.returncode, unittest_run.stdout, unittest_run.stderr)


def _run_tests(directory: Path, process_count: int) -> int:
    started_seconds = time.monotonic()
    try:
        test_ids = _list_test_ids(directory)
    except _DiscoveryFailed as exc:
        print(f"cannot import the tests of {directory}:\n{exc}", file=sys.stderr)
        return 1
    if not test_ids:
        print(f"Ran 0 tests: {directory} holds none\n\nNO TESTS RAN", file=sys.stderr)
        return _NO_TESTS_EXIT_CODE
    shares = share_out(test_ids, process_count)
    with ThreadPoolExecutor(max_workers=len(shares)) as executor:
        share_runs = list(executor.map(lambda share: _run_share(directory, share), shares))
    failed_runs = [run for run in share_runs if run.exit_code != 0 or run.run_count != len(run.test_ids)]
    for share_run in failed_runs:
        shortfall = len(share_run.test_ids) - share_run.run_count
        unreported = f", {shortfall} of which unittest did not report" if shortfall else ""
        print(
            f"=== {len(share_run.test_ids)} tests{unreported}, among them {share_run.test_ids[0]}:\n"
            f"{share_run.printed}{share_run.report}",
            file=sys.stderr,
        )
    run_count = sum(share_run.run_count for share_run in share_runs)
    elapsed_seconds = time.monotonic() - started_seconds
    test_noun = "test" if run_count == 1 else "tests"
    process_noun = "process" if len(shares) == 1 else "processes"
    summary = f"Ran {run_count} {test_noun} in {elapsed_seconds:.3f}s, in {len(shares)} {process_noun}"
    print(f"{summary}\n", file=sys.stderr)
    if failed_runs:
        unreported_count = len(test_ids) - run_count
        unreported = f", {unreported_count} tests unreported" if unreported_count else ""
        print(f"FAILED ({len(failed_runs)} of {len(shares)} processes{unreported})", file=sys.stderr)
        return 1
    skipped_count = sum(share_run.skipped_count for share_run in share_runs)
    print("OK" if skipped_count == 0 else f"OK (skipped={skipped_count})", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Runs the unittest tests of a directory in parallel processes.")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--processes", type=int, default=os.cpu_count() or 1)
    arguments = parser.parse_args(argv)
    return _run_tests(arguments.directory.resolve(), arguments.processes)


if __name__ == "__main__":
    sys.exit(main())
