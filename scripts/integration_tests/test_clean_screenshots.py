"""The cleanup of the screenshots of pull requests (`.claude/skills/clean-pr-screenshots/scripts/clean_screenshots.py`),
against a bare origin that the script takes for a GitHub repository, and a stand-in for the GitHub CLI
(screenshots_support.py).

Needs git. Standard library only:
    python3 -m unittest discover -s scripts/integration_tests -p 'test_clean_screenshots.py'
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from screenshots_support import BRANCH, CLEAN, FETCHED_REF, OWNER, PUBLISH, REPOSITORY, Remote, Run, make_png

COMMIT = "0123456789abcdef0123456789abcdef01234567"
#: Open pull requests: two link pictures of the branch, in the two forms GitHub serves them; the others link nothing of
#: it, one of them a picture of another repository.
OPEN_PULL_REQUESTS = [
    {"number": 8, "body": f"![a](https://raw.githubusercontent.com/{OWNER}/{REPOSITORY}/{COMMIT}/pr-8/a.png)"},
    {"number": 5, "body": "No picture."},
    {"number": 4, "body": f"![c](https://github.com/{OWNER}/other/blob/{COMMIT}/pr-4/c.png?raw=true)"},
    {"number": 3, "body": f"![b](https://github.com/{OWNER}/{REPOSITORY}/blob/{COMMIT}/pr-3/b.png?raw=true)"},
    {"number": 9, "body": None},
]


def make_remote(test_case: type[unittest.TestCase]) -> Remote:
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-screenshots-")
    test_case.addClassCleanup(directory.cleanup)
    return Remote(Path(os.path.realpath(directory.name)))


def make_published_remote(test_case: type[unittest.TestCase]) -> Remote:
    """A remote whose branch holds a publication, made from the clone, and whose open pull requests are listed."""
    remote = make_remote(test_case)
    # The publication's push leaves the branch's remote-tracking branch in the clone.
    remote.run(PUBLISH, "3", str(remote.write_picture("b.png", make_png())))
    remote.gh_answer.write_text(json.dumps(OPEN_PULL_REQUESTS))
    return remote


class WhenOpenPullRequestsLinkPicturesOfTheBranch(unittest.TestCase):
    cleanup: ClassVar[Run]
    tip: ClassVar[str | None]
    gh_calls: ClassVar[list[str]]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_published_remote(cls)
        cls.cleanup = remote.run(CLEAN)
        cls.tip = remote.read_branch_tip()
        cls.gh_calls = remote.gh_log.read_text().splitlines()

    def test_should_list_the_open_pull_requests_that_link_a_picture_of_the_branch(self) -> None:
        self.assertEqual(
            [line for line in self.cleanup.stdout.splitlines() if line.startswith("  #")],
            [
                f"  #3 https://github.com/{OWNER}/{REPOSITORY}/pull/3",
                f"  #8 https://github.com/{OWNER}/{REPOSITORY}/pull/8",
            ],
        )

    def test_should_ask_github_for_the_open_pull_requests_of_origin(self) -> None:
        self.assertEqual(
            self.gh_calls, [f"pr list --repo {OWNER}/{REPOSITORY} --state open --limit 1000 --json number,body"]
        )

    def test_should_delete_nothing_without_delete(self) -> None:
        self.assertIsNotNone(self.tip)

    def test_should_say_how_to_delete(self) -> None:
        self.assertIn("run again with --delete", self.cleanup.stdout)


class WhenTheBranchIsDeleted(unittest.TestCase):
    cleanup: ClassVar[Run]
    tip: ClassVar[str | None]
    fetched_before: ClassVar[str]
    fetched: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_published_remote(cls)
        # A fetch configuration that maps no branch of screenshots, so that only the script can drop its copy.
        main_only = "+refs/heads/main:refs/remotes/origin/main"
        remote.run_git("-C", str(remote.clone), "config", "remote.origin.fetch", main_only)
        cls.fetched_before = remote.run_git("-C", str(remote.clone), "for-each-ref", FETCHED_REF)
        cls.cleanup = remote.run(CLEAN, "--delete")
        cls.tip = remote.read_branch_tip()
        cls.fetched = remote.run_git("-C", str(remote.clone), "for-each-ref", FETCHED_REF)

    def test_should_warn_of_the_open_pull_requests_it_breaks(self) -> None:
        self.assertIn(f"  #3 https://github.com/{OWNER}/{REPOSITORY}/pull/3", self.cleanup.stdout)

    def test_should_delete_the_branch_on_origin(self) -> None:
        self.assertIsNone(self.tip)

    def test_should_drop_the_copy_that_the_publication_fetched(self) -> None:
        self.assertEqual((bool(self.fetched_before), self.fetched), (True, ""))

    def test_should_say_it_deleted_the_branch(self) -> None:
        self.assertIn(f"Deleted the {BRANCH.removeprefix('refs/heads/')} branch on origin.", self.cleanup.stdout)


class WhenOriginHasNoBranchOfScreenshots(unittest.TestCase):
    cleanup: ClassVar[Run]
    gh_called: ClassVar[bool]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_remote(cls)
        cls.cleanup = remote.run(CLEAN, "--delete")
        cls.gh_called = remote.gh_log.exists()

    def test_should_say_there_is_nothing_to_clean(self) -> None:
        self.assertEqual(self.cleanup.stdout, "Nothing to clean: origin has no pr-screenshots branch.\n")

    def test_should_not_ask_github(self) -> None:
        self.assertFalse(self.gh_called)


class WhenGitHubAnswersWithSomethingElseThanPullRequests(unittest.TestCase):
    cleanup: ClassVar[Run]
    tip: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_published_remote(cls)
        remote.gh_answer.write_text(json.dumps({"message": "Not Found"}))
        cls.cleanup = remote.run(CLEAN, "--delete")
        cls.tip = remote.read_branch_tip()

    def test_should_refuse_since_it_could_not_tell_which_pull_requests_link_pictures(self) -> None:
        self.assertIn("error: gh pr list printed no list of pull requests", self.cleanup.stderr)

    def test_should_delete_nothing(self) -> None:
        self.assertIsNotNone(self.tip)


class WhenOriginPushesToAnotherRepository(unittest.TestCase):
    cleanup: ClassVar[Run]
    tip: ClassVar[str | None]
    fork_tip: ClassVar[str]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_published_remote(cls)
        fork_url = f"git@github.com:{OWNER}/fork.git"
        fork = remote.make_fork(fork_url)
        remote.run_origin_git("push", "--quiet", str(fork), BRANCH)
        remote.run_git("-C", str(remote.clone), "config", "remote.origin.pushurl", fork_url)
        cls.cleanup = remote.run(CLEAN, "--delete")
        cls.tip = remote.read_branch_tip()
        cls.fork_tip = remote.run_git("--git-dir", str(fork), "for-each-ref", BRANCH)

    def test_should_refuse_since_it_would_check_one_repository_and_delete_in_another(self) -> None:
        self.assertIn("origin's URLs name several repositories", self.cleanup.stderr)

    def test_should_delete_in_neither_repository(self) -> None:
        self.assertIsNotNone(self.tip)
        self.assertNotEqual(self.fork_tip, "")


class WhenGitHubCannotListThePullRequests(unittest.TestCase):
    cleanup: ClassVar[Run]
    tip: ClassVar[str | None]

    @classmethod
    def setUpClass(cls) -> None:
        remote = make_published_remote(cls)
        remote.gh_answer.unlink()
        cls.cleanup = remote.run(CLEAN, "--delete")
        cls.tip = remote.read_branch_tip()

    def test_should_refuse_with_the_error_of_gh(self) -> None:
        self.assertIn("error: gh pr: gh: not logged in", self.cleanup.stderr)

    def test_should_delete_nothing_since_it_could_not_warn(self) -> None:
        self.assertIsNotNone(self.tip)


if __name__ == "__main__":
    unittest.main()
