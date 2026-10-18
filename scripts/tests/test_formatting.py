"""What scripts/check.sh hands to its formatters and linters, and what comes back from the copy
(scripts/lib/formatting.py).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from git_environment import build_git_environment

FORMATTING = Path(__file__).resolve().parent.parent / "lib" / "formatting.py"
sys.path.insert(0, str(FORMATTING.parent))
import formatting  # noqa: E402 (scripts/lib/formatting.py, found once scripts/lib/ is on the path)

PATHSPECS = ("server/*.py", "scripts/*.py", "scripts/*.sh")
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


class FormattingTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="scanmylib-formatting-")
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name).resolve()
        self.checkout = self.base / "checkout"
        self.tree = self.base / "copy" / "tree"
        self.digests_file = self.base / "copy" / "digests.json"
        self.elsewhere = self.base / "elsewhere"
        for path in (self.checkout / "scripts" / "lib", self.tree, self.elsewhere):
            path.mkdir(parents=True)
        self.git("init", "--quiet", "--initial-branch=main")
        self.write("scripts/dev.sh", "dev\n")
        self.write("scripts/lib/common.sh", "common\n")
        self.write("scripts/lib/stack.py", "stack\n")
        self.write("server/app.py", "app\n")
        self.write("server/requirements.lock", "lock\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "--message", "Example")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.checkout,
            env=build_git_environment(os.environ),
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def write(self, path: str, text: str) -> None:
        (self.checkout / path).parent.mkdir(parents=True, exist_ok=True)
        (self.checkout / path).write_text(text)

    def run_formatting(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(FORMATTING), *args],
            env=build_git_environment(os.environ),
            capture_output=True,
            check=False,
        )

    def run_make_copy(self) -> subprocess.CompletedProcess[bytes]:
        return self.run_formatting("make-copy", str(self.checkout), str(self.tree), str(self.digests_file), *PATHSPECS)

    def make_copy(self) -> list[str]:
        copy_run = self.run_make_copy()
        self.assertEqual(copy_run.returncode, 0, copy_run.stderr)
        return [os.fsdecode(path) for path in copy_run.stdout.split(b"\0") if path]

    def bring_back(self) -> subprocess.CompletedProcess[bytes]:
        return self.run_formatting("bring-back", str(self.checkout), str(self.tree), str(self.digests_file))

    def format_copy(self, path: str, text: str) -> None:
        (self.tree / path).parent.mkdir(parents=True, exist_ok=True)
        (self.tree / path).write_text(text)

    def read(self, path: str) -> str:
        return (self.checkout / path).read_text()

    def replace_library_with_link(self, root: Path) -> None:
        library = root / "scripts" / "lib"
        for path in library.iterdir():
            path.unlink()
        library.rmdir()
        library.symlink_to(self.elsewhere)

    def assert_nothing_came_back(self, refusal: bytes) -> None:
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(refusal, bring_back_run.stderr)
        self.assertEqual((self.checkout / "scripts" / "dev.sh").read_bytes(), b"dev\n")

    def test_the_shell_scripts_are_those_of_the_working_tree_tracked_or_not(self) -> None:
        self.write("scripts/new.sh", "new\n")
        self.write("scripts/na\N{LATIN SMALL LETTER I WITH DIAERESIS}ve.sh", "naive\n")
        (self.checkout / "scripts" / "lib" / "common.sh").unlink()
        listing_run = self.run_formatting("shell-scripts", str(self.checkout))
        self.assertEqual(listing_run.returncode, 0, listing_run.stderr)
        self.assertEqual(
            sorted(os.fsdecode(path) for path in listing_run.stdout.split(b"\0") if path),
            ["scripts/dev.sh", "scripts/na\N{LATIN SMALL LETTER I WITH DIAERESIS}ve.sh", "scripts/new.sh"],
        )

    def test_git_s_own_message_explains_a_failure(self) -> None:
        listing_run = self.run_formatting("shell-scripts", str(self.base / "missing"))
        self.assertEqual(listing_run.returncode, 1)
        self.assertIn(b"fatal: cannot change to", listing_run.stderr)
        self.assertNotIn(b"Traceback", listing_run.stderr)

    def test_a_digests_file_that_cannot_be_read_fails_with_a_message_not_a_traceback(self) -> None:
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(b"digests.json", bring_back_run.stderr)
        self.assertNotIn(b"Traceback", bring_back_run.stderr)

    def test_files_that_git_diff_would_not_show_are_refused(self) -> None:
        for flag, path in (("--assume-unchanged", "scripts/dev.sh"), ("--skip-worktree", "server/app.py")):
            with self.subTest(flag=flag):
                self.git("update-index", flag, path)
                check_run = self.run_formatting("check-hidden", str(self.checkout), "server", "scripts")
                self.assertEqual(check_run.returncode, 1)
                self.assertIn(path.encode(), check_run.stderr)
                self.git("update-index", flag.replace("--", "--no-", 1), path)

    def test_the_copy_holds_the_tracked_files_the_pathspecs_name(self) -> None:
        self.assertEqual(self.make_copy(), ["scripts/dev.sh", "scripts/lib/common.sh"])
        copied_files = sorted(str(path.relative_to(self.tree)) for path in self.tree.rglob("*.*"))
        self.assertEqual(
            copied_files, ["scripts/dev.sh", "scripts/lib/common.sh", "scripts/lib/stack.py", "server/app.py"]
        )

    def test_the_copy_leaves_out_untracked_files_and_says_so(self) -> None:
        self.write("scripts/local.sh", "local\n")
        copy_run = self.run_make_copy()
        self.assertEqual(copy_run.returncode, 0, copy_run.stderr)
        self.assertFalse((self.tree / "scripts" / "local.sh").exists())
        self.assertIn(b"scripts/local.sh", copy_run.stderr)

    def test_the_copy_leaves_out_the_files_of_a_tracked_directory_turned_into_a_link_and_says_so(self) -> None:
        for name in ("common.sh", "stack.py"):
            (self.elsewhere / name).write_text("elsewhere\n")
        self.replace_library_with_link(self.checkout)
        copy_run = self.run_make_copy()
        self.assertEqual(copy_run.returncode, 0, copy_run.stderr)
        self.assertFalse((self.tree / "scripts" / "lib" / "common.sh").exists())
        self.assertIn(b"scripts/lib/common.sh", copy_run.stderr)

    def test_a_tracked_link_is_neither_copied_nor_written_through(self) -> None:
        (self.elsewhere / "target.sh").write_text("target\n")
        (self.checkout / "scripts" / "linked.sh").symlink_to(self.elsewhere / "target.sh")
        self.git("add", "scripts/linked.sh")
        self.git("commit", "--quiet", "--message", "Link")
        self.make_copy()
        self.format_copy("scripts/linked.sh", "formatted\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual((self.elsewhere / "target.sh").read_text(), "target\n")

    def test_a_tracked_file_deleted_from_the_working_tree_is_left_out_of_the_copy(self) -> None:
        (self.checkout / "scripts" / "dev.sh").unlink()
        self.assertEqual(self.make_copy(), ["scripts/lib/common.sh"])

    def test_a_tracked_file_deleted_from_the_working_tree_is_not_reported_as_left_out(self) -> None:
        (self.checkout / "scripts" / "dev.sh").unlink()
        copy_run = self.run_make_copy()
        self.assertEqual(copy_run.returncode, 0, copy_run.stderr)
        self.assertNotIn(b"scripts/dev.sh", copy_run.stderr)

    def test_what_a_formatter_changes_comes_back(self) -> None:
        self.make_copy()
        self.format_copy("scripts/lib/stack.py", "formatted\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(self.read("scripts/lib/stack.py"), "formatted\n")

    def test_a_file_that_comes_back_keeps_its_mode(self) -> None:
        script = self.checkout / "scripts" / "dev.sh"
        script.chmod(0o755)
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o755)

    def test_a_file_a_formatter_creates_never_comes_back(self) -> None:
        self.make_copy()
        self.format_copy("scripts/test_planted.py", "planted\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertFalse((self.checkout / "scripts" / "test_planted.py").exists())

    def test_a_file_the_pathspecs_leave_out_never_comes_back(self) -> None:
        self.make_copy()
        self.format_copy("server/requirements.lock", "formatted\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(self.read("server/requirements.lock"), "lock\n")

    def test_nothing_comes_back_once_a_formatter_turns_a_file_into_a_link(self) -> None:
        (self.elsewhere / "secret").write_text("secret\n")
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        common = self.tree / "scripts" / "lib" / "common.sh"
        common.unlink()
        common.symlink_to(self.elsewhere / "secret")
        self.assert_nothing_came_back(b"scripts/lib/common.sh into something other than a file")
        self.assertEqual(self.read("scripts/lib/common.sh"), "common\n")

    def test_nothing_comes_back_once_a_formatter_turns_a_file_into_a_directory(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        common = self.tree / "scripts" / "lib" / "common.sh"
        common.unlink()
        common.mkdir()
        self.assert_nothing_came_back(b"scripts/lib/common.sh into something other than a file")

    def test_nothing_comes_back_once_a_formatter_turns_a_directory_into_a_link(self) -> None:
        for name in ("common.sh", "stack.py"):
            (self.elsewhere / name).write_text("elsewhere\n")
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        self.replace_library_with_link(self.tree)
        self.assert_nothing_came_back(b"into something other than a file")
        self.assertEqual(self.read("scripts/lib/common.sh"), "common\n")

    def test_nothing_comes_back_once_a_file_changes_in_the_checkout_meanwhile(self) -> None:
        self.make_copy()
        self.format_copy("scripts/lib/stack.py", "formatted\n")
        self.format_copy("server/app.py", "formatted\n")
        self.write("scripts/lib/stack.py", "edited meanwhile\n")
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(b"scripts/lib/stack.py changed in the checkout", bring_back_run.stderr)
        self.assertEqual(self.read("scripts/lib/stack.py"), "edited meanwhile\n")
        self.assertEqual(self.read("server/app.py"), "app\n")

    def test_nothing_comes_back_once_a_file_of_the_checkout_becomes_a_link_meanwhile(self) -> None:
        (self.elsewhere / "dev.sh").write_text("dev\n")
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        (self.checkout / "scripts" / "dev.sh").unlink()
        (self.checkout / "scripts" / "dev.sh").symlink_to(self.elsewhere / "dev.sh")
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(b"scripts/dev.sh changed in the checkout", bring_back_run.stderr)
        self.assertEqual((self.elsewhere / "dev.sh").read_text(), "dev\n")

    def test_nothing_comes_back_once_a_directory_of_the_checkout_becomes_a_link_meanwhile(self) -> None:
        for name in ("common.sh", "stack.py"):
            (self.elsewhere / name).write_text(self.read(f"scripts/lib/{name}"))
        self.make_copy()
        self.format_copy("scripts/lib/common.sh", "formatted\n")
        self.replace_library_with_link(self.checkout)
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(b"scripts/lib/common.sh changed in the checkout", bring_back_run.stderr)
        self.assertEqual((self.elsewhere / "common.sh").read_text(), "common\n")

    @unittest.skipIf(os.geteuid() == 0, "root writes in a read-only directory")
    def test_nothing_comes_back_once_a_directory_of_the_checkout_cannot_be_written(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        self.format_copy("server/app.py", "formatted\n")
        server = self.checkout / "server"
        server.chmod(0o555)
        self.addCleanup(server.chmod, 0o755)
        self.assert_nothing_came_back(b"server/app.py cannot be written")

    @unittest.skipIf(os.geteuid() == 0, "root writes a read-only file")
    def test_nothing_comes_back_once_a_file_of_the_checkout_cannot_be_written(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        self.format_copy("server/app.py", "formatted\n")
        (self.checkout / "server" / "app.py").chmod(0o444)
        self.assert_nothing_came_back(b"server/app.py cannot be written")

    def test_a_file_changed_meanwhile_but_left_alone_by_the_formatters_is_kept(self) -> None:
        self.make_copy()
        self.write("scripts/dev.sh", "edited meanwhile\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(self.read("scripts/dev.sh"), "edited meanwhile\n")

    def test_nothing_comes_back_once_a_formatter_adds_a_character_a_terminal_does_not_show(self) -> None:
        for name, hiding_text in HIDING_TEXTS.items():
            with self.subTest(name=name):
                self.make_copy()
                self.format_copy("scripts/dev.sh", "formatted\n")
                self.format_copy("server/app.py", f"app{hiding_text}\n")
                self.assert_nothing_came_back(
                    b"a formatter added to server/app.py a character a terminal does not show"
                )

    def test_nothing_comes_back_once_a_formatter_changes_a_file_that_holds_a_character_a_terminal_does_not_show(
        self,
    ) -> None:
        for name, hiding_text in HIDING_TEXTS.items():
            with self.subTest(name=name):
                self.write("server/app.py", f"app{hiding_text}\nmore\n")
                self.make_copy()
                self.format_copy("server/app.py", f"app{hiding_text}\nmore = 1\n")
                bring_back_run = self.bring_back()
                self.assertEqual(bring_back_run.returncode, 1)
                self.assertIn(b"server/app.py holds a character a terminal does not show", bring_back_run.stderr)
                self.assertEqual(
                    (self.checkout / "server" / "app.py").read_bytes(), f"app{hiding_text}\nmore\n".encode()
                )

    def test_nothing_comes_back_once_a_formatter_removes_a_character_a_terminal_does_not_show(self) -> None:
        self.write("server/app.py", "app\N{ZERO WIDTH SPACE}\n")
        self.make_copy()
        self.format_copy("server/app.py", "app\n")
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(b"write it as an escape", bring_back_run.stderr)
        self.assertEqual(self.read("server/app.py"), "app\N{ZERO WIDTH SPACE}\n")

    def test_the_refusal_names_the_line_and_the_code_point_of_a_character_a_terminal_does_not_show(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "dev\nmore\N{ZERO WIDTH SPACE}\n")
        self.assert_nothing_came_back(b"line 2: U+200B")

    def test_nothing_comes_back_once_a_formatter_adds_a_byte_that_is_not_utf_8(self) -> None:
        self.make_copy()
        (self.tree / "scripts" / "dev.sh").write_bytes(b"dev" + CONCEALING_SEQUENCE_OF_8_BITS + b"\n")
        self.assert_nothing_came_back(b"(line 1: byte 0x9B)")

    def test_nothing_comes_back_once_a_formatter_changes_a_file_that_holds_a_byte_that_is_not_utf_8(self) -> None:
        checkout_bytes = b"app" + CONCEALING_SEQUENCE_OF_8_BITS + b"\nmore\n"
        (self.checkout / "server" / "app.py").write_bytes(checkout_bytes)
        self.make_copy()
        (self.tree / "server" / "app.py").write_bytes(b"app" + CONCEALING_SEQUENCE_OF_8_BITS + b"\nmore = 1\n")
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(b"server/app.py holds a character a terminal does not show", bring_back_run.stderr)
        self.assertEqual((self.checkout / "server" / "app.py").read_bytes(), checkout_bytes)

    def test_nothing_comes_back_once_a_formatter_adds_a_carriage_return_to_a_file_without_them(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "dev\N{CARRIAGE RETURN}\n")
        self.assert_nothing_came_back(b"a formatter added to scripts/dev.sh a character a terminal does not show")

    def test_a_carriage_return_inside_a_line_hides_text_even_in_a_file_whose_lines_end_in_one(self) -> None:
        (self.checkout / "scripts" / "dev.sh").write_bytes(b"dev\r\n")
        self.make_copy()
        (self.tree / "scripts" / "dev.sh").write_bytes(b"dev\recho\r\n")
        bring_back_run = self.bring_back()
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(
            b"a formatter added to scripts/dev.sh a character a terminal does not show", bring_back_run.stderr
        )
        self.assertEqual((self.checkout / "scripts" / "dev.sh").read_bytes(), b"dev\r\n")

    def test_nothing_comes_back_once_a_formatter_adds_a_character_outside_ascii(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "dev = \N{CYRILLIC SMALL LETTER A}\n")
        self.assert_nothing_came_back(b"characters outside ASCII")

    def grow_the_copy_of_a_thousand_byte_file_to(self, size_bytes: int) -> subprocess.CompletedProcess[bytes]:
        line_of_a_hundred_bytes = "#" * 99 + "\n"
        self.write("server/app.py", line_of_a_hundred_bytes * 10)
        self.make_copy()
        full_lines, remainder_bytes = divmod(size_bytes, 100)
        self.format_copy("server/app.py", line_of_a_hundred_bytes * full_lines + "#" * (remainder_bytes - 1) + "\n")
        return self.bring_back()

    def test_a_file_grown_to_twice_its_size_and_64_kib_comes_back(self) -> None:
        self.assertEqual(self.grow_the_copy_of_a_thousand_byte_file_to(2 * 1000 + 64 * 1024).returncode, 0)

    def test_nothing_comes_back_once_a_formatter_grows_a_file_past_twice_its_size_and_64_kib(self) -> None:
        bring_back_run = self.grow_the_copy_of_a_thousand_byte_file_to(2 * 1000 + 64 * 1024 + 1)
        self.assertEqual(bring_back_run.returncode, 1)
        self.assertIn(b"grew server/app.py past twice its size and 64 KiB", bring_back_run.stderr)

    def test_nothing_comes_back_once_a_formatter_writes_a_line_far_longer_than_the_file_s(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "dev" + " " * 1000 + "; echo\n")
        self.assert_nothing_came_back(b"a formatter wrote in scripts/dev.sh a line of 1009 characters")

    def test_a_formatter_may_keep_a_long_line_the_file_already_had(self) -> None:
        long_line = "#" * 1500
        self.write("scripts/dev.sh", f"{long_line}\ndev\n")
        self.make_copy()
        self.format_copy("scripts/dev.sh", f"{long_line}\ndev = 1\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(self.read("scripts/dev.sh"), f"{long_line}\ndev = 1\n")

    def test_a_file_the_formatters_leave_unchanged_does_not_hold_back_the_others_for_what_a_terminal_does_not_show(
        self,
    ) -> None:
        self.write("scripts/dev.sh", "dev\N{FORM FEED}\n")
        self.make_copy()
        self.format_copy("server/app.py", "formatted\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(self.read("server/app.py"), "formatted\n")

    def test_a_write_that_fails_midway_names_the_files_brought_back_before_it(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "formatted\n")
        self.format_copy("server/app.py", "formatted\n")
        replace = os.replace

        def fail_on_app_py(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
            if Path(target).name == "app.py":
                raise OSError("disk full")
            replace(source, target)

        with (
            mock.patch("os.replace", fail_on_app_py),
            self.assertRaisesRegex(
                formatting.FormattingRefused,
                r"^writing server/app\.py failed \(disk full\); brought back before it: scripts/dev\.sh$",
            ),
        ):
            formatting.bring_back(self.checkout, self.tree, self.digests_file)
        self.assertEqual(self.read("scripts/dev.sh"), "formatted\n")
        self.assertEqual(self.read("server/app.py"), "app\n")

    def test_a_formatter_may_add_a_line_indented_with_a_tab(self) -> None:
        self.make_copy()
        self.format_copy("scripts/dev.sh", "dev\n\tmore\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(self.read("scripts/dev.sh"), "dev\n\tmore\n")

    def test_a_formatter_may_reformat_a_line_that_holds_characters_outside_ascii(self) -> None:
        self.write("scripts/dev.sh", "caf\N{LATIN SMALL LETTER E WITH ACUTE}  =  1\n")
        self.make_copy()
        self.format_copy("scripts/dev.sh", "caf\N{LATIN SMALL LETTER E WITH ACUTE} = 1\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual(self.read("scripts/dev.sh"), "caf\N{LATIN SMALL LETTER E WITH ACUTE} = 1\n")

    def test_a_file_whose_lines_end_in_a_carriage_return_and_a_line_feed_may_come_back(self) -> None:
        (self.checkout / "scripts" / "dev.sh").write_bytes(b"dev\r\n")
        self.make_copy()
        (self.tree / "scripts" / "dev.sh").write_bytes(b"dev\r\nmore\r\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual((self.checkout / "scripts" / "dev.sh").read_bytes(), b"dev\r\nmore\r\n")

    def test_a_formatter_may_drop_the_carriage_returns_that_end_the_lines_of_a_file(self) -> None:
        (self.checkout / "scripts" / "dev.sh").write_bytes(b"dev\r\nmore\r\n")
        self.make_copy()
        (self.tree / "scripts" / "dev.sh").write_bytes(b"dev\nmore\n")
        self.assertEqual(self.bring_back().returncode, 0)
        self.assertEqual((self.checkout / "scripts" / "dev.sh").read_bytes(), b"dev\nmore\n")


if __name__ == "__main__":
    unittest.main()
