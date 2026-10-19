#!/usr/bin/env python3
"""Publishes screenshots for the description of a pull request, on the `pr-screenshots` branch of origin.

That branch holds no code, only a folder per pull request, `pr-<number>/`, and grows by one commit per publication,
which the script builds with git's plumbing, without touching the checkout: its index, its worktree and its branches
stay as they are. Each picture is linked by the commit that adds it, so a later publication, or the cleanup of the
branch (the `clean-pr-screenshots` skill), never changes what a description already shows while GitHub keeps the commit.

Standard library and git only, from any checkout whose `origin` is on GitHub:

    publish_screenshots.py NUMBER PICTURE...

It prints one Markdown image per picture, to paste into the description of pull request NUMBER. A picture is a PNG
file of at most 10 MB, named with letters, digits, dots, dashes and underscores, that holds only the chunks of an image:
the pixels, their palette, transparency and color space, never a chunk that carries text, a time or a profile.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

BRANCH = "pr-screenshots"
BRANCH_REF = f"refs/heads/{BRANCH}"
#: Where the branch is fetched to: its remote-tracking branch, which a push updates too.
FETCHED_REF = f"refs/remotes/origin/{BRANCH}"
#: GitHub shows an image of a description up to 10 MB.
MAX_PICTURE_BYTES = 10 * 1024 * 1024
#: Above this, the branch weighs on every clone that fetches it: time to clean it (decision of the maintainer).
WARN_ABOVE_BYTES = 30 * 1024 * 1024
#: A push races with another publication: each attempt fetches the branch again and builds on its new tip.
PUSH_ATTEMPTS = 3

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
#: The chunks of the image itself. Any other may carry what a reader does not see in the picture, such as a comment, a
#: path, a time, Exif data or the name of a color profile, often the model of a display.
_IMAGE_CHUNKS = frozenset(
    {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"sBIT", b"bKGD", b"pHYs"}
)
_PICTURE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.png")
_GITHUB_REMOTE = re.compile(
    r"(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repository>[A-Za-z0-9._-]+?)(?:\.git)?/?"
)


class PublicationRefused(RuntimeError):
    """What makes the publication impossible, said to the user as is."""


def check_picture(path: Path) -> bytes:
    """The bytes of the PNG file at `path`, or a refusal that says why it cannot be published."""
    if not _PICTURE_NAME.fullmatch(path.name):
        raise PublicationRefused(f"{path}: name a picture with letters, digits, '.', '-' and '_', ending in .png")
    try:
        size_bytes = path.stat().st_size
        if not path.is_file():
            raise PublicationRefused(f"{path} is not a file")
        if size_bytes > MAX_PICTURE_BYTES:
            raise PublicationRefused(
                f"{path} weighs {size_bytes} bytes, above GitHub's {MAX_PICTURE_BYTES} for an image"
            )
        content = path.read_bytes()
    except OSError as exc:
        raise PublicationRefused(f"cannot read {path}: {exc.strerror}") from None
    if not content.startswith(_PNG_SIGNATURE):
        raise PublicationRefused(f"{path} is not a PNG file")
    position = len(_PNG_SIGNATURE)
    while position < len(content):
        if position + 8 > len(content):
            raise PublicationRefused(f"{path} is a truncated PNG file")
        length = int.from_bytes(content[position : position + 4], "big")
        chunk_type = content[position + 4 : position + 8]
        if chunk_type not in _IMAGE_CHUNKS:
            # A chunk type is four ASCII letters: anything else is shown escaped, never written to the terminal as is.
            name = chunk_type.decode("ascii") if chunk_type.isalpha() else repr(chunk_type)
            raise PublicationRefused(f"{path} holds the chunk {name}, which may carry what the picture does not show")
        position += 12 + length
    if position != len(content):
        raise PublicationRefused(f"{path} is a truncated PNG file")
    return content


def parse_github_repository(remote_url: str) -> tuple[str, str]:
    """The owner and the name of the GitHub repository at `remote_url`, the URL of origin as configured."""
    match = _GITHUB_REMOTE.fullmatch(remote_url.strip())
    if match is None:
        raise PublicationRefused(f"origin is not a GitHub repository: {remote_url.strip()!r}")
    return match["owner"], match["repository"]


def build_picture_url(owner: str, repository: str, commit: str, path: str) -> str:
    return f"https://github.com/{owner}/{repository}/blob/{commit}/{path}?raw=true"


def _run_git(*arguments: str, input_bytes: bytes | None = None, environment: Mapping[str, str] | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments], input=input_bytes, capture_output=True, env=environment, check=False
        )
    except OSError as exc:
        raise PublicationRefused(f"cannot run git: {exc.strerror}") from None
    if completed.returncode != 0:
        message = completed.stderr.decode(errors="replace").strip() or f"exit status {completed.returncode}"
        raise PublicationRefused(f"git {arguments[0]}: {message}")
    return completed.stdout.decode().strip()


def _read_config_values(key: str) -> list[str]:
    """The values of `key` in git's configuration, none when it is not set."""
    try:
        completed = subprocess.run(["git", "config", "--get-all", key], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise PublicationRefused(f"cannot run git: {exc.strerror}") from None
    # git config exits with 1 when the key is not set.
    if completed.returncode not in (0, 1):
        raise PublicationRefused(f"git config: {completed.stderr.strip()}")
    return completed.stdout.splitlines()


def find_origin_repository() -> tuple[str, str]:
    """The owner and the name of origin's GitHub repository, which the links name."""
    # git fetches from origin's first URL, and pushes to its push URLs, or to all its URLs without one: they must all
    # name one repository, whatever their case, as GitHub reads it.
    urls = _read_config_values("remote.origin.url")
    if not urls:
        raise PublicationRefused("this checkout has no origin")
    repositories = [parse_github_repository(url) for url in urls + _read_config_values("remote.origin.pushurl")]
    if len({(owner.lower(), name.lower()) for owner, name in repositories}) > 1:
        raise PublicationRefused("origin's URLs name several repositories: set one URL for fetching and pushing")
    return repositories[0]


def _fetch_branch() -> str | None:
    """The tip of the branch on origin, fetched, or None while the branch does not exist."""
    listed = subprocess.run(["git", "ls-remote", "--exit-code", "origin", BRANCH_REF], capture_output=True, check=False)
    # ls-remote --exit-code exits with 2 when no reference matches.
    if listed.returncode == 2:
        return None
    if listed.returncode != 0:
        raise PublicationRefused(f"git ls-remote: {listed.stderr.decode(errors='replace').strip()}")
    _run_git("fetch", "--quiet", "--no-tags", "origin", f"+{BRANCH_REF}:{FETCHED_REF}")
    return _run_git("rev-parse", "--verify", f"{FETCHED_REF}^{{commit}}")


def _commit(parent: str | None, number: int, pictures: Mapping[str, bytes]) -> str:
    """A commit on `parent` that adds `pictures` under `pr-<number>/`, built in an index of its own."""
    with tempfile.TemporaryDirectory(prefix="publish-screenshots-") as directory:
        environment = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
        if parent is None:
            _run_git("read-tree", "--empty", environment=environment)
        else:
            _run_git("read-tree", parent, environment=environment)
        for name, content in pictures.items():
            blob = _run_git("hash-object", "-w", "--stdin", input_bytes=content)
            entry = f"100644,{blob},pr-{number}/{name}"
            _run_git("update-index", "--add", "--cacheinfo", entry, environment=environment)
        tree = _run_git("write-tree", environment=environment)
    parents = [] if parent is None else ["-p", parent]
    return _run_git("commit-tree", tree, *parents, "-m", f"Screenshots of pull request #{number}")


def _measure_branch_bytes(commit: str) -> int:
    """What the branch weighs: the size of every object its history holds."""
    objects = _run_git("rev-list", "--objects", commit)
    ids = "\n".join(line.split(" ", 1)[0] for line in objects.splitlines()) + "\n"
    sizes_bytes = _run_git("cat-file", "--batch-check=%(objectsize)", input_bytes=ids.encode())
    return sum(int(size_bytes) for size_bytes in sizes_bytes.split())


def publish(number: int, paths: Sequence[Path]) -> tuple[list[str], int]:
    """Publishes the pictures at `paths` for pull request `number`; returns their Markdown and the branch's weight."""
    pictures: dict[str, bytes] = {}
    for path in paths:
        if path.name in pictures:
            raise PublicationRefused(f"two pictures are named {path.name}")
        pictures[path.name] = check_picture(path)
    owner, repository = find_origin_repository()
    commit = None
    failure = ""
    for _ in range(PUSH_ATTEMPTS):
        candidate = _commit(_fetch_branch(), number, pictures)
        pushed = subprocess.run(
            ["git", "push", "--quiet", "origin", f"{candidate}:{BRANCH_REF}"], capture_output=True, check=False
        )
        if pushed.returncode == 0:
            commit = candidate
            break
        failure = pushed.stderr.decode(errors="replace").strip()
    if commit is None:
        raise PublicationRefused(f"git push failed {PUSH_ATTEMPTS} times, the last with: {failure}")
    images = [
        f"![{Path(name).stem}]({build_picture_url(owner, repository, commit, f'pr-{number}/{name}')})"
        for name in pictures
    ]
    return images, _measure_branch_bytes(commit)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publishes screenshots for the description of a pull request.")
    parser.add_argument("number", type=int, help="the number of the pull request")
    parser.add_argument("pictures", type=Path, nargs="+", help="PNG files")
    arguments = parser.parse_args(argv)
    if arguments.number <= 0:
        parser.error("the number of a pull request is positive")
    try:
        images, branch_bytes = publish(arguments.number, arguments.pictures)
    except PublicationRefused as refusal:
        print(f"error: {refusal}", file=sys.stderr)
        return 1
    print("\n".join(images))
    if branch_bytes > WARN_ABOVE_BYTES:
        print(
            f"warning: the {BRANCH} branch weighs {branch_bytes // (1024 * 1024)} MB: the maintainer cleans it with "
            "/clean-pr-screenshots",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
