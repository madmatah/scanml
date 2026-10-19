from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

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


def run_git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env=build_git_environment(os.environ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def read_head(repository: Path) -> str:
    return run_git(repository, "rev-parse", "HEAD").strip()


@contextmanager
def isolated_git_environment() -> Iterator[None]:
    # For the code under test that runs git in the test's own process, with its environment.
    with mock.patch.dict(os.environ, build_git_environment(os.environ), clear=True):
        yield
