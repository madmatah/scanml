"""The environment of the tests' own git commands (scripts/tests/git_environment.py).

Standard library only:
    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import unittest

from git_environment import build_git_environment


class GitEnvironmentTest(unittest.TestCase):
    def test_the_tests_git_never_gets_the_git_variables_of_its_caller(self) -> None:
        environment_under_rebase_exec = {
            "PATH": "/usr/bin", "GIT_DIR": "/home/user/project/.git/worktrees/feature", "GIT_PREFIX": "",
        }
        environment = build_git_environment(environment_under_rebase_exec)
        self.assertNotIn("GIT_DIR", environment)
        self.assertNotIn("GIT_PREFIX", environment)
        self.assertEqual(environment["PATH"], "/usr/bin")


if __name__ == "__main__":
    unittest.main()
