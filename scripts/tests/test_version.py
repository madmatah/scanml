"""The versions of releases and development builds (scripts/lib/version.py).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import functools
import io
import sys
import tempfile
import types
import unittest
from collections.abc import Mapping
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from git_environment import isolated_git_environment, read_head, run_git

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import version

RELEASE = (0, 2, 3)
NOW = datetime(2026, 10, 17, 10, 0, 50, tzinfo=UTC)
MINUTES_FROM_THE_EPOCH_TO_NOW = 416_760


def make_directory(test_case: type[unittest.TestCase]) -> Path:
    return Path(test_case.enterClassContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-")))


def make_released_repository(test_case: type[unittest.TestCase]) -> Path:
    repository = make_directory(test_case)
    run_git(repository, "init", "--quiet", "--initial-branch=main")
    (repository / "VERSION").write_text("0.2.3\n")
    run_git(repository, "add", "VERSION")
    run_git(repository, "commit", "--quiet", "--message", "chore(release): 0.2.3")
    return repository


def commit_nothing(repository: Path, message: str) -> None:
    run_git(repository, "commit", "--quiet", "--allow-empty", "--message", message)


class TheParseReleaseFunctionWhenTheTextIsAVersion(unittest.TestCase):
    def setUp(self) -> None:
        self.release = version.parse_release("0.2.3\n")

    def test_should_read_its_major_minor_and_patch_numbers(self) -> None:
        self.assertEqual(self.release, (0, 2, 3))


class TheParseReleaseFunctionWhenTheTextIsNoVersion(unittest.TestCase):
    texts: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {
            "two numbers": "0.2",
            "four numbers": "0.2.3.4",
            "a tag": "v0.2.3",
            "a minor version of 100": "0.100.0",
            "a patch of 100": "0.2.100",
            "a major version of 1000": "1000.0.0",
            "a leading zero": "0.02.3",
            "a pre-release": "0.2.3-dev",
            "a digit outside ASCII": "\N{ARABIC-INDIC DIGIT ONE}.2.3",
            "an empty text": "",
            "two versions": "0.2.3 0.2.4",
        }
    )

    def setUp(self) -> None:
        self.parsing_acts = {row: functools.partial(version.parse_release, text) for row, text in self.texts.items()}

    def test_should_refuse_it_saying_what_form_a_version_takes(self) -> None:
        for row in self.texts:
            with self.subTest(row):
                self.assertRaisesRegex(
                    ValueError,
                    r"^VERSION must be MAJOR\.MINOR\.PATCH, minor and patch below 100, not ",
                    self.parsing_acts[row],
                )


class TheReleaseCodeFunction(unittest.TestCase):
    def setUp(self) -> None:
        self.codes = {release: version.release_code(release) for release in [(0, 2, 3), (1, 10, 0)]}

    def test_should_be_major_times_10000_plus_minor_times_100_plus_patch_so_that_each_release_installs_over_the_last(
        self,
    ) -> None:
        self.assertEqual(self.codes, {(0, 2, 3): 203, (1, 10, 0): 11000})


class TheFormatReleaseFunction(unittest.TestCase):
    def setUp(self) -> None:
        self.text = version.format_release((12, 0, 99))

    def test_should_join_major_minor_and_patch_with_dots(self) -> None:
        self.assertEqual(self.text, "12.0.99")


class TheDevVersionFunctionWhenTheReleaseHasNoTag(unittest.TestCase):
    head: ClassVar[str]
    dev_version: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_released_repository(cls)
        cls.head = read_head(repository)
        with isolated_git_environment():
            cls.dev_version = version.dev_version(repository, RELEASE)

    def test_should_be_a_pre_release_of_the_next_patch_at_its_commit_without_a_count_as_in_a_shallow_clone(
        self,
    ) -> None:
        self.assertEqual(self.dev_version, f"0.2.4-dev+g{self.head[:12]}")


class TheDevVersionFunctionWhenTheReleaseIsTaggedOnTheCommit(unittest.TestCase):
    head: ClassVar[str]
    dev_version: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_released_repository(cls)
        run_git(repository, "tag", "--annotate", "v0.2.3", "--message", "ScanMyLib 0.2.3")
        cls.head = read_head(repository)
        with isolated_git_environment():
            cls.dev_version = version.dev_version(repository, RELEASE)

    def test_should_count_no_commit_since_the_release(self) -> None:
        self.assertEqual(self.dev_version, f"0.2.4-dev.0+g{self.head[:12]}")


class TheDevVersionFunctionWhenCommitsFollowTheTagOfTheRelease(unittest.TestCase):
    head: ClassVar[str]
    dev_version: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_released_repository(cls)
        run_git(repository, "tag", "--annotate", "v0.2.3", "--message", "ScanMyLib 0.2.3")
        commit_nothing(repository, "feat: one")
        commit_nothing(repository, "fix: two")
        cls.head = read_head(repository)
        with isolated_git_environment():
            cls.dev_version = version.dev_version(repository, RELEASE)

    def test_should_count_the_commits_since_the_release(self) -> None:
        self.assertEqual(self.dev_version, f"0.2.4-dev.2+g{self.head[:12]}")


class TheDevVersionFunctionWhenAFileIsUntracked(unittest.TestCase):
    head: ClassVar[str]
    dev_version: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_released_repository(cls)
        (repository / "untracked.txt").write_text("not part of the build's version\n")
        cls.head = read_head(repository)
        with isolated_git_environment():
            cls.dev_version = version.dev_version(repository, RELEASE)

    def test_should_not_call_the_version_dirty_since_the_file_is_no_part_of_the_build(self) -> None:
        self.assertEqual(self.dev_version, f"0.2.4-dev+g{self.head[:12]}")


class TheDevVersionFunctionWhenATrackedFileIsChanged(unittest.TestCase):
    head: ClassVar[str]
    dev_version: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_released_repository(cls)
        (repository / "VERSION").write_text("0.2.3\n\n")
        cls.head = read_head(repository)
        with isolated_git_environment():
            cls.dev_version = version.dev_version(repository, RELEASE)

    def test_should_call_the_version_dirty(self) -> None:
        self.assertEqual(self.dev_version, f"0.2.4-dev+g{self.head[:12]}.dirty")


class TheDevVersionFunctionWhenTheDirectoryIsNoCheckout(unittest.TestCase):
    def setUp(self) -> None:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-")))
        with isolated_git_environment():
            self.dev_version = version.dev_version(directory, RELEASE)

    def test_should_be_the_next_patch_alone(self) -> None:
        self.assertEqual(self.dev_version, "0.2.4-dev")


class TheDevCodeFunctionWhenNoBuildIsPublished(unittest.TestCase):
    def setUp(self) -> None:
        epoch = version.DEV_CODE_EPOCH
        self.code_after_a_minute_and_59_seconds = version.dev_code(epoch + timedelta(minutes=1, seconds=59))
        self.code_on_october_17 = version.dev_code(datetime(2026, 10, 17, tzinfo=UTC))
        self.code_at_the_end_of_2026 = version.dev_code(datetime(2026, 12, 31, 23, 59, tzinfo=UTC))
        self.code_at_the_start_of_2027 = version.dev_code(datetime(2027, 1, 1, tzinfo=UTC))

    def test_should_count_whole_minutes_only(self) -> None:
        self.assertEqual(self.code_after_a_minute_and_59_seconds, 1)

    def test_should_count_the_minutes_since_the_start_of_2026(self) -> None:
        self.assertEqual(self.code_on_october_17, 416_160)

    def test_should_keep_growing_into_the_next_year(self) -> None:
        self.assertGreater(self.code_at_the_start_of_2027, self.code_at_the_end_of_2026)


class TheDevCodeFunctionWhenTheClockIsOutsideItsRange(unittest.TestCase):
    def setUp(self) -> None:
        epoch = version.DEV_CODE_EPOCH
        clocks = {
            "at the epoch": epoch,
            "a day before the epoch": epoch - timedelta(days=1),
            "past the largest versionCode": epoch + timedelta(minutes=version.MAX_VERSION_CODE + 1),
        }
        self.coding_acts = {row: functools.partial(version.dev_code, clock) for row, clock in clocks.items()}

    def test_should_refuse_it_since_no_dev_version_code_exists_then(self) -> None:
        for row, coding_act in self.coding_acts.items():
            with self.subTest(row):
                self.assertRaisesRegex(ValueError, "^the clock says .*: no dev versionCode then$", coding_act)


class TheDevCodeFunctionWhenThePublishedCodeIsBelowTheTime(unittest.TestCase):
    def setUp(self) -> None:
        self.code = version.dev_code(NOW, MINUTES_FROM_THE_EPOCH_TO_NOW - 5)

    def test_should_be_the_time(self) -> None:
        self.assertEqual(self.code, MINUTES_FROM_THE_EPOCH_TO_NOW)


class TheDevCodeFunctionWhenThePublishedCodeIsTheTime(unittest.TestCase):
    def setUp(self) -> None:
        self.code = version.dev_code(NOW, MINUTES_FROM_THE_EPOCH_TO_NOW)

    def test_should_be_one_above_so_that_a_second_build_in_the_same_minute_installs_over_the_first(self) -> None:
        self.assertEqual(self.code, MINUTES_FROM_THE_EPOCH_TO_NOW + 1)


class TheDevCodeFunctionWhenThePublishedCodeIsAheadOfTheTime(unittest.TestCase):
    def setUp(self) -> None:
        self.code = version.dev_code(NOW, MINUTES_FROM_THE_EPOCH_TO_NOW + 7)

    def test_should_be_one_above_the_published_code_so_that_the_build_installs_over_it(self) -> None:
        self.assertEqual(self.code, MINUTES_FROM_THE_EPOCH_TO_NOW + 8)


class TheDevCodeFunctionWhenThePublishedCodeIsTheLargestAndroidAccepts(unittest.TestCase):
    def setUp(self) -> None:
        self.compute_code = functools.partial(version.dev_code, NOW, version.MAX_VERSION_CODE)

    def test_should_refuse_since_no_version_code_is_left_above_it(self) -> None:
        self.assertRaisesRegex(ValueError, "^no versionCode above 2100000000 is left$", self.compute_code)


class ThePublishedCodeFunctionWhenTheMetadataHoldsAVersionCode(unittest.TestCase):
    def setUp(self) -> None:
        metadata = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-"))) / "scanmylib.json"
        metadata.write_text('{"version_code": 416760}')
        self.code = version.published_code(metadata)

    def test_should_read_it(self) -> None:
        self.assertEqual(self.code, 416_760)


class ThePublishedCodeFunctionWhenTheMetadataHoldsNoVersionCodeThatHoldsUp(unittest.TestCase):
    metadata_texts: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {
            "a code written as text": '{"version_code": "416760"}',
            "a code that is a boolean": '{"version_code": true}',
            "a list": "[1]",
            "a text that is no JSON": "not json",
        }
    )

    def setUp(self) -> None:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-")))
        self.codes: dict[str, int | None] = {}
        for index, (row, text) in enumerate(self.metadata_texts.items()):
            metadata = directory / f"scanmylib-{index}.json"
            metadata.write_text(text)
            self.codes[row] = version.published_code(metadata)

    def test_should_find_none(self) -> None:
        for row in self.metadata_texts:
            with self.subTest(row):
                self.assertIsNone(self.codes[row])


class ThePublishedCodeFunctionWhenTheMetadataIsMissing(unittest.TestCase):
    def setUp(self) -> None:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-")))
        self.code = version.published_code(directory / "missing.json")

    def test_should_find_none(self) -> None:
        self.assertIsNone(self.code)


class TheMainFunctionWhenAskedForTheRelease(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-")))
        (root / "VERSION").write_text("0.2.3\n")
        output = io.StringIO()
        with redirect_stdout(output):
            self.exit_code = version.main(["release", str(root)])
        self.printed = output.getvalue()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.exit_code, 0)

    def test_should_print_the_version_and_its_version_code(self) -> None:
        self.assertEqual(self.printed, "0.2.3 203\n")


class TheMainFunctionWhenAskedForADevelopmentBuild(unittest.TestCase):
    exit_code: ClassVar[int]
    printed: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_released_repository(cls)
        output = io.StringIO()
        with isolated_git_environment(), redirect_stdout(output):
            cls.exit_code = version.main(["dev", str(repository)])
        cls.printed = output.getvalue()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.exit_code, 0)

    def test_should_print_the_version_of_the_build_and_its_version_code(self) -> None:
        self.assertRegex(self.printed, r"^0\.2\.4-dev\+g[0-9a-f]{12} [0-9]+\n$")


class TheMainFunctionWhenAskedForADevelopmentBuildAboveAPublishedOne(unittest.TestCase):
    exit_code: ClassVar[int]
    printed: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_released_repository(cls)
        metadata = repository / "scanmylib.json"
        metadata.write_text('{"version_code": 2000000000}')
        output = io.StringIO()
        with isolated_git_environment(), redirect_stdout(output):
            cls.exit_code = version.main(["dev", str(repository), str(metadata)])
        cls.printed = output.getvalue()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.exit_code, 0)

    def test_should_print_a_version_code_above_the_published_one(self) -> None:
        self.assertTrue(self.printed.endswith(" 2000000001\n"), self.printed)


class TheMainFunctionWhenVersionIsMalformed(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-")))
        (root / "VERSION").write_text("0.2\n")
        errors = io.StringIO()
        with redirect_stderr(errors):
            self.exit_code = version.main(["dev", str(root)])
        self.error_text = errors.getvalue()

    def test_should_refuse_saying_what_form_a_version_takes(self) -> None:
        self.assertEqual(self.exit_code, 1)
        self.assertIn("MAJOR.MINOR.PATCH", self.error_text)


class TheMainFunctionWhenTheCommandIsUnknown(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-version-")))
        errors = io.StringIO()
        with redirect_stderr(errors):
            self.exit_code = version.main(["next", str(root)])
        self.error_text = errors.getvalue()

    def test_should_refuse_printing_its_usage(self) -> None:
        self.assertEqual(self.exit_code, 2)
        self.assertIn("Usage: version.py release ROOT", self.error_text)


if __name__ == "__main__":
    unittest.main()
