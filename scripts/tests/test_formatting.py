"""What scripts/check.sh hands to its formatters and linters, and what comes back from the copy
(scripts/lib/formatting.py).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import contextlib
import functools
import os
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from unittest import mock

from git_environment import build_git_environment, run_git

FORMATTING = Path(__file__).resolve().parent.parent / "lib" / "formatting.py"
sys.path.insert(0, str(FORMATTING.parent))
import formatting  # noqa: E402 (scripts/lib/formatting.py, found once scripts/lib/ is on the path)

PATHSPECS = ("server/*.py", "scripts/*.py", "scripts/*.sh")
COMMITTED_FILES = {
    "scripts/dev.sh": "dev\n",
    "scripts/lib/common.sh": "common\n",
    "scripts/lib/stack.py": "stack\n",
    "server/app.py": "app\n",
    "server/requirements.lock": "lock\n",
}
HIDING_TEXTS = {
    "backspace": "\N{BACKSPACE}",
    "concealing escape sequence": "\N{ESCAPE}[8m",
    "carriage return inside a line": "\N{CARRIAGE RETURN}echo",
    "right-to-left override": "\N{RIGHT-TO-LEFT OVERRIDE}",
    "zero-width space": "\N{ZERO WIDTH SPACE}",
    "word joiner": "\N{WORD JOINER}",
    "tag character": "\N{TAG LATIN CAPITAL LETTER A}",
    "Hangul filler": "\N{HANGUL FILLER}",
    "Hangul choseong filler": "\N{HANGUL CHOSEONG FILLER}",
    "Hangul jungseong filler": "\N{HANGUL JUNGSEONG FILLER}",
    "halfwidth Hangul filler": "\N{HALFWIDTH HANGUL FILLER}",
    "Khmer inherent vowel": "\N{KHMER VOWEL INHERENT AQ}",
    "other Khmer inherent vowel": "\N{KHMER VOWEL INHERENT AA}",
    "Mongolian free variation selector": "\N{MONGOLIAN FREE VARIATION SELECTOR ONE}",
    "last Mongolian free variation selector": "\N{MONGOLIAN FREE VARIATION SELECTOR FOUR}",
    "first variation selector": "\N{VARIATION SELECTOR-1}",
    "supplementary variation selector": "\N{VARIATION SELECTOR-17}",
    "variation selector": "\N{VARIATION SELECTOR-16}",
    "combining grapheme joiner": "\N{COMBINING GRAPHEME JOINER}",
    "Braille blank": "\N{BRAILLE PATTERN BLANK}",
    "line separator": "\N{LINE SEPARATOR}",
    "paragraph separator": "\N{PARAGRAPH SEPARATOR}",
    "private-use character": chr(0xE000),
    "noncharacter": chr(0xFDD0),
}
CONCEALING_SEQUENCE_OF_8_BITS = b"\x9b8m"
LARGEST_GROWN_SIZE_BYTES_OF_A_THOUSAND_BYTE_FILE = 2 * 1000 + 64 * 1024


@dataclass(frozen=True)
class Layout:
    checkout: Path
    tree: Path
    digests_file: Path
    elsewhere: Path


class MakeCopyFailed(RuntimeError):
    pass


def write_file(root: Path, path: str, text: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)


def make_layout(base: Path) -> Layout:
    layout = Layout(base / "checkout", base / "copy" / "tree", base / "copy" / "digests.json", base / "elsewhere")
    for directory in (layout.checkout / "scripts" / "lib", layout.tree, layout.elsewhere):
        directory.mkdir(parents=True)
    run_git(layout.checkout, "init", "--quiet", "--initial-branch=main")
    for path, text in COMMITTED_FILES.items():
        write_file(layout.checkout, path, text)
    run_git(layout.checkout, "add", ".")
    run_git(layout.checkout, "commit", "--quiet", "--message", "Example")
    return layout


def make_temporary_directory(test_case: type[unittest.TestCase]) -> Path:
    return Path(test_case.enterClassContext(tempfile.TemporaryDirectory(prefix="scanmylib-formatting-"))).resolve()


def run_formatting(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(FORMATTING), *arguments],
        env=build_git_environment(os.environ),
        capture_output=True,
        check=False,
    )


def run_make_copy(layout: Layout) -> subprocess.CompletedProcess[bytes]:
    return run_formatting("make-copy", str(layout.checkout), str(layout.tree), str(layout.digests_file), *PATHSPECS)


def make_copy(layout: Layout) -> None:
    copy_run = run_make_copy(layout)
    if copy_run.returncode != 0:
        raise MakeCopyFailed(f"make-copy failed: {os.fsdecode(copy_run.stderr)}")


def run_bring_back(layout: Layout) -> subprocess.CompletedProcess[bytes]:
    return run_formatting("bring-back", str(layout.checkout), str(layout.tree), str(layout.digests_file))


def read_printed_paths(printed: bytes) -> list[str]:
    return [os.fsdecode(path) for path in printed.split(b"\0") if path]


def replace_library_with_link(root: Path, target: Path) -> None:
    library = root / "scripts" / "lib"
    for path in library.iterdir():
        path.unlink()
    library.rmdir()
    library.symlink_to(target)


def make_replace_failing_on(name: str) -> Callable[[str | os.PathLike[str], str | os.PathLike[str]], None]:
    replace = os.replace

    def replace_unless_named(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        if Path(target).name == name:
            raise OSError("disk full")
        replace(source, target)

    return replace_unless_named


def format_two_files(base: Path) -> Layout:
    layout = make_layout(base)
    make_copy(layout)
    write_file(layout.tree, "scripts/dev.sh", "formatted\n")
    write_file(layout.tree, "server/app.py", "formatted\n")
    return layout


def grow_the_copy_of_a_thousand_byte_file(layout: Layout, size_bytes: int) -> None:
    line_of_a_hundred_bytes = "#" * 99 + "\n"
    write_file(layout.checkout, "server/app.py", line_of_a_hundred_bytes * 10)
    make_copy(layout)
    full_lines, remainder_bytes = divmod(size_bytes, 100)
    write_file(layout.tree, "server/app.py", line_of_a_hundred_bytes * full_lines + "#" * (remainder_bytes - 1) + "\n")


class TheShellScriptsCommandWhenScriptsAreAddedAndRemovedInTheWorkingTree(unittest.TestCase):
    listing_run: ClassVar[subprocess.CompletedProcess[bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        write_file(layout.checkout, "scripts/new.sh", "new\n")
        write_file(layout.checkout, "scripts/na\N{LATIN SMALL LETTER I WITH DIAERESIS}ve.sh", "naive\n")
        (layout.checkout / "scripts" / "lib" / "common.sh").unlink()
        cls.listing_run = run_formatting("shell-scripts", str(layout.checkout))

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.listing_run.returncode, 0, self.listing_run.stderr)

    def test_should_list_the_shell_scripts_of_the_working_tree_whether_git_tracks_them_or_not(self) -> None:
        self.assertEqual(
            sorted(read_printed_paths(self.listing_run.stdout)),
            ["scripts/dev.sh", "scripts/na\N{LATIN SMALL LETTER I WITH DIAERESIS}ve.sh", "scripts/new.sh"],
        )


class TheShellScriptsCommandWhenTheCheckoutIsMissing(unittest.TestCase):
    listing_run: ClassVar[subprocess.CompletedProcess[bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.listing_run = run_formatting("shell-scripts", str(make_temporary_directory(cls) / "missing"))

    def test_should_refuse_with_git_s_own_message(self) -> None:
        self.assertEqual(self.listing_run.returncode, 1)
        self.assertIn(b"fatal: cannot change to", self.listing_run.stderr)

    def test_should_print_no_traceback(self) -> None:
        self.assertNotIn(b"Traceback", self.listing_run.stderr)


class TheCheckHiddenCommandWhenAFileIsHiddenFromGitDiff(unittest.TestCase):
    hidden_files: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {"--assume-unchanged": "scripts/dev.sh", "--skip-worktree": "server/app.py"}
    )
    check_runs: ClassVar[dict[str, subprocess.CompletedProcess[bytes]]]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        cls.check_runs = {}
        for flag, path in cls.hidden_files.items():
            run_git(layout.checkout, "update-index", flag, path)
            cls.check_runs[flag] = run_formatting("check-hidden", str(layout.checkout), "server", "scripts")
            run_git(layout.checkout, "update-index", flag.replace("--", "--no-", 1), path)

    def test_should_refuse_it_naming_it_so_that_git_diff_shows_whatever_the_formatters_change(self) -> None:
        for flag, path in self.hidden_files.items():
            with self.subTest(flag):
                self.assertEqual(self.check_runs[flag].returncode, 1)
                self.assertIn(path.encode(), self.check_runs[flag].stderr)


class TheMakeCopyCommandWhenTheWorkingTreeHoldsTheCommittedFiles(unittest.TestCase):
    copy_run: ClassVar[subprocess.CompletedProcess[bytes]]
    copied_files: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        cls.copy_run = run_make_copy(layout)
        cls.copied_files = sorted(str(path.relative_to(layout.tree)) for path in layout.tree.rglob("*.*"))

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.copy_run.returncode, 0, self.copy_run.stderr)

    def test_should_print_the_shell_scripts_it_copied(self) -> None:
        self.assertEqual(read_printed_paths(self.copy_run.stdout), ["scripts/dev.sh", "scripts/lib/common.sh"])

    def test_should_copy_the_tracked_files_the_pathspecs_name_and_no_other(self) -> None:
        self.assertEqual(
            self.copied_files, ["scripts/dev.sh", "scripts/lib/common.sh", "scripts/lib/stack.py", "server/app.py"]
        )


class TheMakeCopyCommandWhenAFileIsUntracked(unittest.TestCase):
    copy_run: ClassVar[subprocess.CompletedProcess[bytes]]
    is_copied: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        write_file(layout.checkout, "scripts/local.sh", "local\n")
        cls.copy_run = run_make_copy(layout)
        cls.is_copied = (layout.tree / "scripts" / "local.sh").exists()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.copy_run.returncode, 0, self.copy_run.stderr)

    def test_should_leave_it_out_of_the_copy(self) -> None:
        self.assertFalse(self.is_copied)

    def test_should_say_it_left_it_out(self) -> None:
        self.assertIn(b"scripts/local.sh", self.copy_run.stderr)


class TheMakeCopyCommandWhenATrackedDirectoryIsALink(unittest.TestCase):
    copy_run: ClassVar[subprocess.CompletedProcess[bytes]]
    is_copied: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        for name in ("common.sh", "stack.py"):
            (layout.elsewhere / name).write_text("elsewhere\n")
        replace_library_with_link(layout.checkout, layout.elsewhere)
        cls.copy_run = run_make_copy(layout)
        cls.is_copied = (layout.tree / "scripts" / "lib" / "common.sh").exists()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.copy_run.returncode, 0, self.copy_run.stderr)

    def test_should_leave_its_files_out_of_the_copy(self) -> None:
        self.assertFalse(self.is_copied)

    def test_should_say_it_left_them_out(self) -> None:
        self.assertIn(b"scripts/lib/common.sh", self.copy_run.stderr)


class TheMakeCopyCommandWhenATrackedFileIsDeletedFromTheWorkingTree(unittest.TestCase):
    copy_run: ClassVar[subprocess.CompletedProcess[bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.checkout / "scripts" / "dev.sh").unlink()
        cls.copy_run = run_make_copy(layout)

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.copy_run.returncode, 0, self.copy_run.stderr)

    def test_should_leave_it_out_of_the_copy(self) -> None:
        self.assertEqual(read_printed_paths(self.copy_run.stdout), ["scripts/lib/common.sh"])

    def test_should_not_report_it_as_left_out(self) -> None:
        self.assertNotIn(b"scripts/dev.sh", self.copy_run.stderr)


class TheBringBackCommandWhenTheDigestsFileCannotBeRead(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        cls.bring_back_run = run_bring_back(layout)

    def test_should_refuse_naming_the_digests_file(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"digests.json", self.bring_back_run.stderr)

    def test_should_print_no_traceback(self) -> None:
        self.assertNotIn(b"Traceback", self.bring_back_run.stderr)


class TheBringBackCommandWhenATrackedFileIsALink(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    target: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.elsewhere / "target.sh").write_text("target\n")
        (layout.checkout / "scripts" / "linked.sh").symlink_to(layout.elsewhere / "target.sh")
        run_git(layout.checkout, "add", "scripts/linked.sh")
        run_git(layout.checkout, "commit", "--quiet", "--message", "Link")
        make_copy(layout)
        write_file(layout.tree, "scripts/linked.sh", "formatted\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.target = (layout.elsewhere / "target.sh").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_never_write_through_the_link(self) -> None:
        self.assertEqual(self.target, "target\n")


class TheBringBackCommandWhenAFormatterChangesAFile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    stack_module: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/lib/stack.py", "formatted\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.stack_module = (layout.checkout / "scripts" / "lib" / "stack.py").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_the_change_back(self) -> None:
        self.assertEqual(self.stack_module, "formatted\n")


class TheBringBackCommandWhenAFormatterChangesAnExecutableFile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    mode: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        script = layout.checkout / "scripts" / "dev.sh"
        script.chmod(0o755)
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "formatted\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.mode = stat.S_IMODE(script.stat().st_mode)

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_keep_its_mode(self) -> None:
        self.assertEqual(self.mode, 0o755)


class TheBringBackCommandWhenAFormatterCreatesAFile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    is_brought_back: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/test_planted.py", "planted\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.is_brought_back = (layout.checkout / "scripts" / "test_planted.py").exists()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_never_bring_it_back_so_that_nothing_a_formatter_plants_reaches_the_checkout(self) -> None:
        self.assertFalse(self.is_brought_back)


class TheBringBackCommandWhenAFormatterChangesAFileThePathspecsLeaveOut(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    lock: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "server/requirements.lock", "formatted\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.lock = (layout.checkout / "server" / "requirements.lock").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_never_bring_it_back(self) -> None:
        self.assertEqual(self.lock, "lock\n")


class TheBringBackCommandWhenAFormatterTurnsAFileIntoALink(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]
    common_library: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.elsewhere / "secret").write_text("secret\n")
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "formatted\n")
        common = layout.tree / "scripts" / "lib" / "common.sh"
        common.unlink()
        common.symlink_to(layout.elsewhere / "secret")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()
        cls.common_library = (layout.checkout / "scripts" / "lib" / "common.sh").read_text()

    def test_should_refuse_since_the_copy_of_the_file_is_no_longer_a_file(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"scripts/lib/common.sh into something other than a file", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")

    def test_should_leave_the_file_of_the_checkout_as_it_was(self) -> None:
        self.assertEqual(self.common_library, "common\n")


class TheBringBackCommandWhenAFormatterTurnsAFileIntoADirectory(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "formatted\n")
        common = layout.tree / "scripts" / "lib" / "common.sh"
        common.unlink()
        common.mkdir()
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_since_the_copy_of_the_file_is_no_longer_a_file(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"scripts/lib/common.sh into something other than a file", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


class TheBringBackCommandWhenAFormatterTurnsADirectoryIntoALink(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]
    common_library: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        for name in ("common.sh", "stack.py"):
            (layout.elsewhere / name).write_text("elsewhere\n")
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "formatted\n")
        replace_library_with_link(layout.tree, layout.elsewhere)
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()
        cls.common_library = (layout.checkout / "scripts" / "lib" / "common.sh").read_text()

    def test_should_refuse_since_the_copies_of_its_files_are_no_longer_files(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"into something other than a file", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")

    def test_should_leave_the_files_of_the_directory_as_they_were(self) -> None:
        self.assertEqual(self.common_library, "common\n")


class TheBringBackCommandWhenAFileAFormatterChangedChangesInTheCheckoutMeanwhile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    stack_module: ClassVar[str]
    app_module: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/lib/stack.py", "formatted\n")
        write_file(layout.tree, "server/app.py", "formatted\n")
        write_file(layout.checkout, "scripts/lib/stack.py", "edited meanwhile\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.stack_module = (layout.checkout / "scripts" / "lib" / "stack.py").read_text()
        cls.app_module = (layout.checkout / "server" / "app.py").read_text()

    def test_should_refuse_since_the_file_changed_in_the_checkout(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"scripts/lib/stack.py changed in the checkout", self.bring_back_run.stderr)

    def test_should_keep_the_edit_of_the_checkout(self) -> None:
        self.assertEqual(self.stack_module, "edited meanwhile\n")

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.app_module, "app\n")


class TheBringBackCommandWhenAFileOfTheCheckoutBecomesALinkMeanwhile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    target: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.elsewhere / "dev.sh").write_text("dev\n")
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "formatted\n")
        (layout.checkout / "scripts" / "dev.sh").unlink()
        (layout.checkout / "scripts" / "dev.sh").symlink_to(layout.elsewhere / "dev.sh")
        cls.bring_back_run = run_bring_back(layout)
        cls.target = (layout.elsewhere / "dev.sh").read_text()

    def test_should_refuse_since_the_file_changed_in_the_checkout(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"scripts/dev.sh changed in the checkout", self.bring_back_run.stderr)

    def test_should_never_write_through_the_link(self) -> None:
        self.assertEqual(self.target, "dev\n")


class TheBringBackCommandWhenADirectoryOfTheCheckoutBecomesALinkMeanwhile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    target: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        for name in ("common.sh", "stack.py"):
            (layout.elsewhere / name).write_text(COMMITTED_FILES[f"scripts/lib/{name}"])
        make_copy(layout)
        write_file(layout.tree, "scripts/lib/common.sh", "formatted\n")
        replace_library_with_link(layout.checkout, layout.elsewhere)
        cls.bring_back_run = run_bring_back(layout)
        cls.target = (layout.elsewhere / "common.sh").read_text()

    def test_should_refuse_since_the_file_changed_in_the_checkout(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"scripts/lib/common.sh changed in the checkout", self.bring_back_run.stderr)

    def test_should_never_write_through_the_link(self) -> None:
        self.assertEqual(self.target, "common\n")


@unittest.skipIf(os.geteuid() == 0, "root writes in a read-only directory")
class TheBringBackCommandWhenADirectoryOfTheCheckoutCannotBeWritten(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = format_two_files(make_temporary_directory(cls))
        server = layout.checkout / "server"
        server.chmod(0o555)
        cls.addClassCleanup(server.chmod, 0o755)
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_naming_the_file_it_cannot_write(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"server/app.py cannot be written", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


@unittest.skipIf(os.geteuid() == 0, "root writes a read-only file")
class TheBringBackCommandWhenAFileOfTheCheckoutCannotBeWritten(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = format_two_files(make_temporary_directory(cls))
        (layout.checkout / "server" / "app.py").chmod(0o444)
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_naming_the_file_it_cannot_write(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"server/app.py cannot be written", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


class TheBringBackCommandWhenAFileTheFormattersLeftAloneChangesInTheCheckoutMeanwhile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.checkout, "scripts/dev.sh", "edited meanwhile\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_keep_the_edit_of_the_checkout(self) -> None:
        self.assertEqual(self.dev_script, "edited meanwhile\n")


class TheBringBackCommandWhenAFormatterAddsACharacterATerminalDoesNotShow(unittest.TestCase):
    bring_back_runs: ClassVar[dict[str, subprocess.CompletedProcess[bytes]]]
    dev_scripts: ClassVar[dict[str, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        cls.bring_back_runs, cls.dev_scripts = {}, {}
        for row, hiding_text in HIDING_TEXTS.items():
            make_copy(layout)
            write_file(layout.tree, "scripts/dev.sh", "formatted\n")
            write_file(layout.tree, "server/app.py", f"app{hiding_text}\n")
            cls.bring_back_runs[row] = run_bring_back(layout)
            cls.dev_scripts[row] = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_each_one_since_a_reader_of_git_diff_would_not_see_it(self) -> None:
        for row in HIDING_TEXTS:
            with self.subTest(row):
                self.assertEqual(self.bring_back_runs[row].returncode, 1)
                self.assertIn(
                    b"a formatter added to server/app.py a character a terminal does not show",
                    self.bring_back_runs[row].stderr,
                )

    def test_should_bring_back_nothing(self) -> None:
        for row in HIDING_TEXTS:
            with self.subTest(row):
                self.assertEqual(self.dev_scripts[row], b"dev\n")


class TheBringBackCommandWhenAFormatterChangesAFileThatHoldsACharacterATerminalDoesNotShow(unittest.TestCase):
    bring_back_runs: ClassVar[dict[str, subprocess.CompletedProcess[bytes]]]
    app_modules: ClassVar[dict[str, bytes]]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        cls.bring_back_runs, cls.app_modules = {}, {}
        for row, hiding_text in HIDING_TEXTS.items():
            write_file(layout.checkout, "server/app.py", f"app{hiding_text}\nmore\n")
            make_copy(layout)
            write_file(layout.tree, "server/app.py", f"app{hiding_text}\nmore = 1\n")
            cls.bring_back_runs[row] = run_bring_back(layout)
            cls.app_modules[row] = (layout.checkout / "server" / "app.py").read_bytes()

    def test_should_refuse_each_one_naming_the_file_that_holds_it(self) -> None:
        for row in HIDING_TEXTS:
            with self.subTest(row):
                self.assertEqual(self.bring_back_runs[row].returncode, 1)
                self.assertIn(
                    b"server/app.py holds a character a terminal does not show", self.bring_back_runs[row].stderr
                )

    def test_should_leave_the_file_as_it_was(self) -> None:
        for row, hiding_text in HIDING_TEXTS.items():
            with self.subTest(row):
                self.assertEqual(self.app_modules[row], f"app{hiding_text}\nmore\n".encode())


class TheBringBackCommandWhenAFormatterRemovesACharacterATerminalDoesNotShow(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    app_module: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        write_file(layout.checkout, "server/app.py", "app\N{ZERO WIDTH SPACE}\n")
        make_copy(layout)
        write_file(layout.tree, "server/app.py", "app\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.app_module = (layout.checkout / "server" / "app.py").read_text()

    def test_should_refuse_asking_for_the_character_to_be_written_as_an_escape(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"write it as an escape", self.bring_back_run.stderr)

    def test_should_leave_the_file_as_it_was(self) -> None:
        self.assertEqual(self.app_module, "app\N{ZERO WIDTH SPACE}\n")


class TheBringBackCommandWhenAFormatterAddsACharacterATerminalDoesNotShowOnTheSecondLine(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "dev\nmore\N{ZERO WIDTH SPACE}\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_naming_the_line_and_the_code_point_of_the_character(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"line 2: U+200B", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


class TheBringBackCommandWhenAFormatterAddsAByteThatIsNotUtf8(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        (layout.tree / "scripts" / "dev.sh").write_bytes(b"dev" + CONCEALING_SEQUENCE_OF_8_BITS + b"\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_naming_the_line_and_the_byte(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"(line 1: byte 0x9B)", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


class TheBringBackCommandWhenAFormatterChangesAFileThatHoldsAByteThatIsNotUtf8(unittest.TestCase):
    checkout_bytes: ClassVar[bytes] = b"app" + CONCEALING_SEQUENCE_OF_8_BITS + b"\nmore\n"
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    app_module: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.checkout / "server" / "app.py").write_bytes(cls.checkout_bytes)
        make_copy(layout)
        (layout.tree / "server" / "app.py").write_bytes(b"app" + CONCEALING_SEQUENCE_OF_8_BITS + b"\nmore = 1\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.app_module = (layout.checkout / "server" / "app.py").read_bytes()

    def test_should_refuse_naming_the_file_that_holds_it(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"server/app.py holds a character a terminal does not show", self.bring_back_run.stderr)

    def test_should_leave_the_file_as_it_was(self) -> None:
        self.assertEqual(self.app_module, self.checkout_bytes)


class TheBringBackCommandWhenAFormatterAddsACarriageReturnToAFileWithoutThem(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "dev\N{CARRIAGE RETURN}\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_since_a_terminal_does_not_show_it(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(
            b"a formatter added to scripts/dev.sh a character a terminal does not show", self.bring_back_run.stderr
        )

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


class TheBringBackCommandWhenAFormatterAddsACarriageReturnInsideALineOfAFileWhoseLinesEndInOne(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.checkout / "scripts" / "dev.sh").write_bytes(b"dev\r\n")
        make_copy(layout)
        (layout.tree / "scripts" / "dev.sh").write_bytes(b"dev\recho\r\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_since_it_hides_text(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(
            b"a formatter added to scripts/dev.sh a character a terminal does not show", self.bring_back_run.stderr
        )

    def test_should_leave_the_file_as_it_was(self) -> None:
        self.assertEqual(self.dev_script, b"dev\r\n")


class TheBringBackCommandWhenAFormatterAddsACharacterOutsideAscii(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "dev = \N{CYRILLIC SMALL LETTER A}\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_since_it_may_look_like_another(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"characters outside ASCII", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


class TheBringBackCommandWhenAFormatterGrowsAFileToTwiceItsSizeAnd64Kib(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    app_module_size_bytes: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        grow_the_copy_of_a_thousand_byte_file(layout, LARGEST_GROWN_SIZE_BYTES_OF_A_THOUSAND_BYTE_FILE)
        cls.bring_back_run = run_bring_back(layout)
        cls.app_module_size_bytes = (layout.checkout / "server" / "app.py").stat().st_size

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_it_back(self) -> None:
        self.assertEqual(self.app_module_size_bytes, LARGEST_GROWN_SIZE_BYTES_OF_A_THOUSAND_BYTE_FILE)


class TheBringBackCommandWhenAFormatterGrowsAFilePastTwiceItsSizeAnd64Kib(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    app_module_size_bytes: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        grow_the_copy_of_a_thousand_byte_file(layout, LARGEST_GROWN_SIZE_BYTES_OF_A_THOUSAND_BYTE_FILE + 1)
        cls.bring_back_run = run_bring_back(layout)
        cls.app_module_size_bytes = (layout.checkout / "server" / "app.py").stat().st_size

    def test_should_refuse_since_formatting_never_grows_a_file_that_much(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"grew server/app.py past twice its size and 64 KiB", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.app_module_size_bytes, 1000)


class TheBringBackCommandWhenAFormatterWritesALineFarLongerThanTheFiles(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "dev" + " " * 1000 + "; echo\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_refuse_since_it_could_push_text_out_of_sight(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 1)
        self.assertIn(b"a formatter wrote in scripts/dev.sh a line of 1009 characters", self.bring_back_run.stderr)

    def test_should_bring_back_nothing(self) -> None:
        self.assertEqual(self.dev_script, b"dev\n")


class TheBringBackCommandWhenAFormatterKeepsALongLineTheFileAlreadyHad(unittest.TestCase):
    long_line: ClassVar[str] = "#" * 1500
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        write_file(layout.checkout, "scripts/dev.sh", f"{cls.long_line}\ndev\n")
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", f"{cls.long_line}\ndev = 1\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_the_change_back(self) -> None:
        self.assertEqual(self.dev_script, f"{self.long_line}\ndev = 1\n")


class TheBringBackCommandWhenAFileTheFormattersLeaveUnchangedHoldsACharacterATerminalDoesNotShow(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    app_module: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        write_file(layout.checkout, "scripts/dev.sh", "dev\N{FORM FEED}\n")
        make_copy(layout)
        write_file(layout.tree, "server/app.py", "formatted\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.app_module = (layout.checkout / "server" / "app.py").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_the_changes_of_the_other_files_back(self) -> None:
        self.assertEqual(self.app_module, "formatted\n")


class TheBringBackCommandWhenAFormatterAddsALineIndentedWithATab(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "dev\n\tmore\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_the_change_back(self) -> None:
        self.assertEqual(self.dev_script, "dev\n\tmore\n")


class TheBringBackCommandWhenAFormatterReformatsALineThatHoldsACharacterOutsideAscii(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        write_file(layout.checkout, "scripts/dev.sh", "caf\N{LATIN SMALL LETTER E WITH ACUTE}  =  1\n")
        make_copy(layout)
        write_file(layout.tree, "scripts/dev.sh", "caf\N{LATIN SMALL LETTER E WITH ACUTE} = 1\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_the_change_back(self) -> None:
        self.assertEqual(self.dev_script, "caf\N{LATIN SMALL LETTER E WITH ACUTE} = 1\n")


class TheBringBackCommandWhenAFormatterChangesAFileWhoseLinesEndInACarriageReturnAndALineFeed(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.checkout / "scripts" / "dev.sh").write_bytes(b"dev\r\n")
        make_copy(layout)
        (layout.tree / "scripts" / "dev.sh").write_bytes(b"dev\r\nmore\r\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_the_change_back(self) -> None:
        self.assertEqual(self.dev_script, b"dev\r\nmore\r\n")


class TheBringBackCommandWhenAFormatterDropsTheCarriageReturnsThatEndTheLinesOfAFile(unittest.TestCase):
    bring_back_run: ClassVar[subprocess.CompletedProcess[bytes]]
    dev_script: ClassVar[bytes]

    @classmethod
    def setUpClass(cls) -> None:
        layout = make_layout(make_temporary_directory(cls))
        (layout.checkout / "scripts" / "dev.sh").write_bytes(b"dev\r\nmore\r\n")
        make_copy(layout)
        (layout.tree / "scripts" / "dev.sh").write_bytes(b"dev\nmore\n")
        cls.bring_back_run = run_bring_back(layout)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_bytes()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.bring_back_run.returncode, 0, self.bring_back_run.stderr)

    def test_should_bring_the_change_back(self) -> None:
        self.assertEqual(self.dev_script, b"dev\nmore\n")


class TheBringBackFunctionWhenAWriteFailsMidway(unittest.TestCase):
    def setUp(self) -> None:
        base = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="scanmylib-formatting-"))).resolve()
        layout = format_two_files(base)
        self.enterContext(mock.patch("os.replace", make_replace_failing_on("app.py")))
        self.bring_back = functools.partial(formatting.bring_back, layout.checkout, layout.tree, layout.digests_file)

    def test_should_refuse_naming_the_files_it_brought_back_before_it(self) -> None:
        self.assertRaisesRegex(
            formatting.FormattingRefused,
            r"^writing server/app\.py failed \(disk full\); brought back before it: scripts/dev\.sh$",
            self.bring_back,
        )


class TheBringBackFunctionWhenAWriteHasFailedMidway(unittest.TestCase):
    dev_script: ClassVar[str]
    app_module: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        layout = format_two_files(make_temporary_directory(cls))
        # The refusal ends the act: what it leaves in the checkout is read once the refusal is caught.
        with (
            mock.patch("os.replace", make_replace_failing_on("app.py")),
            contextlib.suppress(formatting.FormattingRefused),
        ):
            formatting.bring_back(layout.checkout, layout.tree, layout.digests_file)
        cls.dev_script = (layout.checkout / "scripts" / "dev.sh").read_text()
        cls.app_module = (layout.checkout / "server" / "app.py").read_text()

    def test_should_keep_the_files_it_brought_back_before_it(self) -> None:
        self.assertEqual(self.dev_script, "formatted\n")

    def test_should_leave_the_file_it_failed_to_write_as_it_was(self) -> None:
        self.assertEqual(self.app_module, "app\n")


if __name__ == "__main__":
    unittest.main()
