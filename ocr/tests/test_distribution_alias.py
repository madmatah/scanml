"""The alias distribution (ocr/setup/distribution_alias.py): the pin it reads, and the wheel it writes.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`. The module lives with the installer, outside the
package of the image the sandbox runs, so the tests load it by its path.
"""

from __future__ import annotations

import base64
import contextlib
import csv
import functools
import hashlib
import importlib.metadata
import importlib.util
import io
import sys
import tempfile
import unittest
import zipfile
from email.parser import Parser
from pathlib import Path
from types import ModuleType
from typing import ClassVar
from unittest import mock

DISTRIBUTION_ALIAS_PATH = Path(__file__).resolve().parents[1] / "setup" / "distribution_alias.py"


def load_distribution_alias() -> ModuleType:
    spec = importlib.util.spec_from_file_location("distribution_alias", DISTRIBUTION_ALIAS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {DISTRIBUTION_ALIAS_PATH}")
    module = importlib.util.module_from_spec(spec)
    # dataclasses reads the module of a class from sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


distribution_alias = load_distribution_alias()
AliasRefused = distribution_alias.AliasRefused
build_alias_wheel = distribution_alias.build_alias_wheel
main = distribution_alias.main
read_exact_pin = distribution_alias.read_exact_pin
write_wheel = distribution_alias.write_wheel

ALIAS = "opencv-contrib-python"
TARGET = "opencv-contrib-python-headless"
VERSION = "4.10.0.84"
OTHER_REQUIREMENTS = "# The engine.\npaddleocr[doc-parser]==3.7.0\nsafetensors\n"
DIST_INFO = f"opencv_contrib_python-{VERSION}.dist-info"
FIRST_WRITE_EPOCH_SECONDS = 1_700_000_000.0
SECOND_WRITE_EPOCH_SECONDS = FIRST_WRITE_EPOCH_SECONDS + 86_400


def make_directory(test: unittest.TestCase) -> Path:
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-alias-")
    test.addCleanup(directory.cleanup)
    return Path(directory.name)


def hash_for_record(content: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()


class TheReadExactPinFunctionWhenTheTargetIsPinnedToOneVersion(unittest.TestCase):
    requirements_by_row: ClassVar[dict[str, str]] = {
        "a pin alone": f"{OTHER_REQUIREMENTS}{TARGET}=={VERSION}\n",
        "a pin with a comment after it": f"{TARGET} == {VERSION}  # why this pin\n{OTHER_REQUIREMENTS}",
        "a pin next to the alias's own name": f"{ALIAS}==1.0\n{TARGET}=={VERSION}\n",
        "a pin whose name is written another way": f"OpenCV_Contrib.Python-Headless=={VERSION}\n",
    }

    def setUp(self) -> None:
        self.versions = {
            row: read_exact_pin(requirements, TARGET) for row, requirements in self.requirements_by_row.items()
        }

    def test_should_read_the_pinned_version(self) -> None:
        self.assertEqual(len(self.versions), len(self.requirements_by_row))
        for row, version in self.versions.items():
            with self.subTest(row):
                self.assertEqual(version, VERSION)


class TheReadExactPinFunctionWhenTheTargetIsNotPinnedToOneVersion(unittest.TestCase):
    refusals_by_row: ClassVar[dict[str, tuple[str, str]]] = {
        "no line names it": (OTHER_REQUIREMENTS, "found 0 pins"),
        "only a longer name starts with it": (f"{TARGET}-extra=={VERSION}\n", "found 0 pins"),
        "its pin is commented out": (f"# {TARGET}=={VERSION}\n", "found 0 pins"),
        "it is pinned twice": (f"{TARGET}=={VERSION}\n{TARGET}=={VERSION}\n", "found 2 pins"),
        "a range": (f"{TARGET}>=4.10\n", "not pinned to one version with =="),
        "a URL": (f"{TARGET} @ https://example.invalid/{TARGET}.whl\n", "not pinned to one version with =="),
        "a pin under a marker": (f"{TARGET}=={VERSION} ; python_version >= '3.12'\n", "not pinned to one version"),
        "a wildcard": (f"{TARGET}==4.10.*\n", "not a canonical public version"),
        "a version outside PEP 440": (f"{TARGET}==4.10/../x\n", "not a canonical public version"),
        "a local version": (f"{TARGET}=={VERSION}+local\n", "not a canonical public version"),
    }

    def setUp(self) -> None:
        self.reads = {
            row: functools.partial(read_exact_pin, requirements, TARGET)
            for row, (requirements, _) in self.refusals_by_row.items()
        }

    def test_should_refuse_it_so_that_the_alias_never_requires_another_version_than_ours(self) -> None:
        self.assertEqual(len(self.reads), len(self.refusals_by_row))
        for row, read in self.reads.items():
            with self.subTest(row):
                self.assertRaisesRegex(AliasRefused, self.refusals_by_row[row][1], read)


class TheBuildAliasWheelFunction(unittest.TestCase):
    def setUp(self) -> None:
        self.wheel = build_alias_wheel(ALIAS, TARGET, VERSION)
        contents: dict[str, bytes] = {file.path: file.content for file in self.wheel.files}
        self.metadata = Parser().parsestr(contents[f"{DIST_INFO}/METADATA"].decode())
        record = contents[f"{DIST_INFO}/RECORD"].decode()
        self.records = {row[0]: (row[1], row[2]) for row in csv.reader(io.StringIO(record))}
        self.hashed_files = {
            file.path: (hash_for_record(file.content), str(len(file.content)))
            for file in self.wheel.files
            if file.path != f"{DIST_INFO}/RECORD"
        }

    def test_should_name_its_file_after_the_alias_and_the_version_for_every_python(self) -> None:
        self.assertEqual(self.wheel.file_name, f"opencv_contrib_python-{VERSION}-py3-none-any.whl")

    def test_should_hold_only_the_metadata_of_a_distribution_and_no_code(self) -> None:
        self.assertEqual(
            [file.path for file in self.wheel.files],
            [f"{DIST_INFO}/METADATA", f"{DIST_INFO}/WHEEL", f"{DIST_INFO}/RECORD"],
        )

    def test_should_install_under_the_alias_s_name_at_the_target_s_version(self) -> None:
        self.assertEqual((self.metadata["Name"], self.metadata["Version"]), (ALIAS, VERSION))

    def test_should_require_the_target_at_that_version_alone(self) -> None:
        self.assertEqual(self.metadata.get_all("Requires-Dist"), [f"{TARGET}=={VERSION}"])

    def test_should_record_the_hash_and_the_size_of_each_other_file_so_that_an_installer_accepts_it(self) -> None:
        self.assertEqual(self.records, {**self.hashed_files, f"{DIST_INFO}/RECORD": ("", "")})


class TheBuildAliasWheelFunctionWhenANameOrTheVersionCouldReachAPath(unittest.TestCase):
    refusals_by_row: ClassVar[dict[str, tuple[tuple[str, str, str], str]]] = {
        "an alias with a separator": (("../opencv", TARGET, VERSION), "not a distribution name"),
        "a target with a blank": ((ALIAS, "opencv headless", VERSION), "not a distribution name"),
        "a version with a separator": ((ALIAS, TARGET, "4.10/../x"), "not a canonical public version"),
    }

    def setUp(self) -> None:
        self.builds = {
            row: functools.partial(build_alias_wheel, *arguments)
            for row, (arguments, _) in self.refusals_by_row.items()
        }

    def test_should_refuse_it(self) -> None:
        self.assertEqual(len(self.builds), len(self.refusals_by_row))
        for row, build in self.builds.items():
            with self.subTest(row):
                self.assertRaisesRegex(AliasRefused, self.refusals_by_row[row][1], build)


class TheWriteWheelFunction(unittest.TestCase):
    def setUp(self) -> None:
        directory = make_directory(self)
        wheel_path = write_wheel(build_alias_wheel(ALIAS, TARGET, VERSION), directory / "alias")
        unpacked = directory / "unpacked"
        with zipfile.ZipFile(wheel_path) as archive:
            archive.extractall(unpacked)
        distribution = next(iter(importlib.metadata.distributions(name=ALIAS, path=[str(unpacked)])))
        self.installed_version = distribution.version

    def test_should_write_a_wheel_whose_unpacked_metadata_gives_the_alias_the_target_s_version(self) -> None:
        self.assertEqual(self.installed_version, VERSION)


class TheWriteWheelFunctionWhenItWritesTheSameAliasTwice(unittest.TestCase):
    def setUp(self) -> None:
        directory = make_directory(self)
        wheel = build_alias_wheel(ALIAS, TARGET, VERSION)
        with mock.patch("time.time", return_value=FIRST_WRITE_EPOCH_SECONDS):
            self.first_wheel_bytes = write_wheel(wheel, directory / "first").read_bytes()
        with mock.patch("time.time", return_value=SECOND_WRITE_EPOCH_SECONDS):
            self.second_wheel_bytes = write_wheel(wheel, directory / "second").read_bytes()

    def test_should_write_the_same_bytes_so_that_the_same_alias_is_the_same_file(self) -> None:
        self.assertEqual(self.first_wheel_bytes, self.second_wheel_bytes)


class TheMainFunctionWhenTheRequirementsPinTheTarget(unittest.TestCase):
    def setUp(self) -> None:
        directory = make_directory(self)
        requirements = directory / "requirements.in"
        requirements.write_text(f"{OTHER_REQUIREMENTS}{TARGET}=={VERSION}\n")
        self.output = directory / "alias"
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.exit_status = main([
                "--requirements", str(requirements), "--alias", ALIAS, "--target", TARGET, "--output", str(self.output),
            ])  # fmt: skip
        self.printed_path = printed.getvalue().strip()
        self.written_paths = sorted(str(path) for path in self.output.iterdir())

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.exit_status, 0)

    def test_should_print_the_path_of_the_wheel_it_wrote_for_the_installer_to_install(self) -> None:
        self.assertEqual([self.printed_path], self.written_paths)


class TheMainFunctionWhenTheRequirementsDoNotPinTheTarget(unittest.TestCase):
    def setUp(self) -> None:
        directory = make_directory(self)
        requirements = directory / "requirements.in"
        requirements.write_text(OTHER_REQUIREMENTS)
        output = directory / "alias"
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            self.exit_status = main(
                ["--requirements", str(requirements), "--alias", ALIAS, "--target", TARGET, "--output", str(output)]
            )
        self.error_text = errors.getvalue()
        self.is_output_written = output.exists()

    def test_should_fail_so_that_the_installation_stops(self) -> None:
        self.assertNotEqual(self.exit_status, 0)

    def test_should_say_why(self) -> None:
        self.assertIn(f"{TARGET} must be pinned once", self.error_text)

    def test_should_write_no_wheel(self) -> None:
        self.assertFalse(self.is_output_written)


class TheMainFunctionWhenTheRequirementsFileCannotBeRead(unittest.TestCase):
    def setUp(self) -> None:
        directory = make_directory(self)
        self.requirements = directory / "missing-requirements.in"
        output = directory / "alias"
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
            self.exit_status = main([
                "--requirements", str(self.requirements), "--alias", ALIAS, "--target", TARGET, "--output", str(output),
            ])  # fmt: skip
        self.error_text = errors.getvalue()
        self.is_output_written = output.exists()

    def test_should_fail_so_that_the_installation_stops(self) -> None:
        self.assertNotEqual(self.exit_status, 0)

    def test_should_say_which_file_it_cannot_read(self) -> None:
        self.assertIn(str(self.requirements), self.error_text)

    def test_should_write_no_wheel(self) -> None:
        self.assertFalse(self.is_output_written)


if __name__ == "__main__":
    unittest.main()
