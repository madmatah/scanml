"""The parallel test runner of the gate (scripts/lib/parallel_tests.py).

Standard library only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import parallel_tests

RUNNER = Path(__file__).resolve().parent.parent / "lib" / "parallel_tests.py"
# Each test leaves a file named after the process that ran it, so that the run shows how many processes it used.
PASSING_TESTS = """
import os
import unittest
from pathlib import Path


class Pages(unittest.TestCase):
    def test_first(self) -> None:
        Path("processes", str(os.getpid())).touch()

    def test_second(self) -> None:
        Path("processes", str(os.getpid())).touch()

    def test_third(self) -> None:
        Path("processes", str(os.getpid())).touch()

    def test_fourth(self) -> None:
        Path("processes", str(os.getpid())).touch()
"""


@dataclass(frozen=True)
class RunnerRun:
    exit_code: int
    report: str
    process_count: int
    class_setup_count: int


def run_the_runner(test_files: dict[str, str], process_count: int) -> RunnerRun:
    with tempfile.TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)
        (directory / "processes").mkdir()
        (directory / "setups").mkdir()
        for name, text in test_files.items():
            (directory / name).write_text(text)
        runner_process = subprocess.run(
            [sys.executable, str(RUNNER), str(directory), "--processes", str(process_count)],
            capture_output=True,
            text=True,
            check=False,
        )
        used_process_count = len(list((directory / "processes").iterdir()))
        class_setup_count = len(list((directory / "setups").iterdir()))
    return RunnerRun(runner_process.returncode, runner_process.stderr, used_process_count, class_setup_count)


class TheMainFunctionWhenEveryTestPasses(unittest.TestCase):
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        cls.runner_run = run_the_runner({"test_pages.py": PASSING_TESTS}, process_count=2)

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.runner_run.exit_code, 0, self.runner_run.report)

    def test_should_report_every_test_it_ran(self) -> None:
        self.assertIn("Ran 4 tests in ", self.runner_run.report)

    def test_should_spread_a_class_whose_tests_each_set_up_their_own_over_the_processes_it_is_given(self) -> None:
        self.assertEqual(self.runner_run.process_count, 2, self.runner_run.report)


class TheMainFunctionWhenATestFails(unittest.TestCase):
    failing_test: ClassVar[str] = """
import unittest


class Pages(unittest.TestCase):
    def test_count(self) -> None:
        self.fail("the page count is wrong")
"""
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        test_files = {"test_pages.py": PASSING_TESTS, "test_count.py": cls.failing_test}
        cls.runner_run = run_the_runner(test_files, process_count=2)

    def test_should_exit_with_one(self) -> None:
        self.assertEqual(self.runner_run.exit_code, 1, self.runner_run.report)

    def test_should_show_the_failure_with_its_message(self) -> None:
        self.assertIn("AssertionError: the page count is wrong", self.runner_run.report)


class TheMainFunctionWhenATestIsSkipped(unittest.TestCase):
    skipped_test: ClassVar[str] = """
import unittest


class Pages(unittest.TestCase):
    @unittest.skip("needs a scanner")
    def test_scan(self) -> None:
        pass
"""
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        test_files = {"test_pages.py": PASSING_TESTS, "test_scan.py": cls.skipped_test}
        cls.runner_run = run_the_runner(test_files, process_count=2)

    def test_should_count_it_among_the_skipped_tests_so_that_the_report_says_what_did_not_run(self) -> None:
        self.assertIn("OK (skipped=1)", self.runner_run.report)


class TheMainFunctionWhenATestPrintsWhatUnittestPrints(unittest.TestCase):
    printing_test: ClassVar[str] = """
import sys
import unittest


class Pages(unittest.TestCase):
    def test_report(self) -> None:
        print("\\nRan 1 test in 0.001s", file=sys.stderr)
"""
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        test_files = {"test_pages.py": PASSING_TESTS, "test_report.py": cls.printing_test}
        cls.runner_run = run_the_runner(test_files, process_count=1)

    def test_should_count_the_tests_from_unittest_s_own_summary_so_that_a_test_s_output_never_fails_the_run(
        self,
    ) -> None:
        self.assertEqual(self.runner_run.exit_code, 0, self.runner_run.report)


class TheMainFunctionWhenAProcessEndsBeforeUnittestReports(unittest.TestCase):
    stopping_test: ClassVar[str] = """
import os
import unittest


class Pages(unittest.TestCase):
    def test_stop(self) -> None:
        os._exit(0)
"""
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        test_files = {"test_pages.py": PASSING_TESTS, "test_stop.py": cls.stopping_test}
        cls.runner_run = run_the_runner(test_files, process_count=1)

    def test_should_exit_with_one_so_that_tests_unittest_never_reported_never_pass(self) -> None:
        self.assertEqual(self.runner_run.exit_code, 1, self.runner_run.report)

    def test_should_say_how_many_tests_unittest_did_not_report(self) -> None:
        self.assertIn("FAILED (1 of 1 processes, 5 tests unreported)", self.runner_run.report)


class TheMainFunctionWhenAModuleCannotBeImported(unittest.TestCase):
    broken_module: ClassVar[str] = """
import a_module_that_does_not_exist
"""
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        test_files = {"test_pages.py": PASSING_TESTS, "test_broken.py": cls.broken_module}
        cls.runner_run = run_the_runner(test_files, process_count=2)

    def test_should_exit_with_one_so_that_a_broken_module_never_passes_unnoticed(self) -> None:
        self.assertEqual(self.runner_run.exit_code, 1, self.runner_run.report)

    def test_should_name_the_module_it_could_not_import(self) -> None:
        self.assertIn("test_broken", self.runner_run.report)


class TheMainFunctionWhenTheDirectoryHoldsNoTest(unittest.TestCase):
    unittest_exit_code_without_tests: ClassVar[int] = 5
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        cls.runner_run = run_the_runner({}, process_count=2)

    def test_should_exit_as_unittest_does_so_that_an_emptied_test_directory_fails_the_gate(self) -> None:
        self.assertEqual(self.runner_run.exit_code, self.unittest_exit_code_without_tests, self.runner_run.report)


class TheMainFunctionWhenAClassInheritsASetupFromTheBaseOfItsSituation(unittest.TestCase):
    stocked_shelves_tests: ClassVar[str] = """
import unittest
import uuid
from pathlib import Path


class _ShelvesWhenStocked(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Path("setups", uuid.uuid4().hex).touch()


class ShelvesWhenStocked(_ShelvesWhenStocked):
    def test_first(self) -> None:
        pass

    def test_second(self) -> None:
        pass

    def test_third(self) -> None:
        pass

    def test_fourth(self) -> None:
        pass
"""
    runner_run: ClassVar[RunnerRun]

    @classmethod
    def setUpClass(cls) -> None:
        cls.runner_run = run_the_runner({"test_shelves.py": cls.stocked_shelves_tests}, process_count=4)

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.runner_run.exit_code, 0, self.runner_run.report)

    def test_should_run_every_test_of_the_class(self) -> None:
        self.assertIn("Ran 4 tests in ", self.runner_run.report)

    def test_should_run_the_setup_once_so_that_a_costly_act_runs_once(self) -> None:
        self.assertEqual(self.runner_run.class_setup_count, 1, self.runner_run.report)


class TheShareOutFunctionWhenOneGroupHoldsMoreTestsThanTheOthers(unittest.TestCase):
    test_groups: ClassVar[tuple[tuple[str, ...], ...]] = (
        ("test_library.Pages.test_first", "test_library.Pages.test_second", "test_library.Pages.test_third"),
        ("test_library.Covers.test_first",),
        ("test_library.Spines.test_first",),
        ("test_library.Shelves.test_first",),
    )

    def setUp(self) -> None:
        process_count = 2
        self.shares = parallel_tests.share_out(self.test_groups, process_count)

    def test_should_give_each_group_whole_to_one_process_so_that_the_setup_of_its_class_runs_once(self) -> None:
        shares_holding_each_group = [
            sum(set(group) <= set(share) for share in self.shares) for group in self.test_groups
        ]
        self.assertEqual(shares_holding_each_group, [1, 1, 1, 1])

    def test_should_deal_the_groups_out_in_turn_since_a_group_costs_about_one_act_whatever_its_number_of_tests(
        self,
    ) -> None:
        group_indexes_of_each_share = [
            [index for index, group in enumerate(self.test_groups) if set(group) <= set(share)] for share in self.shares
        ]
        self.assertEqual(group_indexes_of_each_share, [[0, 2], [1, 3]])


class TheShareOutFunctionWhenAProcessTakesTheGroupsOfSeveralModules(unittest.TestCase):
    def setUp(self) -> None:
        test_groups = [
            ("test_covers.Covers.test_first",),
            ("test_pages.Pages.test_first", "test_pages.Pages.test_second"),
            ("test_pages.Spines.test_first",),
        ]
        process_count = 1
        self.shares = parallel_tests.share_out(test_groups, process_count)

    def test_should_keep_the_order_they_were_found_in_so_that_the_setup_of_each_module_runs_once_in_the_process(
        self,
    ) -> None:
        self.assertEqual(
            self.shares,
            [
                (
                    "test_covers.Covers.test_first",
                    "test_pages.Pages.test_first",
                    "test_pages.Pages.test_second",
                    "test_pages.Spines.test_first",
                )
            ],
        )


class TheShareOutFunctionWhenThereAreFewerGroupsThanProcesses(unittest.TestCase):
    def setUp(self) -> None:
        test_groups = [("test_library.Pages.test_first",), ("test_library.Covers.test_first",)]
        process_count = 8
        self.shares = parallel_tests.share_out(test_groups, process_count)

    def test_should_start_no_process_without_a_test(self) -> None:
        self.assertEqual(self.shares, [("test_library.Pages.test_first",), ("test_library.Covers.test_first",)])


if __name__ == "__main__":
    unittest.main()
