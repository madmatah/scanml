"""The commits that already passed scripts/check.sh --last-commit, which it skips (scripts/lib/passed_commit_check.py).

Standard library and git only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from git_environment import build_git_environment, isolated_git_environment, run_git

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
import passed_commit_check

PASSED_COMMIT_CHECK = Path(__file__).resolve().parent.parent / "lib" / "passed_commit_check.py"
MUST_CHECK_STATUS = 3
ALREADY_PASSED = "Skipped: this commit already passed the check."
FIXUP_SKIPPED = "Skipped: a fixup is checked once folded into its commit."
NOT_RECORDED = "Not recorded: the working tree has changes or untracked files."


class CheckDidNotAskForTheAreas(RuntimeError):
    pass


def run_passed_commit_check(
    *arguments: str, environment: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PASSED_COMMIT_CHECK), *arguments],
        env={**build_git_environment(os.environ), **(environment or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def run_check(repository: Path) -> subprocess.CompletedProcess[str]:
    return run_passed_commit_check("check", str(repository))


def make_temporary_directory(test_case: type[unittest.TestCase]) -> Path:
    return Path(test_case.enterClassContext(tempfile.TemporaryDirectory(prefix="scanmylib-passed-"))).resolve()


def make_repository(test_case: type[unittest.TestCase]) -> Path:
    repository = make_temporary_directory(test_case)
    run_git(repository, "init", "--quiet", "--initial-branch=main")
    return repository


def commit_file(repository: Path, name: str, text: str, message: str) -> str:
    (repository / name).write_text(text)
    run_git(repository, "add", "--all")
    run_git(repository, "commit", "--quiet", "--message", message)
    return run_git(repository, "rev-parse", "--short", "HEAD").strip()


def commit_three_files(repository: Path) -> list[str]:
    return [
        commit_file(repository, f"{name}.md", f"# {name}\n", f"docs: add the {name}")
        for name in ("guide", "notes", "glossary")
    ]


def find_record(repository: Path) -> Path:
    with isolated_git_environment():
        return passed_commit_check.find_record(repository)


def check_and_record(repository: Path, tree_state: str | None = None) -> subprocess.CompletedProcess[str]:
    check_run = run_check(repository)
    if check_run.returncode != MUST_CHECK_STATUS:
        raise CheckDidNotAskForTheAreas(f"check exited with {check_run.returncode}: {check_run.stdout}")
    head_tree, parent_tree, printed_state = check_run.stdout.split()
    return run_passed_commit_check("record", str(repository), f"{head_tree} {parent_tree}", tree_state or printed_state)


def check_and_record_each_commit(repository: Path, commits: list[str]) -> None:
    for commit in commits:
        run_git(repository, "checkout", "--quiet", "--detach", commit)
        check_and_record(repository)
    run_git(repository, "checkout", "--quiet", "main")


def check_each_commit(repository: Path, commits: list[str]) -> list[int]:
    statuses = []
    for commit in commits:
        run_git(repository, "checkout", "--quiet", "--detach", commit)
        statuses.append(run_check(repository).returncode)
    run_git(repository, "checkout", "--quiet", "main")
    return statuses


def list_commits(repository: Path) -> list[str]:
    return run_git(repository, "log", "--reverse", "--format=%h", "main").split()


class TheCheckCommandWhenTheCommitAlreadyPassed(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_three_files(repository)
        check_and_record(repository)
        cls.check_run = run_check(repository)

    def test_should_skip_it_and_say_so(self) -> None:
        self.assertEqual(self.check_run.returncode, 0, self.check_run.stderr)
        self.assertEqual(self.check_run.stdout.strip(), ALREADY_PASSED)


class TheCheckCommandWhenTheCommitPassedInAnotherWorktree(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_three_files(repository)
        check_and_record(repository)
        worktree = make_temporary_directory(cls) / "worktree"
        run_git(repository, "worktree", "add", "--quiet", "--detach", str(worktree), "main")
        cls.check_run = run_check(worktree)

    def test_should_skip_it_since_every_worktree_shares_the_record(self) -> None:
        self.assertEqual(self.check_run.returncode, 0, self.check_run.stderr)
        self.assertEqual(self.check_run.stdout.strip(), ALREADY_PASSED)


class TheCheckCommandWhenAPassedCommitIsReworded(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_three_files(repository)
        check_and_record(repository)
        run_git(repository, "commit", "--quiet", "--amend", "--message", "docs: name the terms of the guide")
        cls.check_run = run_check(repository)

    def test_should_skip_it_since_its_files_and_its_parent_s_did_not_change(self) -> None:
        self.assertEqual(self.check_run.returncode, 0, self.check_run.stderr)
        self.assertEqual(self.check_run.stdout.strip(), ALREADY_PASSED)


class TheCheckCommandWhenAFixupIsFoldedIntoTheSecondOfThreePassedCommits(unittest.TestCase):
    statuses: ClassVar[list[int]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commits = commit_three_files(repository)
        check_and_record_each_commit(repository, commits)
        (repository / "notes.md").write_text("# notes\n\nThe notes of the guide.\n")
        run_git(repository, "commit", "--quiet", "--all", f"--fixup={commits[1]}")
        run_git(repository, "-c", "sequence.editor=:", "rebase", "--quiet", "-i", "--autosquash", "--root")
        cls.statuses = check_each_commit(repository, list_commits(repository))

    def test_should_skip_the_first_check_the_second_that_the_fix_changed_and_the_third_that_follows_it(self) -> None:
        self.assertEqual(self.statuses, [0, MUST_CHECK_STATUS, MUST_CHECK_STATUS])


class TheCheckCommandWhenTwoPassedCommitsAreSquashed(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commits = commit_three_files(repository)
        check_and_record_each_commit(repository, commits)
        run_git(repository, "reset", "--quiet", "--soft", "HEAD~2")
        run_git(repository, "commit", "--quiet", "--message", "docs: add the notes and the glossary")
        cls.check_run = run_check(repository)

    def test_should_check_it_since_the_squash_holds_the_changes_of_both(self) -> None:
        self.assertEqual(self.check_run.returncode, MUST_CHECK_STATUS, self.check_run.stderr)


class TheCheckCommandWhenTheCommitHasNoParent(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]
    tree: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_file(repository, "guide.md", "# guide\n", "docs: add the guide")
        cls.tree = run_git(repository, "rev-parse", "HEAD^{tree}").strip()
        cls.check_run = run_check(repository)

    def test_should_ask_for_the_areas_with_root_in_place_of_the_parent_s_tree(self) -> None:
        self.assertEqual(self.check_run.returncode, MUST_CHECK_STATUS, self.check_run.stderr)
        self.assertEqual(self.check_run.stdout.strip(), f"{self.tree} root clean")


class TheCheckCommandWhenAPassedCommitHasAnUntrackedFileBeside(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_three_files(repository)
        check_and_record(repository)
        run_git(repository, "config", "status.showUntrackedFiles", "no")
        (repository / "draft.md").write_text("# draft\n")
        cls.check_run = run_check(repository)

    def test_should_check_it_whatever_git_status_shows_since_the_areas_would_read_the_untracked_file(self) -> None:
        self.assertEqual(self.check_run.returncode, MUST_CHECK_STATUS, self.check_run.stderr)

    def test_should_report_the_working_tree_dirty(self) -> None:
        self.assertEqual(self.check_run.stdout.split()[-1], "dirty")


class TheCheckCommandWhenAPassedCommitHasAChangedFileThatGitStatusHides(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_three_files(repository)
        check_and_record(repository)
        run_git(repository, "update-index", "--skip-worktree", "guide.md")
        (repository / "guide.md").write_text("# guide\n\nA change that git status does not show.\n")
        cls.check_run = run_check(repository)

    def test_should_check_it_since_the_areas_would_read_the_changed_file(self) -> None:
        self.assertEqual(self.check_run.returncode, MUST_CHECK_STATUS, self.check_run.stderr)

    def test_should_report_the_working_tree_dirty(self) -> None:
        self.assertEqual(self.check_run.stdout.split()[-1], "dirty")


class TheCheckCommandWhenTheHeaderStartsAsAFixup(unittest.TestCase):
    prefixes: ClassVar[tuple[str, ...]] = ("fixup! ", "amend! ", "squash! ")
    check_runs: ClassVar[dict[str, subprocess.CompletedProcess[str]]]
    is_recorded: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_file(repository, "guide.md", "# guide\n", "docs: add the guide")
        cls.check_runs = {}
        for prefix in cls.prefixes:
            run_git(repository, "commit", "--quiet", "--allow-empty", "--message", f"{prefix}docs: add the guide")
            cls.check_runs[prefix] = run_check(repository)
        cls.is_recorded = find_record(repository).exists()

    def test_should_skip_it_and_say_that_it_is_checked_once_folded(self) -> None:
        self.assertEqual(len(self.check_runs), len(self.prefixes))
        for prefix, check_run in self.check_runs.items():
            with self.subTest(prefix):
                self.assertEqual(check_run.returncode, 0, check_run.stderr)
                self.assertEqual(check_run.stdout.strip(), FIXUP_SKIPPED)

    def test_should_record_nothing(self) -> None:
        self.assertFalse(self.is_recorded)


class TheCheckCommandWhenTheHeaderHoldsAFixupMarkPastItsStart(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_file(repository, "guide.md", "# guide\n", "docs: say what fixup! commits are for")
        cls.check_run = run_check(repository)

    def test_should_ask_for_the_areas_since_only_autosquash_s_own_prefixes_mark_a_fixup(self) -> None:
        self.assertEqual(self.check_run.returncode, MUST_CHECK_STATUS, self.check_run.stderr)


class TheCheckCommandWhenTheRootIsOutsideAGitRepository(unittest.TestCase):
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        directory = make_temporary_directory(cls)
        # So that git does not find a repository that encloses the temporary directory.
        cls.check_run = run_passed_commit_check(
            "check", str(directory), environment={"GIT_CEILING_DIRECTORIES": str(directory.parent)}
        )

    def test_should_exit_with_neither_the_skip_nor_the_check_status_so_that_the_caller_stops(self) -> None:
        self.assertNotIn(self.check_run.returncode, (0, MUST_CHECK_STATUS))


class TheRecordCommandWhenTheWorkingTreeWasDirty(unittest.TestCase):
    record_run: ClassVar[subprocess.CompletedProcess[str]]
    check_run: ClassVar[subprocess.CompletedProcess[str]]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_three_files(repository)
        cls.record_run = check_and_record(repository, tree_state="dirty")
        cls.check_run = run_check(repository)

    def test_should_say_that_it_records_nothing(self) -> None:
        self.assertEqual(self.record_run.returncode, 0, self.record_run.stderr)
        self.assertEqual(self.record_run.stdout.strip(), NOT_RECORDED)

    def test_should_leave_the_next_check_to_ask_for_the_areas(self) -> None:
        self.assertEqual(self.check_run.returncode, MUST_CHECK_STATUS, self.check_run.stderr)


class TheRecordCommandWhenTheKeyIsNotATreePair(unittest.TestCase):
    record_run: ClassVar[subprocess.CompletedProcess[str]]
    is_recorded: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        repository = make_repository(cls)
        commit_file(repository, "guide.md", "# guide\n", "docs: add the guide")
        cls.record_run = run_passed_commit_check("record", str(repository), "HEAD root", "clean")
        cls.is_recorded = find_record(repository).exists()

    def test_should_refuse_it_naming_what_a_key_is(self) -> None:
        self.assertNotEqual(self.record_run.returncode, 0)
        self.assertIn("not a tree and its parent's tree", self.record_run.stderr)

    def test_should_record_nothing(self) -> None:
        self.assertFalse(self.is_recorded)


if __name__ == "__main__":
    unittest.main()
