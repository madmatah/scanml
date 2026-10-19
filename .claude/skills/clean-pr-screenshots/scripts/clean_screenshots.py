#!/usr/bin/env python3
"""Cleans the `pr-screenshots` branch of origin, where the pull-request skill publishes screenshots.

The cleanup is blunt: it deletes the whole branch. The descriptions of the pull requests that link its pictures are
left as they are, and their pictures break once GitHub drops the commits. So it first lists the open pull requests
whose description links a picture of the branch, and deletes nothing without --delete.

Standard library, git and the GitHub CLI (`gh`, logged in) only, from any checkout whose `origin` is on GitHub:

    clean_screenshots.py            what the cleanup would delete, and the open pull requests it would break
    clean_screenshots.py --delete   the same, then deletes the branch on origin
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence

BRANCH = "pr-screenshots"
BRANCH_REF = f"refs/heads/{BRANCH}"
#: The branch's remote-tracking branch, where the pull-request skill's script fetches it.
FETCHED_REF = f"refs/remotes/origin/{BRANCH}"
#: More open pull requests than any review queue holds.
LISTED_PULL_REQUESTS = 1000

_GITHUB_REMOTE = re.compile(
    r"(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repository>[A-Za-z0-9._-]+?)(?:\.git)?/?"
)


class CleanupRefused(RuntimeError):
    """What makes the cleanup impossible, said to the user as is."""


def parse_github_repository(remote_url: str) -> tuple[str, str]:
    """The owner and the name of the GitHub repository at `remote_url`, the URL of origin as configured."""
    match = _GITHUB_REMOTE.fullmatch(remote_url.strip())
    if match is None:
        raise CleanupRefused(f"origin is not a GitHub repository: {remote_url.strip()!r}")
    return match["owner"], match["repository"]


def compile_picture_link(owner: str, repository: str) -> re.Pattern[str]:
    """A link to a picture of the branch, as the pull-request skill's script writes it, or as raw content."""
    names = f"{re.escape(owner)}/{re.escape(repository)}"
    return re.compile(
        rf"(?:github\.com/{names}/(?:blob|raw)|raw\.githubusercontent\.com/{names})/[0-9a-f]{{40}}/pr-[0-9]+/",
        re.IGNORECASE,
    )


def _run(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise CleanupRefused(f"cannot run {command[0]}: {exc.strerror}") from None
    if completed.returncode != 0:
        raise CleanupRefused(f"{command[0]} {command[1]}: {completed.stderr.strip() or 'failed'}")
    return completed.stdout


def _read_config_values(key: str) -> list[str]:
    """The values of `key` in git's configuration, none when it is not set."""
    try:
        completed = subprocess.run(["git", "config", "--get-all", key], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise CleanupRefused(f"cannot run git: {exc.strerror}") from None
    # git config exits with 1 when the key is not set.
    if completed.returncode not in (0, 1):
        raise CleanupRefused(f"git config: {completed.stderr.strip()}")
    return completed.stdout.splitlines()


def find_origin_repository() -> tuple[str, str]:
    """The owner and the name of origin's GitHub repository, where the branch is looked for and deleted."""
    # git reads from origin's first URL, and deletes through its push URLs, or all its URLs without one: they must all
    # name one repository, whatever their case, as GitHub reads it.
    urls = _read_config_values("remote.origin.url")
    if not urls:
        raise CleanupRefused("this checkout has no origin")
    repositories = [parse_github_repository(url) for url in urls + _read_config_values("remote.origin.pushurl")]
    if len({(owner.lower(), name.lower()) for owner, name in repositories}) > 1:
        raise CleanupRefused("origin's URLs name several repositories: set one URL for reading and deleting")
    return repositories[0]


def _is_branch_on_origin() -> bool:
    listed = subprocess.run(
        ["git", "ls-remote", "--exit-code", "origin", BRANCH_REF], capture_output=True, text=True, check=False
    )
    # ls-remote --exit-code exits with 2 when no reference matches.
    if listed.returncode == 2:
        return False
    if listed.returncode != 0:
        raise CleanupRefused(f"git ls-remote: {listed.stderr.strip()}")
    return True


def list_pull_requests_linking(owner: str, repository: str) -> list[int]:
    """The open pull requests whose description links a picture of the branch, in increasing order."""
    listed = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            f"{owner}/{repository}",
            "--state",
            "open",
            "--limit",
            str(LISTED_PULL_REQUESTS),
            "--json",
            "number,body",
        ]
    )
    try:
        pull_requests = json.loads(listed)
    except ValueError as exc:
        raise CleanupRefused(f"gh pr list printed no JSON: {exc}") from None
    # Anything but a list of pull requests would read as "no pull request links a picture", and the deletion go ahead.
    if not isinstance(pull_requests, list) or not all(isinstance(each, dict) for each in pull_requests):
        raise CleanupRefused("gh pr list printed no list of pull requests")
    link = compile_picture_link(owner, repository)
    return sorted(
        int(pull_request["number"])
        for pull_request in pull_requests
        if link.search(str(pull_request.get("body") or ""))
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Cleans the {BRANCH} branch of origin.")
    parser.add_argument("--delete", action="store_true", help="delete the branch on origin")
    arguments = parser.parse_args(argv)
    try:
        owner, repository = find_origin_repository()
        if not _is_branch_on_origin():
            print(f"Nothing to clean: origin has no {BRANCH} branch.")
            return 0
        linking = list_pull_requests_linking(owner, repository)
        if linking:
            print(f"warning: these open pull requests link pictures of the {BRANCH} branch, which its deletion breaks:")
            for number in linking:
                print(f"  #{number} https://github.com/{owner}/{repository}/pull/{number}")
        else:
            print(f"No open pull request links a picture of the {BRANCH} branch.")
        if not arguments.delete:
            print(f"Nothing was deleted: run again with --delete to delete the {BRANCH} branch on origin.")
            return 0
        _run(["git", "push", "--quiet", "origin", "--delete", BRANCH_REF])
        # The copy that the publication fetched, if this checkout has one.
        subprocess.run(["git", "update-ref", "-d", FETCHED_REF], capture_output=True, check=False)
    except CleanupRefused as refusal:
        print(f"error: {refusal}", file=sys.stderr)
        return 1
    print(f"Deleted the {BRANCH} branch on origin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
