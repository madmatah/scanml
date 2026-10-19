"""The environment of the tests' own git commands (scripts/tests/git_environment.py).

Standard library only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import types
import unittest
from collections.abc import Mapping
from typing import ClassVar

from git_environment import build_git_environment


class TheBuildGitEnvironmentFunctionWhenTheCallerRunsUnderRebaseExec(unittest.TestCase):
    environment_under_rebase_exec: ClassVar[Mapping[str, str]] = types.MappingProxyType(
        {"PATH": "/usr/bin", "GIT_DIR": "/home/user/project/.git/worktrees/feature", "GIT_PREFIX": ""}
    )

    def setUp(self) -> None:
        self.environment = build_git_environment(self.environment_under_rebase_exec)

    def test_should_drop_the_git_variables_of_its_caller_so_that_the_tests_git_works_on_its_own_repository(
        self,
    ) -> None:
        self.assertEqual(self.environment.keys() & {"GIT_DIR", "GIT_PREFIX"}, set())

    def test_should_keep_the_other_variables_of_its_caller(self) -> None:
        self.assertEqual(self.environment["PATH"], "/usr/bin")


if __name__ == "__main__":
    unittest.main()
