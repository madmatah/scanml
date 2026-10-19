"""The next release from the commits since the last one (scripts/release.py), and the workflows that publish it
(.github/workflows/).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import datetime
import functools
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from git_environment import build_git_environment, read_head, run_git

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import release  # noqa: E402 (scripts/release.py, found once scripts/ is on the path)
from release import Change  # noqa: E402 (the same module)

COMMIT = "0123456789abcdef0123456789abcdef01234567"
CHANGELOG = """# Changelog

The notable changes of each release.

## [Unreleased]

## [0.2.3] - 2026-10-15

### Added

- Scan books

[unreleased]: https://github.com/example/project/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/example/project/tree/v0.2.3
"""
SECTION_EDITED_IN_ITS_PULL_REQUEST = "### Added\n\n- App: updates, edited by hand\n\n### Fixed\n\n- App: a crash\n"
SUBJECTS_OF_EVERY_KIND = (
    "fix(android): a crash",
    "feat(server): a route",
    "build: a script",
    "feat!: a new format",
    "feat(cli): a flag",
    "Odd one",
    "fixup! feat(server): a route",
)
SUBJECTS_WITHOUT_NOTES = ("docs: explain the setup", "build(scripts): pin a tool", "fixup! docs: explain the setup")


def parse_changes(*subjects: str) -> list[Change]:
    return [Change.parse(COMMIT, subject, "") for subject in subjects]


def commit_nothing(repository: Path, message: str) -> str:
    run_git(repository, "commit", "--quiet", "--allow-empty", "--message", message)
    return read_head(repository)


def commit_everything(repository: Path, message: str) -> None:
    run_git(repository, "commit", "--quiet", "--all", "--message", message)


def append_a_blank_line_to_the_changelog(repository: Path) -> None:
    with (repository / "CHANGELOG.md").open("a") as changelog:
        changelog.write("\n")


def replace_in_the_changelog(repository: Path, old: str, new: str) -> None:
    changelog = repository / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().replace(old, new))


def make_repository(test_case: type[unittest.TestCase]) -> Path:
    repository = Path(test_case.enterClassContext(tempfile.TemporaryDirectory(prefix="scanmylib-release-")))
    run_git(repository, "init", "--quiet", "--initial-branch=main")
    (repository / "VERSION").write_text("0.2.3\n")
    (repository / "CHANGELOG.md").write_text(CHANGELOG)
    run_git(repository, "add", "VERSION", "CHANGELOG.md")
    run_git(repository, "commit", "--quiet", "--message", "chore(release): 0.2.3")
    run_git(repository, "tag", "--annotate", "v0.2.3", "--message", "ScanMyLib 0.2.3")
    return repository


def run_release(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "release.py"), *arguments],
        cwd=repository,
        env=build_git_environment(os.environ),
        capture_output=True,
        text=True,
        check=False,
    )


def run_release_commit(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    # main as fetched from origin, which --commit prepares the release on.
    run_git(repository, "update-ref", "refs/remotes/origin/main", "main")
    return run_release(repository, "--commit", *arguments)


def prepare_release(repository: Path, *edits: str) -> None:
    run_git(repository, "switch", "--quiet", "-c", "release/v0.3.0")
    run_release_commit(repository).check_returncode()
    # As the suggestions of a release pull request on GitHub do.
    for old, new in zip(edits[0::2], edits[1::2], strict=True):
        replace_in_the_changelog(repository, old, new)
        commit_everything(repository, "Update CHANGELOG.md")
    run_git(repository, "switch", "--quiet", "main")


def merge_release(repository: Path, branch: str) -> None:
    run_git(repository, "switch", "--quiet", "main")
    # As "Rebase and merge" does on GitHub.
    run_git(repository, "cherry-pick", "main.." + branch)


def run_to_publish(repository: Path, ref: str = "HEAD") -> subprocess.CompletedProcess[str]:
    return run_release(repository, "--ref", ref, "--to-publish", str(repository / ".git" / "notes.md"))


def read_notes(repository: Path) -> str:
    return (repository / ".git" / "notes.md").read_text()


def read_today() -> str:
    return datetime.datetime.now(datetime.UTC).date().isoformat()


class TheChangeParseMethodWhenTheSubjectFollowsConventionalCommits(unittest.TestCase):
    def setUp(self) -> None:
        self.change = Change.parse(COMMIT, "feat(android): scan from the card", "")

    def test_should_read_its_type_scope_and_summary(self) -> None:
        self.assertEqual(
            self.change,
            Change(COMMIT, "feat(android): scan from the card", "feat", "android", "scan from the card", False),
        )


class TheChangeParseMethodWhenTheSubjectHasNoScope(unittest.TestCase):
    def setUp(self) -> None:
        self.change = Change.parse(COMMIT, "fix: a crash", "")

    def test_should_read_its_type_and_no_scope(self) -> None:
        self.assertEqual((self.change.type, self.change.scope), ("fix", None))


class TheChangeParseMethodWhenTheTypeIsMarkedBreaking(unittest.TestCase):
    def setUp(self) -> None:
        self.change = Change.parse(COMMIT, "feat(server)!: drop the old route", "")

    def test_should_be_a_breaking_change(self) -> None:
        self.assertTrue(self.change.breaking)


class TheChangeParseMethodWhenTheBodyHasABreakingChangeFooter(unittest.TestCase):
    bodies: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {
            "BREAKING CHANGE": "Why.\n\nBREAKING CHANGE: the route moved",
            "BREAKING-CHANGE": "BREAKING-CHANGE: the route moved",
        }
    )

    def setUp(self) -> None:
        self.breaking = {
            row: Change.parse(COMMIT, "refactor: rename", body).breaking for row, body in self.bodies.items()
        }

    def test_should_be_a_breaking_change(self) -> None:
        for row in self.bodies:
            with self.subTest(row):
                self.assertTrue(self.breaking[row])


class TheChangeParseMethodWhenTheBodyMentionsABreakingChangeInsideALine(unittest.TestCase):
    def setUp(self) -> None:
        self.change = Change.parse(COMMIT, "docs: explain", "Not a BREAKING CHANGE: inline")

    def test_should_not_be_a_breaking_change(self) -> None:
        self.assertFalse(self.change.breaking)


class TheChangeParseMethodWhenTheSubjectDoesNotFollowConventionalCommits(unittest.TestCase):
    subjects: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {
            "no type": "Fix a crash",
            "no space after the colon": "feat:no space",
            "an uppercase scope": "feat(Android): upper case",
            "no summary": "feat: ",
        }
    )

    def setUp(self) -> None:
        self.types = {row: Change.parse(COMMIT, subject, "").type for row, subject in self.subjects.items()}

    def test_should_read_no_type(self) -> None:
        for row in self.subjects:
            with self.subTest(row):
                self.assertIsNone(self.types[row])


class TheIncrementFunctionWhenTheChangesHoldFixesAndOtherChanges(unittest.TestCase):
    def setUp(self) -> None:
        self.increment = release.increment(parse_changes("fix: a", "docs: d"), (0, 2, 3))

    def test_should_be_a_patch(self) -> None:
        self.assertEqual(self.increment, "patch")


class TheIncrementFunctionWhenTheChangesHoldAFeature(unittest.TestCase):
    def setUp(self) -> None:
        self.increment = release.increment(parse_changes("fix: a", "feat: b"), (0, 2, 3))

    def test_should_be_a_minor_release(self) -> None:
        self.assertEqual(self.increment, "minor")


class TheIncrementFunctionWhenABreakingChangeComesBeforeVersionOne(unittest.TestCase):
    def setUp(self) -> None:
        self.increment = release.increment(parse_changes("fix: a", "feat: b", "refactor!: c"), (0, 2, 3))

    def test_should_be_a_minor_release_since_a_0_x_version_promises_nothing(self) -> None:
        self.assertEqual(self.increment, "minor")


class TheIncrementFunctionWhenABreakingChangeComesFromVersionOneOn(unittest.TestCase):
    def setUp(self) -> None:
        self.increment = release.increment(parse_changes("fix: a", "refactor!: c"), (1, 2, 3))

    def test_should_be_a_major_release(self) -> None:
        self.assertEqual(self.increment, "major")


class TheIncrementFunctionWhenACommitDoesNotFollowConventionalCommits(unittest.TestCase):
    def setUp(self) -> None:
        self.increment = release.increment(parse_changes("Not conventional"), (1, 2, 3))

    def test_should_be_a_patch(self) -> None:
        self.assertEqual(self.increment, "patch")


class TheBumpFunctionWhenTheNextVersionFitsInVersion(unittest.TestCase):
    following_releases: ClassVar[Mapping[str, tuple[int, int, int]]] = types.MappingProxyType(
        {
            "patch": (0, 2, 4),
            "minor": (0, 3, 0),
            "major": (1, 0, 0),
        }
    )

    def setUp(self) -> None:
        self.releases = {level: release.bump((0, 2, 3), level) for level in self.following_releases}

    def test_should_raise_the_level_and_reset_the_levels_below(self) -> None:
        for level, following_release in self.following_releases.items():
            with self.subTest(level):
                self.assertEqual(self.releases[level], following_release)


class TheBumpFunctionWhenTheNextVersionIsPastWhatVersionAllows(unittest.TestCase):
    last_releases: ClassVar[Mapping[str, tuple[tuple[int, int, int], str]]] = types.MappingProxyType(
        {
            "a minor version of 100": ((0, 99, 3), "minor"),
            "a patch of 100": ((0, 2, 99), "patch"),
            "a major version of 1000": ((999, 0, 0), "major"),
        }
    )

    def setUp(self) -> None:
        self.bumping_acts = {
            row: functools.partial(release.bump, last, level) for row, (last, level) in self.last_releases.items()
        }

    def test_should_refuse_it_asking_for_another_increment(self) -> None:
        for row in self.last_releases:
            with self.subTest(row):
                self.assertRaisesRegex(
                    release.ReleaseError,
                    "is past what VERSION allows .*choose another increment",
                    self.bumping_acts[row],
                )


class TheNotesFunctionWhenTheChangesHoldFeaturesFixesAndABreakingChange(unittest.TestCase):
    def setUp(self) -> None:
        changes = parse_changes(*SUBJECTS_OF_EVERY_KIND)
        self.notes = release.notes(changes)

    def test_should_draft_them_in_the_sections_of_keep_a_changelog_each_named_by_its_scope(self) -> None:
        self.assertEqual(
            self.notes,
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


class TheLeftOutFunctionWhenTheChangesHoldFeaturesFixesAndABreakingChange(unittest.TestCase):
    def setUp(self) -> None:
        changes = parse_changes(*SUBJECTS_OF_EVERY_KIND)
        self.left_out = release.left_out(changes)

    def test_should_list_the_other_changes_and_those_still_to_fold(self) -> None:
        self.assertEqual(
            self.left_out,
            [
                "- `0123456789ab` build: a script",
                "- `0123456789ab` Odd one",
                "- `0123456789ab` fixup! feat(server): a route",
            ],
        )


class TheSummaryFunctionWhenTheChangesHoldFeaturesFixesAndABreakingChange(unittest.TestCase):
    def setUp(self) -> None:
        changes = parse_changes(*SUBJECTS_OF_EVERY_KIND)
        self.summary = release.summary(changes)

    def test_should_count_each_kind_of_change(self) -> None:
        self.assertEqual(self.summary, "1 breaking change, 2 features, 1 fix, 3 other changes")


class TheNotesFunctionWhenNoChangeIsNotable(unittest.TestCase):
    def setUp(self) -> None:
        changes = parse_changes(*SUBJECTS_WITHOUT_NOTES)
        self.notes = release.notes(changes)

    def test_should_list_the_changes_under_changed_so_that_the_release_has_notes(self) -> None:
        self.assertEqual(self.notes, "### Changed\n\n- Explain the setup\n- Scripts: pin a tool\n")


class TheLeftOutFunctionWhenNoChangeIsNotable(unittest.TestCase):
    def setUp(self) -> None:
        changes = parse_changes(*SUBJECTS_WITHOUT_NOTES)
        self.left_out = release.left_out(changes)

    def test_should_list_only_the_changes_still_to_fold(self) -> None:
        self.assertEqual(self.left_out, ["- `0123456789ab` fixup! docs: explain the setup"])


class TheAddReleaseFunctionWhenTheChangelogIsReady(unittest.TestCase):
    def setUp(self) -> None:
        self.changelog = release.add_release(CHANGELOG, "0.3.0", "0.2.3", "2026-10-20", "### Added\n\n- App: updates\n")

    def test_should_add_the_section_after_unreleased_and_link_it_to_the_comparison_with_the_last_release(
        self,
    ) -> None:
        self.assertEqual(
            self.changelog,
            CHANGELOG.replace(
                "## [Unreleased]\n",
                "\n".join(
                    ["## [Unreleased]", "", "## [0.3.0] - 2026-10-20", "", "### Added", "", "- App: updates", ""]
                ),
            ).replace(
                "[unreleased]: https://github.com/example/project/compare/v0.2.3...HEAD\n",
                "[unreleased]: https://github.com/example/project/compare/v0.3.0...HEAD\n"
                "[0.3.0]: https://github.com/example/project/compare/v0.2.3...v0.3.0\n",
            ),
        )


class TheAddReleaseFunctionWhenTheChangelogCannotTakeTheRelease(unittest.TestCase):
    changelogs: ClassVar[Mapping[str, tuple[str, str]]] = types.MappingProxyType(
        {
            "no [Unreleased]": (CHANGELOG.replace("## [Unreleased]\n", ""), "no '## [Unreleased]' heading"),
            "entries under [Unreleased]": (
                CHANGELOG.replace("## [Unreleased]\n", "## [Unreleased]\n\n- Early\n"),
                "entries under [Unreleased]",
            ),
            "no link": (CHANGELOG.replace("[unreleased]: ", "[later]: "), "no '[unreleased]:"),
            "a link from another release": (
                CHANGELOG.replace("v0.2.3...HEAD", "v0.2.2...HEAD"),
                "compares from v0.2.2, not from the last release v0.2.3",
            ),
            "the release is there": (CHANGELOG.replace("## [0.2.3]", "## [0.3.0]"), "already has a section [0.3.0]"),
        }
    )

    def setUp(self) -> None:
        self.adding_acts = {
            row: functools.partial(
                release.add_release, changelog, "0.3.0", "0.2.3", "2026-10-20", "### Added\n\n- App: updates\n"
            )
            for row, (changelog, _) in self.changelogs.items()
        }

    def test_should_refuse_it_saying_why(self) -> None:
        for row, (_, reason) in self.changelogs.items():
            with self.subTest(row):
                self.assertRaisesRegex(release.ReleaseError, re.escape(reason), self.adding_acts[row])


class TheCompleteReleaseFunctionWhenTheSectionWasEditedByHand(unittest.TestCase):
    def setUp(self) -> None:
        changelog = release.add_release(CHANGELOG, "0.3.0", "0.2.3", "2026-10-20", SECTION_EDITED_IN_ITS_PULL_REQUEST)
        self.changelog = release.complete_release(
            changelog,
            "0.3.0",
            "### Added\n\n- Server: a route\n\n### Changed\n\n- Scripts: a check\n\n### Fixed\n\n- Server: a leak\n",
        )

    def test_should_add_each_entry_at_the_end_of_its_subsection_and_keep_the_entries_edited_by_hand(self) -> None:
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
            self.changelog,
        )


class TheCompleteReleaseFunctionWhenASubsectionTheSectionLacksComesAfterItsOthers(unittest.TestCase):
    def setUp(self) -> None:
        changelog = release.add_release(CHANGELOG, "0.3.0", "0.2.3", "2026-10-20", SECTION_EDITED_IN_ITS_PULL_REQUEST)
        self.changelog = release.complete_release(changelog, "0.3.0", "### Security\n\n- Server: a check\n")

    def test_should_add_it_at_the_end_of_the_section(self) -> None:
        self.assertIn("- App: a crash\n\n### Security\n\n- Server: a check\n\n## [0.2.3]", self.changelog)


class TheCompleteReleaseFunctionWhenASubsectionTheSectionLacksComesBeforeOneWrittenByHand(unittest.TestCase):
    def setUp(self) -> None:
        changelog = release.add_release(CHANGELOG, "0.3.0", "0.2.3", "2026-10-20", SECTION_EDITED_IN_ITS_PULL_REQUEST)
        edited = changelog.replace("### Fixed\n", "### Removed\n\n- Server: the old route\n\n### Fixed\n")
        self.changelog = release.complete_release(edited, "0.3.0", "### Changed\n\n- **Breaking:** Server: a format\n")

    def test_should_add_it_in_the_order_of_keep_a_changelog(self) -> None:
        self.assertIn(
            "- App: updates, edited by hand\n\n### Changed\n\n- **Breaking:** Server: a format\n\n### Removed\n",
            self.changelog,
        )


class TheCompleteReleaseFunctionWhenTheSectionIsTheLastOne(unittest.TestCase):
    def setUp(self) -> None:
        self.changelog = release.complete_release(CHANGELOG, "0.2.3", "### Fixed\n\n- OCR: a fix\n")

    def test_should_add_the_entries_right_before_the_links(self) -> None:
        self.assertIn("- Scan books\n\n### Fixed\n\n- OCR: a fix\n\n[unreleased]:", self.changelog)


class TheCompleteReleaseFunctionWhenTheChangelogHasNoSectionForTheRelease(unittest.TestCase):
    def setUp(self) -> None:
        self.complete = functools.partial(release.complete_release, CHANGELOG, "0.4.0", "### Fixed\n\n- OCR: a fix\n")

    def test_should_refuse_it_naming_the_missing_section(self) -> None:
        self.assertRaisesRegex(release.ReleaseError, re.escape("no section ## [0.4.0]"), self.complete)


class TheCompleteReleaseFunctionWhenAnEntryComesBeforeAnySubsection(unittest.TestCase):
    def setUp(self) -> None:
        self.complete = functools.partial(
            release.complete_release, CHANGELOG, "0.2.3", "- OCR: a fix\n\n### Fixed\n\n- Server: a leak\n"
        )

    def test_should_refuse_it_naming_the_entry(self) -> None:
        self.assertRaisesRegex(
            release.ReleaseError, re.escape("comes before any subsection: - OCR: a fix"), self.complete
        )


class TheReleaseBaseFunctionWhenTheMessageEndsWithTheTrailer(unittest.TestCase):
    def setUp(self) -> None:
        self.base = release.release_base(f"chore(release): 0.3.0\n\nWhy.\n\nRelease-Base: {COMMIT}\n")

    def test_should_read_the_commit_of_the_trailer(self) -> None:
        self.assertEqual(self.base, COMMIT)


class TheReleaseBaseFunctionWhenTheTrailerHoldsNoFullCommit(unittest.TestCase):
    def setUp(self) -> None:
        self.base = release.release_base("chore(release): 0.3.0\n\nRelease-Base: 0123\n")

    def test_should_find_none(self) -> None:
        self.assertIsNone(self.base)


class TheReleaseBaseFunctionWhenTheTrailerDoesNotStartItsLine(unittest.TestCase):
    def setUp(self) -> None:
        self.base = release.release_base(f"chore(release): 0.3.0\n\nThe Release-Base: {COMMIT}\n")

    def test_should_find_none(self) -> None:
        self.assertIsNone(self.base)


def make_repository_with_a_feature(test_case: type[unittest.TestCase]) -> Path:
    repository = make_repository(test_case)
    commit_nothing(repository, "fix(android): a crash")
    commit_nothing(repository, "feat(android): scan from the card")
    commit_nothing(repository, "docs: explain the card")
    return repository


class TheMainFunctionWhenAFeatureFollowsTheLastRelease(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]
    today: ClassVar[str]
    status: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository_with_a_feature(cls)
        cls.release_run = run_release(repository)
        cls.today = read_today()
        cls.status = run_git(repository, "status", "--porcelain")

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.release_run.returncode, 0, self.release_run.stderr)

    def test_should_say_the_last_release_the_commits_since_and_the_next_release_then_its_heading(self) -> None:
        self.assertEqual(
            self.release_run.stdout.splitlines()[:5],
            [
                "Last release: 0.2.3 (v0.2.3)",
                "Commits since: 3 (1 feature, 1 fix, 1 other change)",
                "Next release: 0.3.0, a minor release (new features)",
                "",
                f"## [0.3.0] - {self.today}",
            ],
        )

    def test_should_draft_the_feature_and_the_fix(self) -> None:
        self.assertIn(
            "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- App: a crash\n", self.release_run.stdout
        )

    def test_should_list_last_the_commits_left_out_of_the_changelog(self) -> None:
        self.assertRegex(
            self.release_run.stdout, r"Not in the changelog .*:\n- `[0-9a-f]{12}` docs: explain the card\n$"
        )

    def test_should_change_nothing_in_the_checkout(self) -> None:
        self.assertEqual(self.status, "")


class TheMainFunctionWhenAFeatureFollowsTheLastReleaseWhenAskedForTheVersionOnly(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]
    status: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository_with_a_feature(cls)
        cls.release_run = run_release(repository, "--version-only")
        cls.status = run_git(repository, "status", "--porcelain")

    def test_should_print_the_next_version_alone(self) -> None:
        self.assertEqual(self.release_run.stdout, "0.3.0\n")

    def test_should_change_nothing_in_the_checkout(self) -> None:
        self.assertEqual(self.status, "")


class TheMainFunctionWhenAFeatureFollowsTheLastReleaseWhenAskedForTheNotesOnly(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]
    status: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository_with_a_feature(cls)
        cls.release_run = run_release(repository, "--notes-only")
        cls.status = run_git(repository, "status", "--porcelain")

    def test_should_print_the_notes_without_their_heading(self) -> None:
        self.assertTrue(self.release_run.stdout.startswith("### Added\n"), self.release_run.stdout)

    def test_should_change_nothing_in_the_checkout(self) -> None:
        self.assertEqual(self.status, "")


class TheMainFunctionWhenAFeatureFollowsTheLastReleaseWhenAskedForAMajorRelease(unittest.TestCase):
    version_run: ClassVar[subprocess.CompletedProcess[str]]
    release_run: ClassVar[subprocess.CompletedProcess[str]]
    status: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository_with_a_feature(cls)
        cls.version_run = run_release(repository, "--bump", "major", "--version-only")
        cls.release_run = run_release(repository, "--bump", "major")
        cls.status = run_git(repository, "status", "--porcelain")

    def test_should_release_the_next_major_version(self) -> None:
        self.assertEqual(self.version_run.stdout, "1.0.0\n")

    def test_should_say_the_increment_was_chosen_over_the_one_the_commits_give(self) -> None:
        self.assertIn("a major release (--bump major; the commits give a minor release)", self.release_run.stdout)

    def test_should_change_nothing_in_the_checkout(self) -> None:
        self.assertEqual(self.status, "")


class TheMainFunctionWhenAFeatureFollowsTheLastReleaseWhenGivenAnEarlierRef(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]
    status: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository_with_a_feature(cls)
        cls.release_run = run_release(repository, "--ref", "HEAD~2")
        cls.status = run_git(repository, "status", "--porcelain")

    def test_should_release_the_commits_up_to_that_ref(self) -> None:
        self.assertIn("a patch release", self.release_run.stdout)

    def test_should_change_nothing_in_the_checkout(self) -> None:
        self.assertEqual(self.status, "")


class TheMainFunctionWhenABreakingChangeComesBeforeVersionOne(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "refactor(server)!: move the routes")
        cls.release_run = run_release(repository)

    def test_should_release_a_minor_version_saying_why(self) -> None:
        self.assertIn("Next release: 0.3.0, a minor release (breaking changes, before 1.0)", self.release_run.stdout)

    def test_should_draft_the_change_as_breaking_under_changed(self) -> None:
        self.assertIn("### Changed\n\n- **Breaking:** Server: move the routes\n", self.release_run.stdout)


class TheMainFunctionWhenACommitDoesNotFollowConventionalCommits(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "Update things")
        cls.release_run = run_release(repository, "--version-only")

    def test_should_release_a_patch(self) -> None:
        self.assertEqual(self.release_run.stdout, "0.2.4\n")

    def test_should_warn_that_it_does_not_follow_conventional_commits(self) -> None:
        self.assertIn("not a Conventional Commit, released as a patch", self.release_run.stderr)

    def test_should_name_it(self) -> None:
        self.assertIn("Update things", self.release_run.stderr)


class TheMainFunctionWhenNothingFollowsTheLastRelease(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.release_run = run_release(make_repository(cls))

    def test_should_refuse_since_there_is_nothing_to_release(self) -> None:
        self.assertEqual(self.release_run.returncode, 1)
        self.assertIn("nothing to release", self.release_run.stderr)


class TheMainFunctionWhenCommitsAreStillToFold(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        commit_nothing(repository, "fixup! feat: a")
        cls.release_run = run_release(repository)

    def test_should_refuse_until_they_are_folded(self) -> None:
        self.assertEqual(self.release_run.returncode, 1)
        self.assertIn("commits still to fold", self.release_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.release_run.stdout, "")


class TheMainFunctionWhenCommitsStillToFoldReachedMainForGood(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        commit_nothing(repository, "fixup! feat: a")
        cls.release_run = run_release(repository, "--allow-unfolded")

    def test_should_release_them_as_they_are_since_main_s_history_is_never_rewritten(self) -> None:
        self.assertEqual(self.release_run.returncode, 0, self.release_run.stderr)

    def test_should_warn_that_they_are_released_unfolded(self) -> None:
        self.assertIn("released as it is, not folded", self.release_run.stderr)

    def test_should_not_warn_that_they_do_not_follow_conventional_commits(self) -> None:
        self.assertNotIn("not a Conventional Commit", self.release_run.stderr)

    def test_should_list_them_as_left_out_of_the_changelog(self) -> None:
        self.assertRegex(self.release_run.stdout, r"\n- `[0-9a-f]{12}` fixup! feat: a\n")

    def test_should_release_the_version_the_other_commits_give(self) -> None:
        self.assertIn("Next release: 0.3.0", self.release_run.stdout)


class TheMainFunctionWhenVersionIsSetWithoutAReleaseCommit(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        (repository / "VERSION").write_text("0.3.0\n")
        commit_everything(repository, "build: set VERSION by hand")
        cls.release_run = run_release(repository)

    def test_should_refuse_saying_there_is_neither_its_tag_nor_its_release_commit(self) -> None:
        self.assertEqual(self.release_run.returncode, 1)
        self.assertIn("no tag v0.3.0 nor a release commit 'chore(release): 0.3.0'", self.release_run.stderr)


class TheMainFunctionWhenTheRefDoesNotExist(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.release_run = run_release(make_repository(cls), "--ref", "nonexistent")

    def test_should_refuse_with_an_error_that_names_it(self) -> None:
        self.assertEqual(self.release_run.returncode, 1)
        self.assertIn("error:", self.release_run.stderr)
        self.assertIn("nonexistent", self.release_run.stderr)


class TheMainFunctionWhenAskedToCommitTheRelease(unittest.TestCase):
    commit_run: ClassVar[subprocess.CompletedProcess[str]]
    base: ClassVar[str]
    today: ClassVar[str]
    message: ClassVar[str]
    parent: ClassVar[str]
    committed_files: ClassVar[list[str]]
    status: ClassVar[str]
    version: ClassVar[str]
    changelog: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "fix(android): a crash")
        cls.base = commit_nothing(repository, "feat(android): scan from the card")
        run_git(repository, "switch", "--quiet", "-c", "release/v0.3.0")
        cls.commit_run = run_release_commit(repository)
        cls.today = read_today()
        cls.message = run_git(repository, "log", "-1", "--format=%B")
        cls.parent = run_git(repository, "rev-parse", "HEAD~1").strip()
        cls.committed_files = run_git(repository, "show", "--name-only", "--format=", "HEAD").split()
        cls.status = run_git(repository, "status", "--porcelain")
        cls.version = (repository / "VERSION").read_text()
        cls.changelog = (repository / "CHANGELOG.md").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.commit_run.returncode, 0, self.commit_run.stderr)

    def test_should_say_in_its_message_why_and_the_commit_its_notes_were_written_on(self) -> None:
        self.assertEqual(
            self.message.rstrip("\n").split("\n\n"),
            [
                "chore(release): 0.3.0",
                "Release 0.3.0 (a minor release): 1 feature, 1 fix since v0.2.3. Its notes are its section of "
                "CHANGELOG.md.",
                f"Release-Base: {self.base}",
            ],
        )

    def test_should_commit_on_the_commit_its_notes_were_written_on(self) -> None:
        self.assertEqual(self.parent, self.base)

    def test_should_commit_the_changelog_and_version_alone(self) -> None:
        self.assertEqual(self.committed_files, ["CHANGELOG.md", "VERSION"])

    def test_should_leave_nothing_uncommitted(self) -> None:
        self.assertEqual(self.status, "")

    def test_should_write_the_next_version_to_version(self) -> None:
        self.assertEqual(self.version, "0.3.0\n")

    def test_should_add_the_section_of_the_release_after_unreleased(self) -> None:
        self.assertIn(
            f"## [Unreleased]\n\n## [0.3.0] - {self.today}\n\n### Added\n\n- App: scan from the card\n\n"
            "### Fixed\n\n- App: a crash\n\n## [0.2.3] - 2026-10-15\n",
            self.changelog,
        )

    def test_should_link_the_section_to_the_comparison_with_the_last_release(self) -> None:
        self.assertIn(
            "[unreleased]: https://github.com/example/project/compare/v0.3.0...HEAD\n"
            "[0.3.0]: https://github.com/example/project/compare/v0.2.3...v0.3.0\n",
            self.changelog,
        )

    def test_should_print_the_description_of_its_pull_request_what_merging_it_does_then_its_notes(self) -> None:
        self.assertEqual(
            self.commit_run.stdout,
            "\n".join(
                [
                    "Merging this pull request publishes ScanMyLib 0.3.0: `.github/workflows/release.yml` tags "
                    "`v0.3.0` and creates the GitHub release with the notes below. Merge nothing else before it.",
                    "",
                    f"## [0.3.0](https://github.com/example/project/compare/v0.2.3...v0.3.0) - {self.today}",
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


def make_repository_released_at_0_2_99(test_case: type[unittest.TestCase]) -> Path:
    repository = make_repository(test_case)
    (repository / "VERSION").write_text("0.2.99\n")
    commit_everything(repository, "chore(release): 0.2.99")
    run_git(repository, "tag", "--annotate", "v0.2.99", "--message", "ScanMyLib 0.2.99")
    (repository / "CHANGELOG.md").write_text(CHANGELOG.replace("v0.2.3...HEAD", "v0.2.99...HEAD"))
    commit_everything(repository, "fix: a crash")
    run_git(repository, "switch", "--quiet", "-c", "release")
    return repository


class TheMainFunctionWhenAskedToCommitAPatchPastWhatVersionAllows(unittest.TestCase):
    commit_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.commit_run = run_release_commit(make_repository_released_at_0_2_99(cls))

    def test_should_refuse_it(self) -> None:
        self.assertEqual(self.commit_run.returncode, 1)
        self.assertIn("0.2.100 is past what VERSION allows", self.commit_run.stderr)


class TheMainFunctionWhenAskedToCommitAnIncrementChosenByHand(unittest.TestCase):
    commit_run: ClassVar[subprocess.CompletedProcess[str]]
    message: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository_released_at_0_2_99(cls)
        cls.commit_run = run_release_commit(repository, "--bump", "minor")
        cls.message = run_git(repository, "log", "-1", "--format=%B")

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.commit_run.returncode, 0, self.commit_run.stderr)

    def test_should_say_in_its_message_that_the_increment_was_chosen_by_hand(self) -> None:
        self.assertIn("Release 0.3.0 (a minor release chosen by hand): 1 fix since v0.2.99.", self.message)


class TheMainFunctionWhenAskedToCommitOnABranchThatHoldsAnotherCommit(unittest.TestCase):
    commit_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        run_git(repository, "switch", "--quiet", "-c", "release")
        commit_nothing(repository, "docs: a note")
        cls.commit_run = run_release_commit(repository)

    def test_should_refuse_since_rebase_and_merge_would_rewrite_the_commit_its_notes_are_written_on(self) -> None:
        self.assertEqual(self.commit_run.returncode, 1)
        self.assertIn("is not in origin/main", self.commit_run.stderr)


class TheMainFunctionWhenAskedToCommitOnMain(unittest.TestCase):
    commit_run: ClassVar[subprocess.CompletedProcess[str]]
    subject: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        cls.commit_run = run_release_commit(repository)
        cls.subject = run_git(repository, "log", "-1", "--format=%s")

    def test_should_refuse_asking_for_a_branch_of_its_own(self) -> None:
        self.assertEqual(self.commit_run.returncode, 1)
        self.assertIn("prepare the release on its own branch, not on main", self.commit_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.commit_run.stdout, "")

    def test_should_commit_nothing(self) -> None:
        self.assertEqual(self.subject, "feat: a\n")


class TheMainFunctionWhenAskedToCommitAnotherRefThanHead(unittest.TestCase):
    commit_run: ClassVar[subprocess.CompletedProcess[str]]
    subject: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        run_git(repository, "switch", "--quiet", "-c", "release")
        cls.commit_run = run_release_commit(repository, "--ref", "HEAD~1")
        cls.subject = run_git(repository, "log", "-1", "--format=%s")

    def test_should_refuse_since_it_prepares_head(self) -> None:
        self.assertEqual(self.commit_run.returncode, 1)
        self.assertIn("--commit prepares HEAD", self.commit_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.commit_run.stdout, "")

    def test_should_commit_nothing(self) -> None:
        self.assertEqual(self.subject, "feat: a\n")


class TheMainFunctionWhenAskedToCommitWithChangesInTheCheckout(unittest.TestCase):
    commit_run: ClassVar[subprocess.CompletedProcess[str]]
    subject: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        run_git(repository, "switch", "--quiet", "-c", "release")
        (repository / "VERSION").write_text("9.9.9\n")
        cls.commit_run = run_release_commit(repository)
        cls.subject = run_git(repository, "log", "-1", "--format=%s")

    def test_should_refuse_asking_to_commit_or_stash_them(self) -> None:
        self.assertEqual(self.commit_run.returncode, 1)
        self.assertIn("commit or stash", self.commit_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.commit_run.stdout, "")

    def test_should_commit_nothing(self) -> None:
        self.assertEqual(self.subject, "feat: a\n")


class _TheMainFunctionWhenAskedForTheDescriptionOfNotesEditedAfterTheReleaseCommit(unittest.TestCase):
    repository: ClassVar[Path]
    first_description: ClassVar[str]
    description_run: ClassVar[subprocess.CompletedProcess[str]]
    head_description_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = make_repository(cls)
        commit_nothing(cls.repository, "feat(android): scan from the card")
        run_git(cls.repository, "switch", "--quiet", "-c", "release/v0.3.0")
        commit_run = run_release_commit(cls.repository)
        commit_run.check_returncode()
        cls.first_description = commit_run.stdout
        replace_in_the_changelog(cls.repository, "scan from the card", "scan straight from the card")
        run_git(cls.repository, "commit", "--quiet", "--all", "--amend", "--no-edit")
        cls.description_run = run_release(cls.repository, "--description")
        cls.head_description_run = run_release(cls.repository, "--description", "--ref", "HEAD")


class TheMainFunctionWhenAskedForTheDescriptionOfNotesEditedAfterTheReleaseCommit(
    _TheMainFunctionWhenAskedForTheDescriptionOfNotesEditedAfterTheReleaseCommit
):
    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.description_run.returncode, 0, self.description_run.stderr)

    def test_should_describe_the_release_from_its_edited_notes(self) -> None:
        self.assertEqual(
            self.description_run.stdout,
            self.first_description.replace("scan from the card", "scan straight from the card"),
        )

    def test_should_describe_head_unless_given_another_ref(self) -> None:
        self.assertEqual(self.description_run.stdout, self.head_description_run.stdout)


class TheMainFunctionWhenAskedForTheDescriptionOfNotesEditedAfterTheReleaseCommitWhenTheEditRemovesEveryEntry(
    _TheMainFunctionWhenAskedForTheDescriptionOfNotesEditedAfterTheReleaseCommit
):
    emptied_description_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        replace_in_the_changelog(cls.repository, "- App: scan straight from the card\n", "")
        run_git(cls.repository, "commit", "--quiet", "--all", "--amend", "--no-edit")
        cls.emptied_description_run = run_release(cls.repository, "--description")

    def test_should_refuse_since_the_release_would_publish_nothing(self) -> None:
        self.assertEqual(self.emptied_description_run.returncode, 1)
        self.assertIn("the section [0.3.0] of CHANGELOG.md has no entry", self.emptied_description_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.emptied_description_run.stdout, "")


class TheMainFunctionWhenAskedForTheDescriptionOfAReleasedVersion(unittest.TestCase):
    description_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.description_run = run_release(make_repository(cls), "--description", "--ref", "v0.2.3")

    def test_should_refuse_since_it_is_released_already(self) -> None:
        self.assertEqual(self.description_run.returncode, 1)
        self.assertIn("0.2.3 is released already", self.description_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.description_run.stdout, "")


class TheMainFunctionWhenAskedForTheDescriptionOfARefThatDoesNotExist(unittest.TestCase):
    description_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.description_run = run_release(make_repository(cls), "--description", "--ref", "nonexistent")

    def test_should_refuse_with_an_error_that_names_it(self) -> None:
        self.assertEqual(self.description_run.returncode, 1)
        self.assertIn("error:", self.description_run.stderr)
        self.assertIn("nonexistent", self.description_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.description_run.stdout, "")


class _TheMainFunctionWhenAFixIsMergedBeforeTheRelease(unittest.TestCase):
    repository: ClassVar[Path]
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = make_repository(cls)
        commit_nothing(cls.repository, "feat(android): scan from the card")
        prepare_release(cls.repository)
        commit_nothing(cls.repository, "fix(server): a leak")
        merge_release(cls.repository, "release/v0.3.0")
        cls.release_run = run_release(cls.repository)


class TheMainFunctionWhenAFixIsMergedBeforeTheRelease(_TheMainFunctionWhenAFixIsMergedBeforeTheRelease):
    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.release_run.returncode, 0, self.release_run.stderr)

    def test_should_say_the_release_is_to_complete_and_count_the_commits_its_notes_miss(self) -> None:
        self.assertEqual(
            self.release_run.stdout.splitlines()[:2],
            [
                "Release to complete: 0.3.0 (VERSION, not tagged: its release commit could not be published)",
                "Commits its notes miss: 1 (1 fix)",
            ],
        )

    def test_should_draft_the_fix_its_notes_miss(self) -> None:
        self.assertIn("### Fixed\n\n- Server: a leak\n", self.release_run.stdout)


class TheMainFunctionWhenAFixIsMergedBeforeTheReleaseWhenAskedForAnotherIncrement(
    _TheMainFunctionWhenAFixIsMergedBeforeTheRelease
):
    bump_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.bump_run = run_release(cls.repository, "--bump", "patch")

    def test_should_refuse_since_a_completed_release_keeps_its_version(self) -> None:
        self.assertEqual(self.bump_run.returncode, 1)
        self.assertIn("no --bump", self.bump_run.stderr)


class _TheMainFunctionWhenAFixIsMergedBeforeTheReleaseWhenItsCompletionIsCommitted(
    _TheMainFunctionWhenAFixIsMergedBeforeTheRelease
):
    base: ClassVar[str]
    completion_run: ClassVar[subprocess.CompletedProcess[str]]
    message_fields: ClassVar[list[str]]
    committed_files: ClassVar[list[str]]
    changelog: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.base = read_head(cls.repository)
        run_git(cls.repository, "switch", "--quiet", "-c", "release/v0.3.0-complete")
        cls.completion_run = run_release_commit(cls.repository)
        cls.message_fields = run_git(
            cls.repository, "log", "-1", "--format=%s%n%(trailers:key=Release-Base,valueonly)"
        ).split()
        cls.committed_files = run_git(cls.repository, "show", "--name-only", "--format=", "HEAD").split()
        cls.changelog = (cls.repository / "CHANGELOG.md").read_text()


class TheMainFunctionWhenAFixIsMergedBeforeTheReleaseWhenItsCompletionIsCommitted(
    _TheMainFunctionWhenAFixIsMergedBeforeTheReleaseWhenItsCompletionIsCommitted
):
    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.completion_run.returncode, 0, self.completion_run.stderr)

    def test_should_print_the_description_of_its_pull_request(self) -> None:
        self.assertTrue(
            self.completion_run.stdout.startswith("Merging this pull request publishes ScanMyLib 0.3.0"),
            self.completion_run.stdout,
        )

    def test_should_print_every_note_of_the_release(self) -> None:
        self.assertIn(
            "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n", self.completion_run.stdout
        )

    def test_should_commit_a_release_commit_written_on_main(self) -> None:
        self.assertEqual(self.message_fields, ["chore(release):", "0.3.0", self.base])

    def test_should_commit_the_changelog_alone_since_the_release_keeps_its_version(self) -> None:
        self.assertEqual(self.committed_files, ["CHANGELOG.md"])

    def test_should_add_the_fix_to_the_section_of_the_release(self) -> None:
        self.assertIn(
            "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n\n## [0.2.3]", self.changelog
        )


class TheMainFunctionWhenAFixIsMergedBeforeTheReleaseWhenItsCompletionIsCommittedWhenItIsMerged(
    _TheMainFunctionWhenAFixIsMergedBeforeTheReleaseWhenItsCompletionIsCommitted
):
    completed_release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        merge_release(cls.repository, "release/v0.3.0-complete")
        cls.completed_release_run = run_release(cls.repository)

    def test_should_refuse_since_the_release_can_be_published_as_it_is_and_waits_for_its_workflow(self) -> None:
        self.assertEqual(self.completed_release_run.returncode, 1)
        self.assertIn("can be published as it is", self.completed_release_run.stderr)


class TheMainFunctionWhenAFixAndOtherChangesAreMergedBeforeAReleaseWhoseNotesWereEdited(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat(android): scan from the card")
        prepare_release(repository, "scan from the card", "scan straight from the card")
        commit_nothing(repository, "docs: explain the card")
        commit_nothing(repository, "fix(server): a leak")
        merge_release(repository, "release/v0.3.0")
        cls.release_run = run_release(repository)

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.release_run.returncode, 0, self.release_run.stderr)

    def test_should_count_the_commits_its_notes_miss_without_the_edits_of_its_notes(self) -> None:
        self.assertIn("Commits its notes miss: 2 (1 fix, 1 other change)", self.release_run.stdout)

    def test_should_draft_the_fix(self) -> None:
        self.assertIn("### Fixed\n\n- Server: a leak\n", self.release_run.stdout)

    def test_should_never_mention_the_edits_of_its_notes(self) -> None:
        self.assertNotIn("Update CHANGELOG.md", self.release_run.stdout + self.release_run.stderr)

    def test_should_list_the_other_change_as_left_out_of_the_changelog(self) -> None:
        self.assertRegex(
            self.release_run.stdout, r"Not in the changelog .*:\n- `[0-9a-f]{12}` docs: explain the card\n$"
        )


class TheMainFunctionWhenOnlyChangesItsNotesNeedNotListAreMergedBeforeTheRelease(unittest.TestCase):
    release_commit: ClassVar[str]
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat(android): scan from the card")
        prepare_release(repository)
        commit_nothing(repository, "test(server): cover the route")
        append_a_blank_line_to_the_changelog(repository)
        commit_everything(repository, "fix: the notes of 0.2.3")
        merge_release(repository, "release/v0.3.0")
        cls.release_commit = read_head(repository)
        commit_nothing(repository, "feat(server): a later feature")
        cls.release_run = run_release(repository)

    def test_should_refuse_since_the_release_can_be_published_as_it_is_on_its_release_commit(self) -> None:
        self.assertEqual(self.release_run.returncode, 1)
        self.assertIn(
            f"the release 0.3.0 can be published as it is, on {self.release_commit[:12]}", self.release_run.stderr
        )

    def test_should_say_how_to_fetch_its_tag_in_case_it_is_published_already(self) -> None:
        self.assertIn("git fetch --tags origin", self.release_run.stderr)


class _TheMainFunctionWhenTheSectionOfAMergedReleaseHasNoEntry(unittest.TestCase):
    repository: ClassVar[Path]
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = make_repository(cls)
        commit_nothing(cls.repository, "feat(android): scan from the card")
        commit_nothing(cls.repository, "fix(server): a crash")
        prepare_release(cls.repository, "- App: scan from the card\n\n### Fixed\n\n- Server: a crash\n", "")
        merge_release(cls.repository, "release/v0.3.0")
        commit_nothing(cls.repository, "docs: explain the card")
        commit_nothing(cls.repository, "fix(web): a later fix")
        cls.release_run = run_release(cls.repository)


class TheMainFunctionWhenTheSectionOfAMergedReleaseHasNoEntry(_TheMainFunctionWhenTheSectionOfAMergedReleaseHasNoEntry):
    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.release_run.returncode, 0, self.release_run.stderr)

    def test_should_count_the_commits_since_the_last_release(self) -> None:
        self.assertIn("Commits since v0.2.3: 4 (1 feature, 2 fixes, 1 other change)", self.release_run.stdout)

    def test_should_draft_the_section_again_from_those_commits(self) -> None:
        self.assertIn(
            "Its section of CHANGELOG.md, written again:\n\n### Added\n\n- App: scan from the card\n\n"
            "### Fixed\n\n- Server: a crash\n- Web UI: a later fix\n",
            self.release_run.stdout,
        )


class TheMainFunctionWhenTheSectionOfAMergedReleaseHasNoEntryWhenItsCompletionIsCommitted(
    _TheMainFunctionWhenTheSectionOfAMergedReleaseHasNoEntry
):
    completion_run: ClassVar[subprocess.CompletedProcess[str]]
    changelog: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        run_git(cls.repository, "switch", "--quiet", "-c", "release/v0.3.0-complete")
        cls.completion_run = run_release_commit(cls.repository)
        cls.changelog = (cls.repository / "CHANGELOG.md").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.completion_run.returncode, 0, self.completion_run.stderr)

    def test_should_print_the_notes_written_again(self) -> None:
        self.assertIn("### Fixed\n\n- Server: a crash\n- Web UI: a later fix\n", self.completion_run.stdout)

    def test_should_write_the_section_again_in_place(self) -> None:
        self.assertRegex(
            self.changelog,
            r"## \[0\.3\.0\] - \d{4}-\d\d-\d\d\n\n### Added\n\n- App: scan from the card\n\n"
            r"### Fixed\n\n- Server: a crash\n- Web UI: a later fix\n\n## \[0\.2\.3\]",
        )


class TheMainFunctionWhenTheCompletionOfAMergedReleaseThatLostItsSectionIsCommitted(unittest.TestCase):
    completion_run: ClassVar[subprocess.CompletedProcess[str]]
    changelog: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat(android): scan from the card")
        prepare_release(repository, "## [0.3.0] - ", "## 0.3.0 - ")
        merge_release(repository, "release/v0.3.0")
        commit_nothing(repository, "fix(server): a leak")
        run_git(repository, "switch", "--quiet", "-c", "release/v0.3.0-complete")
        cls.completion_run = run_release_commit(repository)
        cls.changelog = (repository / "CHANGELOG.md").read_text()

    def test_should_exit_with_zero(self) -> None:
        self.assertEqual(self.completion_run.returncode, 0, self.completion_run.stderr)

    def test_should_write_the_section_again_after_unreleased(self) -> None:
        self.assertRegex(
            self.changelog,
            r"## \[Unreleased\]\n\n## \[0\.3\.0\] - \d{4}-\d\d-\d\d\n\n### Added\n\n"
            r"- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n\n## 0\.3\.0 - ",
        )


class TheMainFunctionWhenTheReleaseIsMergedAlone(unittest.TestCase):
    release_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat(android): scan from the card")
        prepare_release(repository)
        merge_release(repository, "release/v0.3.0")
        cls.release_run = run_release(repository)

    def test_should_refuse_since_it_can_be_published_as_it_is(self) -> None:
        self.assertEqual(self.release_run.returncode, 1)
        self.assertIn("can be published as it is", self.release_run.stderr)

    def test_should_say_that_its_workflow_publishes_it(self) -> None:
        self.assertIn(".github/workflows/release.yml publishes it", self.release_run.stderr)


class _TheMainFunctionWhenAskedToPublishAMergedRelease(unittest.TestCase):
    repository: ClassVar[Path]
    release_commit: ClassVar[str]
    publication_run: ClassVar[subprocess.CompletedProcess[str]]
    notes: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = make_repository(cls)
        commit_nothing(cls.repository, "feat(android): scan from the card")
        commit_nothing(cls.repository, "fix(server): a leak")
        prepare_release(cls.repository)
        merge_release(cls.repository, "release/v0.3.0")
        cls.release_commit = read_head(cls.repository)
        cls.publication_run = run_to_publish(cls.repository)
        cls.notes = read_notes(cls.repository)


class TheMainFunctionWhenAskedToPublishAMergedRelease(_TheMainFunctionWhenAskedToPublishAMergedRelease):
    def test_should_publish_its_version_on_its_release_commit(self) -> None:
        self.assertEqual(
            (self.publication_run.returncode, self.publication_run.stdout.split()),
            (0, ["0.3.0", self.release_commit]),
            self.publication_run.stderr,
        )

    def test_should_write_its_notes(self) -> None:
        self.assertEqual(self.notes, "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n")


class _TheMainFunctionWhenAskedToPublishAMergedReleaseWhenItIsTagged(_TheMainFunctionWhenAskedToPublishAMergedRelease):
    tagged_publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        run_git(cls.repository, "tag", "--annotate", "v0.3.0", "--message", "ScanMyLib 0.3.0")
        cls.tagged_publication_run = run_to_publish(cls.repository)


class TheMainFunctionWhenAskedToPublishAMergedReleaseWhenItIsTagged(
    _TheMainFunctionWhenAskedToPublishAMergedReleaseWhenItIsTagged
):
    def test_should_still_publish_it_on_its_release_commit_so_that_a_failed_github_release_is_finished(self) -> None:
        self.assertEqual(
            (self.tagged_publication_run.returncode, self.tagged_publication_run.stdout.split()),
            (0, ["0.3.0", self.release_commit]),
            self.tagged_publication_run.stderr,
        )


class TheMainFunctionWhenAskedToPublishAMergedReleaseWhenItIsTaggedWhenALaterCommitEditsTheChangelog(
    _TheMainFunctionWhenAskedToPublishAMergedReleaseWhenItIsTagged
):
    later_publication_run: ClassVar[subprocess.CompletedProcess[str]]
    release_commit_publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        append_a_blank_line_to_the_changelog(cls.repository)
        commit_everything(cls.repository, "docs: fix the changelog")
        cls.later_publication_run = run_to_publish(cls.repository)
        cls.release_commit_publication_run = run_to_publish(cls.repository, cls.release_commit)

    def test_should_publish_nothing_from_the_later_commit(self) -> None:
        self.assertEqual(
            (self.later_publication_run.returncode, self.later_publication_run.stdout),
            (0, ""),
            self.later_publication_run.stderr,
        )

    def test_should_say_there_is_nothing_to_publish(self) -> None:
        self.assertIn("nothing to publish", self.later_publication_run.stderr)

    def test_should_still_publish_the_release_from_its_release_commit(self) -> None:
        self.assertEqual(
            (self.release_commit_publication_run.returncode, self.release_commit_publication_run.stdout.split()),
            (0, ["0.3.0", self.release_commit]),
            self.release_commit_publication_run.stderr,
        )


class _TheMainFunctionWhenAskedToPublishAReleaseMergedAfterAFix(unittest.TestCase):
    repository: ClassVar[Path]
    publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = make_repository(cls)
        commit_nothing(cls.repository, "feat(android): scan from the card")
        prepare_release(cls.repository)
        commit_nothing(cls.repository, "fix(server): a leak")
        merge_release(cls.repository, "release/v0.3.0")
        cls.publication_run = run_to_publish(cls.repository)


class TheMainFunctionWhenAskedToPublishAReleaseMergedAfterAFix(
    _TheMainFunctionWhenAskedToPublishAReleaseMergedAfterAFix
):
    def test_should_refuse_naming_the_fix_its_notes_miss_and_the_commit_they_were_written_on(self) -> None:
        self.assertEqual(self.publication_run.returncode, 1)
        self.assertRegex(
            self.publication_run.stderr,
            r"miss features, fixes or breaking changes merged after [0-9a-f]{12}, the "
            r"commit they were written on:\n  [0-9a-f]{12} fix\(server\): a leak\n",
        )

    def test_should_say_that_a_run_on_main_completes_it(self) -> None:
        self.assertIn("completes the release 0.3.0", self.publication_run.stderr)

    def test_should_print_nothing(self) -> None:
        self.assertEqual(self.publication_run.stdout, "")


class TheMainFunctionWhenAskedToPublishAReleaseMergedAfterAFixWhenItsCompletionIsMerged(
    _TheMainFunctionWhenAskedToPublishAReleaseMergedAfterAFix
):
    completion: ClassVar[str]
    completed_publication_run: ClassVar[subprocess.CompletedProcess[str]]
    notes: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        run_git(cls.repository, "switch", "--quiet", "-c", "release/v0.3.0-complete")
        run_release_commit(cls.repository).check_returncode()
        merge_release(cls.repository, "release/v0.3.0-complete")
        cls.completion = read_head(cls.repository)
        cls.completed_publication_run = run_to_publish(cls.repository)
        cls.notes = read_notes(cls.repository)

    def test_should_publish_it_on_its_completion(self) -> None:
        self.assertEqual(
            (self.completed_publication_run.returncode, self.completed_publication_run.stdout.split()),
            (0, ["0.3.0", self.completion]),
            self.completed_publication_run.stderr,
        )

    def test_should_write_every_note_of_the_release(self) -> None:
        self.assertEqual(self.notes, "### Added\n\n- App: scan from the card\n\n### Fixed\n\n- Server: a leak\n")


class _TheMainFunctionWhenAskedToPublishAReleaseWhoseNotesWereEditedInItsPullRequest(unittest.TestCase):
    repository: ClassVar[Path]
    last_edit: ClassVar[str]
    publication_run: ClassVar[subprocess.CompletedProcess[str]]
    notes: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = make_repository(cls)
        commit_nothing(cls.repository, "feat(android): scan from the card")
        prepare_release(cls.repository, "scan from the card", "scan straight from the card")
        commit_nothing(cls.repository, "docs: explain the card")
        append_a_blank_line_to_the_changelog(cls.repository)
        commit_everything(cls.repository, "fix: the notes of 0.2.3")
        merge_release(cls.repository, "release/v0.3.0")
        cls.last_edit = read_head(cls.repository)
        cls.publication_run = run_to_publish(cls.repository)
        cls.notes = read_notes(cls.repository)


class TheMainFunctionWhenAskedToPublishAReleaseWhoseNotesWereEditedInItsPullRequest(
    _TheMainFunctionWhenAskedToPublishAReleaseWhoseNotesWereEditedInItsPullRequest
):
    def test_should_publish_it_on_the_last_edit_despite_the_commits_its_notes_need_not_list_merged_before_it(
        self,
    ) -> None:
        self.assertEqual(
            (self.publication_run.returncode, self.publication_run.stdout.split()),
            (0, ["0.3.0", self.last_edit]),
            self.publication_run.stderr,
        )

    def test_should_write_the_edited_notes(self) -> None:
        self.assertEqual(self.notes, "### Added\n\n- App: scan straight from the card\n")


class TheMainFunctionWhenAskedToPublishAReleaseWhoseNotesWereEditedInItsPullRequestWhenLaterCommitsFollow(
    _TheMainFunctionWhenAskedToPublishAReleaseWhoseNotesWereEditedInItsPullRequest
):
    later_publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        commit_nothing(cls.repository, "feat(server): a later feature")
        append_a_blank_line_to_the_changelog(cls.repository)
        commit_everything(cls.repository, "Update CHANGELOG.md")
        cls.later_publication_run = run_to_publish(cls.repository)

    def test_should_still_publish_it_on_its_last_edit_since_later_commits_belong_to_the_next_release(self) -> None:
        self.assertEqual(
            (self.later_publication_run.returncode, self.later_publication_run.stdout.split()),
            (0, ["0.3.0", self.last_edit]),
            self.later_publication_run.stderr,
        )


class TheMainFunctionWhenAskedToPublishAReleaseBranchWithCommitsAfterItsReleaseCommit(unittest.TestCase):
    release_commit: ClassVar[str]
    publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat(android): scan from the card")
        prepare_release(repository)
        run_git(repository, "switch", "--quiet", "release/v0.3.0")
        cls.release_commit = read_head(repository)
        commit_nothing(repository, "fix(server): a last-minute leak")
        run_git(repository, "switch", "--quiet", "-c", "side", "HEAD~2")
        commit_nothing(repository, "fix(server): another leak")
        run_git(repository, "switch", "--quiet", "release/v0.3.0")
        run_git(repository, "merge", "--quiet", "--no-ff", "--no-edit", "side")
        cls.publication_run = run_to_publish(repository)

    def test_should_publish_it_on_its_release_commit_since_later_commits_belong_to_the_next_release(self) -> None:
        self.assertEqual(
            (self.publication_run.returncode, self.publication_run.stdout.split()),
            (0, ["0.3.0", self.release_commit]),
            self.publication_run.stderr,
        )


class _TheMainFunctionWhenAskedToPublishAReleaseWhoseSectionHasNoEntry(unittest.TestCase):
    repository: ClassVar[Path]
    publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = make_repository(cls)
        commit_nothing(cls.repository, "feat(android): scan from the card")
        prepare_release(cls.repository, "### Added\n\n- App: scan from the card\n\n", "")
        merge_release(cls.repository, "release/v0.3.0")
        cls.publication_run = run_to_publish(cls.repository)


class TheMainFunctionWhenAskedToPublishAReleaseWhoseSectionHasNoEntry(
    _TheMainFunctionWhenAskedToPublishAReleaseWhoseSectionHasNoEntry
):
    def test_should_refuse_until_the_section_is_written(self) -> None:
        self.assertEqual(self.publication_run.returncode, 1)
        self.assertIn("the section [0.3.0] of CHANGELOG.md has no entry, or is missing", self.publication_run.stderr)


class TheMainFunctionWhenAskedToPublishAReleaseWhoseSectionHasNoEntryWhenAPullRequestWritesIt(
    _TheMainFunctionWhenAskedToPublishAReleaseWhoseSectionHasNoEntry
):
    writing_commit: ClassVar[str]
    written_publication_run: ClassVar[subprocess.CompletedProcess[str]]
    notes: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        replace_in_the_changelog(cls.repository, "\n## [0.2.3]", "### Added\n\n- App: scan from the card\n\n## [0.2.3]")
        commit_everything(cls.repository, "docs: write the notes of 0.3.0")
        cls.writing_commit = read_head(cls.repository)
        cls.written_publication_run = run_to_publish(cls.repository)
        cls.notes = read_notes(cls.repository)

    def test_should_publish_the_release_on_that_commit(self) -> None:
        self.assertEqual(
            (self.written_publication_run.returncode, self.written_publication_run.stdout.split()),
            (0, ["0.3.0", self.writing_commit]),
            self.written_publication_run.stderr,
        )

    def test_should_write_the_notes_of_the_section(self) -> None:
        self.assertEqual(self.notes, "### Added\n\n- App: scan from the card\n")


class TheMainFunctionWhenAskedToPublishAVersionSetByHand(unittest.TestCase):
    publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        (repository / "VERSION").write_text("0.3.0\n")
        commit_everything(repository, "build: set VERSION by hand")
        cls.publication_run = run_to_publish(repository)

    def test_should_refuse_since_no_release_commit_set_it(self) -> None:
        self.assertEqual(self.publication_run.returncode, 1)
        self.assertIn("no release commit 'chore(release): 0.3.0'", self.publication_run.stderr)


class TheMainFunctionWhenAskedToPublishAReleaseCommitWrittenByHand(unittest.TestCase):
    publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_nothing(repository, "feat: a")
        (repository / "VERSION").write_text("0.3.0\n")
        commit_everything(repository, "build: set VERSION by hand")
        replace_in_the_changelog(repository, "## [0.2.3]", "## [0.3.0] - 2026-10-20\n\n### Added\n\n- A\n\n## [0.2.3]")
        commit_everything(repository, "chore(release): 0.3.0")
        cls.publication_run = run_to_publish(repository)

    def test_should_refuse_since_it_has_no_release_base_trailer(self) -> None:
        self.assertEqual(self.publication_run.returncode, 1)
        self.assertIn("has no 'Release-Base' trailer", self.publication_run.stderr)


class TheMainFunctionWhenAskedToPublishAfterAVersionTaggedBeforeReleaseCommitsHadATrailer(unittest.TestCase):
    publication_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        append_a_blank_line_to_the_changelog(repository)
        commit_everything(repository, "docs: start the changelog")
        cls.publication_run = run_to_publish(repository)

    def test_should_publish_nothing(self) -> None:
        self.assertEqual(
            (self.publication_run.returncode, self.publication_run.stdout), (0, ""), self.publication_run.stderr
        )


class WorkflowTest(unittest.TestCase):
    """The release workflow is the only one that writes to the repository, and runs nothing else."""

    WORKFLOWS = SCRIPTS.parent / ".github" / "workflows"
    #: Any permission that writes, quoted or not, comments included.
    WRITES = r"[\"']?[a-z-]+[\"']?\s*:\s*[\"']?write\b[\"']?|\bwrite-all\b"

    def test_what_counts_as_writing(self) -> None:
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

    def test_only_the_release_workflow_writes(self) -> None:
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

    def test_the_release_workflow(self) -> None:
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
