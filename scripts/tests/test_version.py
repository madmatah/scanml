"""The versions of releases and development builds (scripts/lib/version.py).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from git_environment import build_git_environment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import version


def git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        env=build_git_environment(os.environ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class ReleaseTest(unittest.TestCase):
    def test_a_release_and_its_version_code(self) -> None:
        self.assertEqual(version.parse_release("0.2.3\n"), (0, 2, 3))
        self.assertEqual(version.release_code((0, 2, 3)), 203)
        self.assertEqual(version.release_code((1, 10, 0)), 11000)
        self.assertEqual(version.format_release((12, 0, 99)), "12.0.99")

    def test_anything_else_is_refused(self) -> None:
        for text in (
            "0.2",
            "0.2.3.4",
            "v0.2.3",
            "0.100.0",
            "0.2.100",
            "1000.0.0",
            "0.02.3",
            "0.2.3-dev",
            "١.2.3",
            "",
            "0.2.3 0.2.4",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                version.parse_release(text)


class DevVersionTest(unittest.TestCase):
    def setUp(self) -> None:
        # version.py runs git in this process, with its environment.
        isolated_environment = mock.patch.dict(os.environ, build_git_environment(os.environ), clear=True)
        isolated_environment.start()
        self.addCleanup(isolated_environment.stop)
        directory = tempfile.TemporaryDirectory(prefix="scanmylib-version-")
        self.addCleanup(directory.cleanup)
        self.repository = Path(directory.name)
        git(self.repository, "init", "--quiet", "--initial-branch=main")
        (self.repository / "VERSION").write_text("0.2.3\n")
        git(self.repository, "add", "VERSION")
        git(self.repository, "commit", "--quiet", "--message", "chore(release): 0.2.3")

    def commit(self, message: str) -> str:
        git(self.repository, "commit", "--quiet", "--allow-empty", "--message", message)
        return git(self.repository, "rev-parse", "HEAD")

    def test_the_next_patch_then_the_commit(self) -> None:
        head = git(self.repository, "rev-parse", "HEAD")
        self.assertEqual(version.dev_version(self.repository, (0, 2, 3)), f"0.2.4-dev+g{head[:12]}")

    def test_the_commits_since_the_release_s_tag(self) -> None:
        git(self.repository, "tag", "--annotate", "v0.2.3", "--message", "ScanMyLib 0.2.3")
        self.assertRegex(version.dev_version(self.repository, (0, 2, 3)), r"^0\.2\.4-dev\.0\+g[0-9a-f]{12}$")
        self.commit("feat: one")
        head = self.commit("fix: two")
        self.assertEqual(version.dev_version(self.repository, (0, 2, 3)), f"0.2.4-dev.2+g{head[:12]}")

    def test_uncommitted_changes_are_dirty(self) -> None:
        (self.repository / "untracked.txt").write_text("not part of the build's version\n")
        self.assertNotIn("dirty", version.dev_version(self.repository, (0, 2, 3)))
        (self.repository / "VERSION").write_text("0.2.3\n\n")
        self.assertRegex(version.dev_version(self.repository, (0, 2, 3)), r"^0\.2\.4-dev\+g[0-9a-f]{12}\.dirty$")

    def test_outside_a_checkout_only_the_next_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(version.dev_version(Path(directory), (0, 2, 3)), "0.2.4-dev")

    def test_the_version_code_is_the_time_of_the_build(self) -> None:
        start = version.DEV_CODE_EPOCH
        self.assertEqual(version.dev_code(start + timedelta(minutes=1, seconds=59)), 1)
        self.assertEqual(version.dev_code(datetime(2026, 10, 17, tzinfo=UTC)), 416160)
        later = version.dev_code(datetime(2027, 1, 1, tzinfo=UTC))
        self.assertGreater(later, version.dev_code(datetime(2026, 12, 31, 23, 59, tzinfo=UTC)))
        for wrong in (start, start - timedelta(days=1), start + timedelta(minutes=version.MAX_VERSION_CODE + 1)):
            with self.subTest(clock=wrong), self.assertRaises(ValueError):
                version.dev_code(wrong)

    def test_the_version_code_stays_above_the_published_one(self) -> None:
        now = datetime(2026, 10, 17, 10, 0, 50, tzinfo=UTC)
        minutes = version.dev_code(now)
        self.assertEqual(version.dev_code(now, minutes - 5), minutes)
        self.assertEqual(version.dev_code(now, minutes), minutes + 1, "a second build in the same minute")
        self.assertEqual(version.dev_code(now, minutes + 7), minutes + 8)
        with self.assertRaises(ValueError):
            version.dev_code(now, version.MAX_VERSION_CODE)
        metadata = self.repository / "scanmylib.json"
        for text, expected in [
            ('{"version_code": 416760}', 416760),
            ('{"version_code": "416760"}', None),
            ('{"version_code": true}', None),
            ("[1]", None),
            ("not json", None),
        ]:
            with self.subTest(text=text):
                metadata.write_text(text)
                self.assertEqual(version.published_code(metadata), expected)
        self.assertIsNone(version.published_code(self.repository / "missing.json"))

    def test_command_line(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(version.main(["release", str(self.repository)]), 0)
        self.assertEqual(output.getvalue(), "0.2.3 203\n")
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(version.main(["dev", str(self.repository)]), 0)
        self.assertRegex(output.getvalue(), r"^0\.2\.4-dev\+g[0-9a-f]{12} [0-9]+\n$")
        (self.repository / "scanmylib.json").write_text('{"version_code": 2000000000}')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(version.main(["dev", str(self.repository), str(self.repository / "scanmylib.json")]), 0)
        self.assertTrue(output.getvalue().endswith(" 2000000001\n"), output.getvalue())
        (self.repository / "VERSION").write_text("0.2\n")
        with redirect_stderr(errors):
            self.assertEqual(version.main(["dev", str(self.repository)]), 1)
            self.assertEqual(version.main(["next", str(self.repository)]), 2)
        self.assertIn("MAJOR.MINOR.PATCH", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
