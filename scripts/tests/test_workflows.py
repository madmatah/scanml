"""The workflows of the repository (.github/workflows/): what they may write, and what they run.

Standard library only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import ClassVar

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
WORKFLOW_NAMES = ("ci.yml", "release.yml")
WRITING_PERMISSION_PATTERN = r"[\"']?[a-z-]+[\"']?\s*:\s*[\"']?write\b[\"']?|\bwrite-all\b"


class TheWritingPermissionPatternWhenAPermissionWrites(unittest.TestCase):
    permissions: ClassVar[tuple[str, ...]] = (
        'contents: "write"',
        "pull-requests:\twrite",
        "permissions: write-all",
        "contents: write  # x",
        "contents: 'write'",
        '"contents": write',
        "'pull-requests': write",
        "contents : write",
        'permissions: {"contents": write}',
    )

    def setUp(self) -> None:
        self.matches = {
            permission: re.findall(WRITING_PERMISSION_PATTERN, permission) for permission in self.permissions
        }

    def test_should_match_it_however_it_is_written_so_that_the_workflow_tests_see_every_write(self) -> None:
        for permission in self.permissions:
            with self.subTest(permission):
                self.assertNotEqual(self.matches[permission], [])


class TheWritingPermissionPatternWhenNoPermissionWrites(unittest.TestCase):
    def setUp(self) -> None:
        self.matches = re.findall(WRITING_PERMISSION_PATTERN, "contents: read\n# it writes nothing\n")

    def test_should_match_nothing_even_where_a_comment_says_write(self) -> None:
        self.assertEqual(self.matches, [])


class TheWorkflowsOfTheRepository(unittest.TestCase):
    action_reference_pattern: ClassVar[re.Pattern[str]] = re.compile(r"^\s*(?:- )?uses: (\S+)", re.MULTILINE)

    def setUp(self) -> None:
        self.workflows = {workflow.name: workflow.read_text() for workflow in sorted(WORKFLOWS.glob("*.y*ml"))}
        self.actions = [
            (name, action)
            for name, text in self.workflows.items()
            for action in self.action_reference_pattern.findall(text)
        ]

    def test_should_be_the_ci_and_release_workflows_alone_so_that_a_new_one_is_checked_here(self) -> None:
        self.assertEqual(list(self.workflows), list(WORKFLOW_NAMES))

    def test_should_use_no_secret(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES))
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertNotIn("secrets.", text)

    def test_should_never_run_on_pull_request_target(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES))
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertNotRegex(text, r"\bpull_request_target\b")

    def test_should_use_only_the_checkout_and_cache_actions_pinned_to_a_commit(self) -> None:
        self.assertGreater(len(self.actions), 0)
        for name, action in self.actions:
            with self.subTest(workflow=name, action=action):
                self.assertRegex(action, r"^actions/checkout@[0-9a-f]{40}$|^actions/cache@[0-9a-f]{40}$")


class TheWorkflowsOtherThanTheReleaseOne(unittest.TestCase):
    def setUp(self) -> None:
        self.workflows = {
            workflow.name: workflow.read_text()
            for workflow in sorted(WORKFLOWS.glob("*.y*ml"))
            if workflow.name != "release.yml"
        }

    def test_should_write_nothing(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES) - 1)
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertEqual(re.findall(WRITING_PERMISSION_PATTERN, text), [])

    def test_should_only_read_the_contents_of_the_repository(self) -> None:
        self.assertEqual(len(self.workflows), len(WORKFLOW_NAMES) - 1)
        for name, text in self.workflows.items():
            with self.subTest(name):
                self.assertRegex(text, r"\npermissions:\n  contents: read\n")


class TheReleaseWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (WORKFLOWS / "release.yml").read_text()
        self.triggers = self.text.split("\non:\n", 1)[1].split("\n\n", 1)[0]

    def test_should_write_the_contents_of_the_repository_alone(self) -> None:
        self.assertEqual(re.findall(WRITING_PERMISSION_PATTERN, self.text), ["contents: write"])

    def test_should_run_on_a_push_to_main_that_changes_version_or_the_changelog(self) -> None:
        self.assertEqual(self.triggers, "  push:\n    branches: [main]\n    paths: [VERSION, CHANGELOG.md]")

    def test_should_grant_no_permission_unless_a_job_asks_for_it(self) -> None:
        self.assertIn("\npermissions: {}\n", self.text)

    def test_should_not_keep_the_credentials_of_its_checkout(self) -> None:
        self.assertIn("persist-credentials: false", self.text)

    def test_should_fetch_the_whole_history_since_release_py_reads_the_history_and_the_tags(self) -> None:
        self.assertIn("fetch-depth: 0", self.text)

    def test_should_use_the_checkout_action_alone_pinned_to_its_commit(self) -> None:
        self.assertEqual(
            re.findall(r"uses: (\S+)", self.text), ["actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"]
        )

    def test_should_ask_release_py_what_the_commit_publishes(self) -> None:
        self.assertIn('python3 scripts/release.py --ref "$COMMIT" --to-publish', self.text)

    def test_should_tag_the_commit_release_py_names_never_the_head_of_the_push(self) -> None:
        self.assertIn('read -r version target <<< "$release"', self.text)
        self.assertIn('-f object="$target"', self.text)
        self.assertEqual(self.text.count("$COMMIT"), 1)


if __name__ == "__main__":
    unittest.main()
