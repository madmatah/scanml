"""The next release from the commits since the last one (scripts/release.py).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from git_environment import build_git_environment

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import release  # noqa: E402
from release import Change  # noqa: E402

CHANGELOG = """# Changelog

The notable changes of each release.

## [Unreleased]

## [0.2.3] - 2026-10-15

### Added

- Scan books

[unreleased]: https://github.com/example/project/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/example/project/tree/v0.2.3
"""


def change(subject: str, body: str = "") -> Change:
    return Change.parse("0123456789abcdef0123456789abcdef01234567", subject, body)


class ChangesTest(unittest.TestCase):
    def test_conventional_commits(self):
        self.assertEqual(
            change("feat(android): scan from the card"),
            Change(
                change("x").commit, "feat(android): scan from the card", "feat", "android", "scan from the card", False
            ),
        )
        self.assertEqual((change("fix: a crash").type, change("fix: a crash").scope), ("fix", None))
        self.assertTrue(change("feat(server)!: drop the old route").breaking)
        self.assertTrue(change("refactor: rename", "Why.\n\nBREAKING CHANGE: the route moved").breaking)
        self.assertTrue(change("refactor: rename", "BREAKING-CHANGE: the route moved").breaking)
        self.assertFalse(change("docs: explain", "Not a BREAKING CHANGE: inline").breaking)
        for subject in ("Fix a crash", "feat:no space", "feat(Android): upper case", "feat: "):
            with self.subTest(subject=subject):
                self.assertIsNone(change(subject).type)

    def test_the_increment(self):
        fix, feat, breaking = change("fix: a"), change("feat: b"), change("refactor!: c")
        self.assertEqual(release.increment([fix, change("docs: d")], (0, 2, 3)), "patch")
        self.assertEqual(release.increment([fix, feat], (0, 2, 3)), "minor")
        self.assertEqual(release.increment([fix, feat, breaking], (0, 2, 3)), "minor", "0.x promises nothing")
        self.assertEqual(release.increment([fix, breaking], (1, 2, 3)), "major")
        self.assertEqual(release.increment([change("Not conventional")], (1, 2, 3)), "patch")

    def test_bump(self):
        self.assertEqual(release.bump((0, 2, 3), "patch"), (0, 2, 4))
        self.assertEqual(release.bump((0, 2, 3), "minor"), (0, 3, 0))
        self.assertEqual(release.bump((0, 2, 3), "major"), (1, 0, 0))
        for last, level in [((0, 99, 3), "minor"), ((0, 2, 99), "patch"), ((999, 0, 0), "major")]:
            with self.subTest(last=last, level=level), self.assertRaises(release.ReleaseError):
                release.bump(last, level)

    def test_the_draft_of_the_changelog(self):
        changes = [
            change("fix(android): a crash"),
            change("feat(server): a route"),
            change("build: a script"),
            change("feat!: a new format"),
            change("feat(cli): a flag"),
            change("Odd one"),
            change("fixup! feat(server): a route"),
        ]
        self.assertEqual(
            release.notes(changes),
            "\n".join(
                [
                    "### Added",
                    "",
                    "- Server: a route",
                    "- Cli: a flag",
                    "",
                    "### Changed",
                    "",
                    "- **Breaking:** A new format",
                    "",
                    "### Fixed",
                    "",
                    "- App: a crash",
                    "",
                ]
            ),
        )
        self.assertEqual(
            release.left_out(changes),
            [
                "- `0123456789ab` build: a script",
                "- `0123456789ab` Odd one",
                "- `0123456789ab` fixup! feat(server): a route",
            ],
        )
        self.assertEqual(release.summary(changes), "1 breaking change, 2 features, 1 fix, 3 other changes")

    def test_a_release_with_nothing_notable_lists_its_changes(self):
        changes = [
            change("docs: explain the setup"),
            change("build(scripts): pin a tool"),
            change("fixup! docs: explain the setup"),
        ]
        self.assertEqual(release.notes(changes), "### Changed\n\n- Explain the setup\n- Scripts: pin a tool\n")
        self.assertEqual(release.left_out(changes), ["- `0123456789ab` fixup! docs: explain the setup"])


class ChangelogTest(unittest.TestCase):
    def test_a_release_s_section_goes_after_unreleased(self):
        updated = release.add_release(CHANGELOG, "0.3.0", "0.2.3", "2026-10-20", "### Added\n\n- App: updates\n")
        self.assertEqual(
            updated,
            CHANGELOG.replace(
                "## [Unreleased]\n",
                "\n".join(
                    [
                        "## [Unreleased]",
                        "",
                        "## [0.3.0] - 2026-10-20",
                        "",
                        "### Added",
                        "",
                        "- App: updates",
                        "",
                    ]
                ),
            ).replace(
                "[unreleased]: https://github.com/example/project/compare/v0.2.3...HEAD\n",
                "[unreleased]: https://github.com/example/project/compare/v0.3.0...HEAD\n"
                "[0.3.0]: https://github.com/example/project/compare/v0.2.3...v0.3.0\n",
            ),
        )

    def test_refusals(self):
        for name, changelog, expected in [
            ("no [Unreleased]", CHANGELOG.replace("## [Unreleased]\n", ""), "no '## [Unreleased]' heading"),
            (
                "entries under [Unreleased]",
                CHANGELOG.replace("## [Unreleased]\n", "## [Unreleased]\n\n- Early\n"),
                "entries under [Unreleased]",
            ),
            ("no link", CHANGELOG.replace("[unreleased]: ", "[later]: "), "no '[unreleased]:"),
            (
                "a link from another release",
                CHANGELOG.replace("v0.2.3...HEAD", "v0.2.2...HEAD"),
                "compares from v0.2.2, not from the last release v0.2.3",
            ),
            ("the release is there", CHANGELOG.replace("## [0.2.3]", "## [0.3.0]"), "already has a section [0.3.0]"),
        ]:
            with self.subTest(name), self.assertRaisesRegex(release.ReleaseError, re.escape(expected)):
                release.add_release(changelog, "0.3.0", "0.2.3", "2026-10-20", "### Added\n\n- App: updates\n")

    def test_completing_a_release_keeps_its_edited_entries(self):
        changelog = release.add_release(
            CHANGELOG,
            "0.3.0",
            "0.2.3",
            "2026-10-20",
            "### Added\n\n- App: updates, edited by hand\n\n### Fixed\n\n- App: a crash\n",
        )
        completed = release.complete_release(
            changelog,
            "0.3.0",
            "### Added\n\n- Server: a route\n\n### Changed\n\n- Scripts: a check\n\n### Fixed\n\n- Server: a leak\n",
        )
        self.assertIn(
            "\n".join(
                [
                    "## [0.3.0] - 2026-10-20",
                    "",
                    "### Added",
                    "",
                    "- App: updates, edited by hand",
                    "- Server: a route",
                    "",
                    "### Changed",
                    "",
                    "- Scripts: a check",
                    "",
                    "### Fixed",
                    "",
                    "- App: a crash",
                    "- Server: a leak",
                    "",
                    "## [0.2.3] - 2026-10-15",
                ]
            ),
            completed,
        )
        # A subsection the section lacks, after the others: at its end.
        completed = release.complete_release(changelog, "0.3.0", "### Security\n\n- Server: a check\n")
        self.assertIn("- App: a crash\n\n### Security\n\n- Server: a check\n\n## [0.2.3]", completed)
        # Keep a Changelog's order, hand-written subsections included.
        edited = changelog.replace("### Fixed\n", "### Removed\n\n- Server: the old route\n\n### Fixed\n")
        completed = release.complete_release(edited, "0.3.0", "### Changed\n\n- **Breaking:** Server: a format\n")
        self.assertIn(
            "- App: updates, edited by hand\n\n### Changed\n\n- **Breaking:** Server: a format\n\n### Removed\n",
            completed,
        )
        # The last section, right before the links.
        completed = release.complete_release(CHANGELOG, "0.2.3", "### Fixed\n\n- OCR: a fix\n")
        self.assertIn("- Scan books\n\n### Fixed\n\n- OCR: a fix\n\n[unreleased]:", completed)
        with self.assertRaisesRegex(release.ReleaseError, re.escape("no section ## [0.4.0]")):
            release.complete_release(CHANGELOG, "0.4.0", "### Fixed\n\n- OCR: a fix\n")

    def test_the_release_base_of_a_commit_message(self):
        commit = "0123456789abcdef0123456789abcdef01234567"
        self.assertEqual(release.release_base(f"chore(release): 0.3.0\n\nWhy.\n\nRelease-Base: {commit}\n"), commit)
        self.assertIsNone(release.release_base("chore(release): 0.3.0\n\nRelease-Base: 0123\n"))
        self.assertIsNone(release.release_base(f"chore(release): 0.3.0\n\nThe Release-Base: {commit}\n"))


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="scanmylib-release-")
        self.addCleanup(directory.cleanup)
        self.repository = Path(directory.name)
        self.git("init", "--quiet", "--initial-branch=main")
        (self.repository / "VERSION").write_text("0.2.3\n")
        (self.repository / "CHANGELOG.md").write_text(CHANGELOG)
        self.git("add", "VERSION", "CHANGELOG.md")
        self.git("commit", "--quiet", "--message", "chore(release): 0.2.3")
        self.git("tag", "--annotate", "v0.2.3", "--message", "ScanMyLib 0.2.3")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repository,
            env=build_git_environment(os.environ),
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def commit(self, message: str) -> str:
        self.git("commit", "--quiet", "--allow-empty", "--message", message)
        return self.git("rev-parse", "HEAD").strip()

    def release(self, *args: str) -> subprocess.CompletedProcess:
        if "--commit" in args:
            self.git("update-ref", "refs/remotes/origin/main", "main")  # main as fetched from origin
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "release.py"), *args],
            cwd=self.repository,
            env=build_git_environment(os.environ),
            capture_output=True,
            text=True,
            check=False,
        )

    def today(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    def test_the_next_release_and_its_notes(self):
        self.commit("fix(android): a crash")
        self.commit("feat(android): scan from the card")
        self.commit("docs: explain the card")
        result = self.release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[:5],
            [
                "Last release: 0.2.3 (v0.2.3)",
                "Commits since: 3 (1 feature, 1 fix, 1 other change)",
                "Next release: 0.3.0, a minor release (new features)",
                "",
                f"## [0.3.0] - {self.today()}",
            ],
        )
        self.assertIn("### Added\n\n- App: scan from the card\n\n### Fixed\n\n- App: a crash\n", result.stdout)
        self.assertRegex(result.stdout, r"Not in the changelog .*:\n- `[0-9a-f]{12}` docs: explain the card\n$")
        self.assertEqual(self.release("--version-only").stdout, "0.3.0\n")
        self.assertTrue(self.release("--notes-only").stdout.startswith("### Added\n"))
        self.assertEqual(self.release("--bump", "major", "--version-only").stdout, "1.0.0\n")
        self.assertIn(
            "a major release (--bump major; the commits give a minor release)", self.release("--bump", "major").stdout
        )
        self.assertIn("a patch release", self.release("--ref", "HEAD~2").stdout)
        self.assertEqual(self.git("status", "--porcelain"), "", "it changes nothing")

    def test_a_breaking_change_before_1_0(self):
        self.commit("refactor(server)!: move the routes")
        result = self.release()
        self.assertIn("Next release: 0.3.0, a minor release (breaking changes, before 1.0)", result.stdout)
        self.assertIn("### Changed\n\n- **Breaking:** Server: move the routes\n", result.stdout)

    def test_odd_commits_are_named(self):
        self.commit("Update things")
        result = self.release("--version-only")
        self.assertEqual(result.stdout, "0.2.4\n")
        self.assertIn("not a Conventional Commit, released as a patch", result.stderr)
        self.assertIn("Update things", result.stderr)

    def test_refusals(self):
        result = self.release()
        self.assertEqual(result.returncode, 1)
        self.assertIn("nothing to release", result.stderr)
        self.commit("feat: a")
        self.commit("fixup! feat: a")
        result = self.release()
        self.assertEqual(result.returncode, 1)
        self.assertIn("commits still to fold", result.stderr)
        self.assertEqual(result.stdout, "")
        # Unless they reached main for good: main's history is never rewritten.
        result = self.release("--allow-unfolded")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("released as it is, not folded", result.stderr)
        self.assertNotIn("not a Conventional Commit", result.stderr)
        self.assertRegex(result.stdout, r"\n- `[0-9a-f]{12}` fixup! feat: a\n")
        self.assertIn("Next release: 0.3.0", result.stdout)
        # VERSION changed without a release commit, or tags not fetched.
        self.git("reset", "--quiet", "--hard", "v0.2.3")
        (self.repository / "VERSION").write_text("0.3.0\n")
        self.git("commit", "--quiet", "--all", "--message", "build: set VERSION by hand")
        result = self.release()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no tag v0.3.0 nor a release commit 'chore(release): 0.3.0'", result.stderr)
        result = self.release("--ref", "nonexistent")
        self.assertEqual(result.returncode, 1)
        self.assertIn("error:", result.stderr)

    def test_commit(self):
        self.commit("fix(android): a crash")
        base = self.commit("feat(android): scan from the card")
        self.git("switch", "--quiet", "-c", "release/v0.3.0")
        result = self.release("--commit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.git("log", "-1", "--format=%B").rstrip("\n").split("\n\n"),
            [
                "chore(release): 0.3.0",
                "Release 0.3.0 (a minor release): 1 feature, 1 fix since v0.2.3. Its notes are its section of "
                "CHANGELOG.md.",
                f"Release-Base: {base}",
            ],
        )
        self.assertEqual(self.git("rev-parse", "HEAD~1").strip(), base)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["CHANGELOG.md", "VERSION"])
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual((self.repository / "VERSION").read_text(), "0.3.0\n")
        changelog = (self.repository / "CHANGELOG.md").read_text()
        self.assertIn(
            f"## [Unreleased]\n\n## [0.3.0] - {self.today()}\n\n### Added\n\n- App: scan from the card\n\n"
            "### Fixed\n\n- App: a crash\n\n## [0.2.3] - 2026-10-15\n",
            changelog,
        )
        self.assertIn(
            "[unreleased]: https://github.com/example/project/compare/v0.3.0...HEAD\n"
            "[0.3.0]: https://github.com/example/project/compare/v0.2.3...v0.3.0\n",
            changelog,
        )
        # The pull request's description: what merging it does, then the notes it publishes.
        self.assertEqual(
            result.stdout,
            "\n".join(
                [
                    "Merging this pull request publishes ScanMyLib 0.3.0: `.github/workflows/release.yml` tags `v0.3.0` and "
                    "creates the GitHub release with the notes below. Merge nothing else before it.",
                    "",
                    f"## [0.3.0](https://github.com/example/project/compare/v0.2.3...v0.3.0) - {self.today()}",
                    "",
                    "### Added",
                    "",
                    "- App: scan from the card",
                    "",
                    "### Fixed",
                    "",
                    "- App: a crash",
                    "",
                ]
            ),
        )

    def test_the_description_follows_the_edited_notes(self):
        self.commit("feat(android): scan from the card")
        self.git("switch", "--quiet", "-c", "release/v0.3.0")
        first = self.release("--commit").stdout
        changelog = self.repository / "CHANGELOG.md"
        changelog.write_text(changelog.read_text().replace("scan from the card", "scan straight from the card"))
        self.git("commit", "--quiet", "--all", "--amend", "--no-edit")
        result = self.release("--description")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, first.replace("scan from the card", "scan straight from the card"))
        self.assertEqual(self.release("--description", "--ref", "HEAD").stdout, result.stdout)
        result = self.release("--description", "--ref", "nonexistent")
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("error:", result.stderr)
        # Not for a section without entries, nor for a version released already.
        changelog.write_text(changelog.read_text().replace("- App: scan straight from the card\n", ""))
        self.git("commit", "--quiet", "--all", "--amend", "--no-edit")
        result = self.release("--description")
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("the section [0.3.0] of CHANGELOG.md has no entry", result.stderr)
        result = self.release("--description", "--ref", "v0.2.3")
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("0.2.3 is released already", result.stderr)

    def test_commit_with_an_increment_chosen_by_hand(self):
        (self.repository / "VERSION").write_text("0.2.99\n")
        self.git("commit", "--quiet", "--all", "--message", "chore(release): 0.2.99")
        self.git("tag", "--annotate", "v0.2.99", "--message", "ScanMyLib 0.2.99")
        (self.repository / "CHANGELOG.md").write_text(CHANGELOG.replace("v0.2.3...HEAD", "v0.2.99...HEAD"))
        self.git("commit", "--quiet", "--all", "--message", "fix: a crash")
        self.git("switch", "--quiet", "-c", "release")
        result = self.release("--commit")
        self.assertEqual(result.returncode, 1)
        self.assertIn("0.2.100 is past what VERSION allows", result.stderr)
        result = self.release("--bump", "minor", "--commit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "Release 0.3.0 (a minor release chosen by hand): 1 fix since v0.2.99.", self.git("log", "-1", "--format=%B")
        )

    def test_a_release_is_prepared_on_main_as_on_origin(self):
        # Rebase and merge rewrites the commits of a pull request: the commit the notes are
        # written on must be one of main's.
        self.commit("feat: a")
        self.git("switch", "--quiet", "-c", "release")
        self.commit("docs: a note")
        result = self.release("--commit")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not in origin/main", result.stderr)

    def test_commit_refusals(self):
        self.commit("feat: a")
        for name, prepare, args, expected in [
            ("on main", lambda: None, (), "prepare the release on its own branch, not on main"),
            (
                "another commit",
                lambda: self.git("switch", "--quiet", "-c", "release"),
                ("--ref", "HEAD~1"),
                "--commit prepares HEAD",
            ),
            ("changes", lambda: (self.repository / "VERSION").write_text("9.9.9\n"), (), "commit or stash"),
        ]:
            with self.subTest(name):
                prepare()
                result = self.release("--commit", *args)
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)
                self.assertEqual(result.stdout, "")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "feat: a\n")

    def merge_release(self, branch: str) -> None:
        """Merges the release branch into main as "Rebase and merge" does: its commits replayed on main."""
        self.git("switch", "--quiet", "main")
        self.git("cherry-pick", "main.." + branch)

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def prepare_release(self, *edits: str) -> None:
        """A release branch from main: its release commit, then commits that only edit CHANGELOG.md."""
        self.git("switch", "--quiet", "-c", "release/v0.3.0")
        self.assertEqual(self.release("--commit").returncode, 0)
        changelog = self.repository / "CHANGELOG.md"
        for old, new in zip(edits[0::2], edits[1::2]):
            changelog.write_text(changelog.read_text().replace(old, new))
            self.git("commit", "--quiet", "--all", "--message", "Update CHANGELOG.md")  # a suggestion, on GitHub
        self.git("switch", "--quiet", "main")

    def test_completing_a_release_after_a_merge_in_between(self):
        self.commit("feat(android): scan from the card")
        self.prepare_release()
        self.commit("fix(server): a leak")  # merged while the release pull request was open
        self.merge_release("release/v0.3.0")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "chore(release): 0.3.0\n")
        result = self.release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines()[:2],
            [
                "Release to complete: 0.3.0 (VERSION, not tagged: its release commit could not be published)",
                "Commits its notes miss: 1 (1 fix)",
            ],
        )
        self.assertIn("### Fixed\n\n- Server: a leak\n", result.stdout)
        result = self.release("--bump", "patch")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no --bump", result.stderr)
        base = self.head()
        self.git("switch", "--quiet", "-c", "release/v0.3.0-complete")
        result = self.release("--commit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("Merging this pull request publishes ScanMyLib 0.3.0"), result.stdout)
        self.assertIn("### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n", result.stdout)
        self.assertEqual(
            self.git("log", "-1", "--format=%s%n%(trailers:key=Release-Base,valueonly)").split(),
            ["chore(release):", "0.3.0", base],
        )
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["CHANGELOG.md"])
        changelog = (self.repository / "CHANGELOG.md").read_text()
        self.assertIn(
            "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n\n## [0.2.3]", changelog
        )
        # Once merged, the release can be published as it is: it waits for its workflow.
        self.merge_release("release/v0.3.0-complete")
        result = self.release()
        self.assertEqual(result.returncode, 1)
        self.assertIn("can be published as it is", result.stderr)

    def test_completing_leaves_out_what_the_notes_need_not_list(self):
        self.commit("feat(android): scan from the card")
        self.prepare_release("scan from the card", "scan straight from the card")
        self.commit("docs: explain the card")
        self.commit("fix(server): a leak")
        self.merge_release("release/v0.3.0")
        result = self.release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Commits its notes miss: 2 (1 fix, 1 other change)", result.stdout)
        self.assertIn("### Fixed\n\n- Server: a leak\n", result.stdout)
        self.assertNotIn("Update CHANGELOG.md", result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"Not in the changelog .*:\n- `[0-9a-f]{12}` docs: explain the card\n$")

    def test_a_release_that_can_be_published_is_not_completed(self):
        self.commit("feat(android): scan from the card")
        self.prepare_release()
        # Merged in between: a commit the notes need not list, and an edit of the changelog alone,
        # whatever its type.
        self.commit("test(server): cover the route")
        with (self.repository / "CHANGELOG.md").open("a") as changelog:
            changelog.write("\n")
        self.git("commit", "--quiet", "--all", "--message", "fix: the notes of 0.2.3")
        self.merge_release("release/v0.3.0")
        release_commit = self.head()
        # After it, a commit of the next release (or its tag is not fetched yet).
        self.commit("feat(server): a later feature")
        result = self.release()
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"the release 0.3.0 can be published as it is, on {release_commit[:12]}", result.stderr)
        self.assertIn("git fetch --tags origin", result.stderr)

    def test_completing_a_release_whose_section_has_no_entry(self):
        # Its entries removed in its pull request (a heading left alone), then other commits merged:
        # the section is written again from the release's commits.
        self.commit("feat(android): scan from the card")
        self.commit("fix(server): a crash")
        self.prepare_release("- App: scan from the card\n\n### Fixed\n\n- Server: a crash\n", "")
        self.merge_release("release/v0.3.0")
        self.commit("docs: explain the card")
        self.commit("fix(web): a later fix")
        result = self.release()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Commits since v0.2.3: 4 (1 feature, 2 fixes, 1 other change)", result.stdout)
        self.assertIn(
            "Its section of CHANGELOG.md, written again:\n\n### Added\n\n- App: scan from the card\n\n"
            "### Fixed\n\n- Server: a crash\n- Web UI: a later fix\n",
            result.stdout,
        )
        self.git("switch", "--quiet", "-c", "release/v0.3.0-complete")
        result = self.release("--commit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("### Fixed\n\n- Server: a crash\n- Web UI: a later fix\n", result.stdout)
        changelog = (self.repository / "CHANGELOG.md").read_text()
        self.assertRegex(
            changelog,
            r"## \[0\.3\.0\] - \d{4}-\d\d-\d\d\n\n### Added\n\n- App: scan from the card\n\n"
            r"### Fixed\n\n- Server: a crash\n- Web UI: a later fix\n\n## \[0\.2\.3\]",
        )

    def test_completing_a_release_whose_section_is_missing(self):
        self.commit("feat(android): scan from the card")
        self.prepare_release("## [0.3.0] - ", "## 0.3.0 - ")
        self.merge_release("release/v0.3.0")
        self.commit("fix(server): a leak")
        self.git("switch", "--quiet", "-c", "release/v0.3.0-complete")
        result = self.release("--commit")
        self.assertEqual(result.returncode, 0, result.stderr)
        changelog = (self.repository / "CHANGELOG.md").read_text()
        self.assertRegex(
            changelog,
            r"## \[Unreleased\]\n\n## \[0\.3\.0\] - \d{4}-\d\d-\d\d\n\n### Added\n\n"
            r"- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n\n## 0\.3\.0 - ",
        )

    def test_a_release_merged_alone_waits_for_its_workflow(self):
        self.commit("feat(android): scan from the card")
        self.prepare_release()
        self.merge_release("release/v0.3.0")
        result = self.release()
        self.assertEqual(result.returncode, 1)
        self.assertIn("can be published as it is", result.stderr)
        self.assertIn(".github/workflows/release.yml publishes it", result.stderr)

    def to_publish(self, ref: str = "HEAD") -> subprocess.CompletedProcess:
        return self.release("--ref", ref, "--to-publish", str(self.repository / ".git" / "notes.md"))

    def published(self, ref: str = "HEAD") -> tuple[str, str]:
        """The version --to-publish publishes and the commit it tags."""
        result = self.to_publish(ref)
        self.assertEqual(result.returncode, 0, result.stderr)
        version, commit = result.stdout.split()
        return version, commit

    def notes(self) -> str:
        return (self.repository / ".git" / "notes.md").read_text()

    def test_publishing_a_merged_release(self):
        self.commit("feat(android): scan from the card")
        self.commit("fix(server): a leak")
        self.prepare_release()
        self.merge_release("release/v0.3.0")
        release_commit = self.head()
        self.assertEqual(self.published(), ("0.3.0", release_commit))
        self.assertEqual(self.notes(), "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n")
        # Run again once tagged (the GitHub release failed): it is still to finish.
        self.git("tag", "--annotate", "v0.3.0", "--message", "ScanMyLib 0.3.0")
        self.assertEqual(self.published(), ("0.3.0", release_commit))
        # A later change to the changelog publishes nothing.
        with (self.repository / "CHANGELOG.md").open("a") as changelog:
            changelog.write("\n")
        self.git("commit", "--quiet", "--all", "--message", "docs: fix the changelog")
        result = self.to_publish()
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        self.assertIn("nothing to publish", result.stderr)
        self.assertEqual(self.published(release_commit), ("0.3.0", release_commit))

    def test_publishing_refuses_a_release_with_commits_merged_in_between(self):
        self.commit("feat(android): scan from the card")
        self.prepare_release()
        self.commit("fix(server): a leak")
        self.merge_release("release/v0.3.0")
        result = self.to_publish()
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertRegex(
            result.stderr,
            r"miss features, fixes or breaking changes merged after [0-9a-f]{12}, the "
            r"commit they were written on:\n  [0-9a-f]{12} fix\(server\): a leak\n",
        )
        self.assertIn("completes the release 0.3.0", result.stderr)
        # Completed in a pull request of its own, it is published with all its notes.
        self.git("switch", "--quiet", "-c", "release/v0.3.0-complete")
        self.assertEqual(self.release("--commit").returncode, 0)
        self.merge_release("release/v0.3.0-complete")
        self.assertEqual(self.published(), ("0.3.0", self.head()))
        self.assertEqual(self.notes(), "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n")

    def test_publishing_the_notes_edited_after_the_release_commit(self):
        # Edited in its pull request (suggestions, on GitHub), with commits the notes need not list
        # and an edit of the changelog alone merged in between: published with the edited notes.
        self.commit("feat(android): scan from the card")
        self.prepare_release("scan from the card", "scan straight from the card")
        self.commit("docs: explain the card")
        with (self.repository / "CHANGELOG.md").open("a") as changelog:
            changelog.write("\n")
        self.git("commit", "--quiet", "--all", "--message", "fix: the notes of 0.2.3")
        self.merge_release("release/v0.3.0")
        edited = self.head()
        self.assertEqual(self.published(), ("0.3.0", edited))
        self.assertEqual(self.notes(), "### Added\n\n- App: scan straight from the card\n")
        # Later commits belong to the next release, whatever they change.
        self.commit("feat(server): a later feature")
        with (self.repository / "CHANGELOG.md").open("a") as changelog:
            changelog.write("\n")
        self.git("commit", "--quiet", "--all", "--message", "Update CHANGELOG.md")
        self.assertEqual(self.published(), ("0.3.0", edited))

    def test_a_commit_after_the_release_commit_belongs_to_the_next_release(self):
        # Pushed to the release branch after its release commit, or merged with it.
        self.commit("feat(android): scan from the card")
        self.prepare_release()
        self.git("switch", "--quiet", "release/v0.3.0")
        release_commit = self.head()
        self.commit("fix(server): a last-minute leak")
        self.git("switch", "--quiet", "-c", "side", "HEAD~2")
        self.commit("fix(server): another leak")
        self.git("switch", "--quiet", "release/v0.3.0")
        self.git("merge", "--quiet", "--no-ff", "--no-edit", "side")
        self.assertEqual(self.published(), ("0.3.0", release_commit))

    def test_publishing_refuses_an_empty_section_until_it_is_written(self):
        self.commit("feat(android): scan from the card")
        self.prepare_release("### Added\n\n- App: scan from the card\n\n", "")
        self.merge_release("release/v0.3.0")
        result = self.to_publish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("the section [0.3.0] of CHANGELOG.md has no entry, or is missing", result.stderr)
        # A pull request that only writes the section publishes the release.
        changelog = self.repository / "CHANGELOG.md"
        changelog.write_text(
            changelog.read_text()
            .replace("## [0.3.0] - ", "## [0.3.0] - ", 1)
            .replace("\n## [0.2.3]", "### Added\n\n- App: scan from the card\n\n## [0.2.3]", 1)
        )
        self.git("commit", "--quiet", "--all", "--message", "docs: write the notes of 0.3.0")
        self.assertEqual(self.published(), ("0.3.0", self.head()))
        self.assertEqual(self.notes(), "### Added\n\n- App: scan from the card\n")

    def test_publishing_refuses_anything_but_a_release(self):
        self.commit("feat: a")
        (self.repository / "VERSION").write_text("0.3.0\n")
        self.git("commit", "--quiet", "--all", "--message", "build: set VERSION by hand")
        result = self.to_publish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("no release commit 'chore(release): 0.3.0'", result.stderr)
        changelog = self.repository / "CHANGELOG.md"
        changelog.write_text(
            changelog.read_text().replace("## [0.2.3]", "## [0.3.0] - 2026-10-20\n\n### Added\n\n- A\n\n## [0.2.3]")
        )
        self.git("commit", "--quiet", "--all", "--message", "chore(release): 0.3.0")  # by hand: no trailer
        result = self.to_publish()
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no 'Release-Base' trailer", result.stderr)
        # A version tagged before release commits had a Release-Base: nothing to publish.
        self.git("reset", "--quiet", "--hard", "v0.2.3")
        with (self.repository / "CHANGELOG.md").open("a") as changelog:
            changelog.write("\n")
        self.git("commit", "--quiet", "--all", "--message", "docs: start the changelog")
        result = self.to_publish()
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)


class WorkflowTest(unittest.TestCase):
    """The release workflow is the only one that writes to the repository, and runs nothing else."""

    WORKFLOWS = SCRIPTS.parent / ".github" / "workflows"
    #: Any permission that writes, quoted or not, comments included.
    WRITES = r"[\"']?[a-z-]+[\"']?\s*:\s*[\"']?write\b[\"']?|\bwrite-all\b"

    def test_what_counts_as_writing(self):
        for text in (
            'contents: "write"',
            "pull-requests:\twrite",
            "permissions: write-all",
            "contents: write  # x",
            "contents: 'write'",
            '"contents": write',
            "'pull-requests': write",
            "contents : write",
            'permissions: {"contents": write}',
        ):
            with self.subTest(text):
                self.assertTrue(re.findall(self.WRITES, text))
        self.assertEqual(re.findall(self.WRITES, "contents: read\n# it writes nothing\n"), [])

    def test_only_the_release_workflow_writes(self):
        workflows = sorted(self.WORKFLOWS.glob("*.y*ml"))
        self.assertEqual([workflow.name for workflow in workflows], ["ci.yml", "release.yml"])
        for workflow in workflows:
            with self.subTest(workflow.name):
                text = workflow.read_text()
                self.assertNotIn("secrets.", text)
                self.assertNotRegex(text, r"\bpull_request_target\b")
                for action in re.findall(r"^\s*(?:- )?uses: (\S+)", text, re.MULTILINE):
                    self.assertRegex(action, r"^actions/checkout@[0-9a-f]{40}$|^actions/cache@[0-9a-f]{40}$")
                writes = re.findall(self.WRITES, text)
                if workflow.name == "release.yml":
                    self.assertEqual(writes, ["contents: write"])
                else:
                    self.assertEqual(writes, [])
                    self.assertRegex(text, r"\npermissions:\n  contents: read\n")

    def test_the_release_workflow(self):
        text = (self.WORKFLOWS / "release.yml").read_text()
        on = text.split("\non:\n", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(on, "  push:\n    branches: [main]\n    paths: [VERSION, CHANGELOG.md]")
        self.assertIn("\npermissions: {}\n", text)
        self.assertIn("persist-credentials: false", text)
        # scripts/release.py reads the history and the tags.
        self.assertIn("fetch-depth: 0", text)
        self.assertEqual(
            re.findall(r"uses: (\S+)", text), ["actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"]
        )
        self.assertIn('python3 scripts/release.py --ref "$COMMIT" --to-publish', text)
        # It tags the commit release.py names, never the push's head.
        self.assertIn('read -r version target <<< "$release"', text)
        self.assertIn('-f object="$target"', text)
        self.assertEqual(text.count("$COMMIT"), 1)


if __name__ == "__main__":
    unittest.main()
