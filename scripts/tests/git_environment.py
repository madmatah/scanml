from __future__ import annotations

from collections.abc import Mapping

_ISOLATED_GIT_SETTINGS = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def build_git_environment(caller_environment: Mapping[str, str]) -> dict[str, str]:
    # `git rebase --exec` run in a worktree exports GIT_DIR, which would send a test's git to the caller's repository.
    without_git = {name: value for name, value in caller_environment.items() if not name.startswith("GIT_")}
    return {**without_git, **_ISOLATED_GIT_SETTINGS}
