#!/usr/bin/env python3
"""Publishes the screenshots of pull requests on the `pr-screenshots` branch of origin, and cleans that branch.

The branch holds no code, only a folder per pull request, `pr-<number>/`, and grows by one commit per publication,
which this script builds with git's plumbing, without touching the checkout: its index, its worktree and its branches
stay as they are. Each picture is linked by the commit that adds it, so a later publication never changes what a
description already shows.

The cleanup is blunt: it deletes the whole branch. The descriptions that link its pictures are left as they are, and
their pictures break once GitHub drops the commits. So it first lists the open pull requests whose description links a
picture of the branch, and deletes nothing without --delete.

Python 3.9 or later, its standard library and git only, plus the GitHub CLI (`gh`, logged in) for the cleanup, from any
checkout whose `origin` is on GitHub. Run it through `python3`, since a copy of this file may lose its executable bit:

    python3 pr_screenshots.py publish NUMBER PICTURE...   one Markdown image per picture, for pull request NUMBER
    python3 pr_screenshots.py strip DIRECTORY PICTURE...  a copy of each picture, with its image only, in DIRECTORY,
                                                          a new directory that it creates
    python3 pr_screenshots.py clean                       what the cleanup would delete, and the pull requests it breaks
    python3 pr_screenshots.py clean --delete              the same, then deletes the branch on origin

A picture is a PNG file of at most 10 MB, named with letters, digits, dots, dashes and underscores, that holds only the
chunks of an image: the pixels, their palette, transparency and color space, never a chunk that carries text, a time or
a profile. Capture tools often add such chunks: `strip` copies a picture without them into a directory that must not
exist yet, and leaves the picture as it is.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
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
#: More open pull requests than any review queue holds.
LISTED_PULL_REQUESTS = 1000

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


class Refusal(RuntimeError):
    """What makes the publication or the cleanup impossible, said to the user as is."""


def check_picture(path: Path) -> bytes:
    """The bytes of the PNG file at `path`, or a refusal that says why it cannot be published."""
    if not _PICTURE_NAME.fullmatch(path.name):
        raise Refusal(f"{path}: name a picture with letters, digits, '.', '-' and '_', ending in .png")
    try:
        size_bytes = path.stat().st_size
        if not path.is_file():
            raise Refusal(f"{path} is not a file")
        if size_bytes > MAX_PICTURE_BYTES:
            raise Refusal(f"{path} weighs {size_bytes} bytes, above GitHub's {MAX_PICTURE_BYTES} for an image")
        content = path.read_bytes()
    except OSError as exc:
        raise Refusal(f"cannot read {path}: {exc.strerror}") from None
    for chunk_type, _ in _walk_chunks(path, content):
        if chunk_type not in _IMAGE_CHUNKS:
            # A chunk type is four ASCII letters: anything else is shown escaped, never written to the terminal as is.
            name = chunk_type.decode("ascii") if chunk_type.isalpha() else repr(chunk_type)
            raise Refusal(f"{path} holds the chunk {name}, which may carry what the picture does not show")
    return content


def _walk_chunks(path: Path, content: bytes) -> Iterator[tuple[bytes, bytes]]:
    """The chunks of `content`, the PNG file at `path`, each as its type and its whole bytes, or a refusal.

    Each chunk is yielded as soon as it is read, so that a reader that stops at one, such as `check_picture` at a
    forbidden chunk, says so even when the file is cut further on.
    """
    if not content.startswith(_PNG_SIGNATURE):
        raise Refusal(f"{path} is not a PNG file")
    position = len(_PNG_SIGNATURE)
    while position < len(content):
        if position + 8 > len(content):
            raise Refusal(f"{path} is a truncated PNG file")
        length = int.from_bytes(content[position : position + 4], "big")
        # Its length, its type, its data and its checksum.
        end = position + 12 + length
        if end > len(content):
            raise Refusal(f"{path} is a truncated PNG file")
        yield content[position + 4 : position + 8], content[position:end]
        position = end


def strip(directory: Path, paths: Sequence[Path]) -> list[Path]:
    """Creates `directory` with a copy of each PNG file at `paths`, with the chunks of its image only; returns them.

    Each copy keeps the name of its picture. `directory` must not exist yet, so no file is ever overwritten, the
    pictures included. Every picture is read and checked first, and two pictures of the same name are refused, whatever
    its case, since a filesystem may not tell the cases apart; only then is `directory` created and each copy written.
    A failure while writing removes `directory` with what it holds, or says that it could not. A copy drops any color
    profile, so its colors may shift slightly from those of a picture taken in a wider gamut, such as Display P3.
    """
    if os.path.lexists(directory):
        raise Refusal(f"{directory} already exists: give a path that does not exist yet, which strip creates")
    # The pictures by their name in any case, which the name of a copy keeps.
    pictures: dict[str, Path] = {}
    copies: dict[Path, bytes] = {}
    for path in paths:
        name = path.name.casefold()
        if name in pictures:
            raise Refusal(f"{pictures[name]} and {path} have the same name, whatever its case: rename one")
        pictures[name] = path
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise Refusal(f"cannot read {path}: {exc.strerror}") from None
        image = (whole for chunk_type, whole in _walk_chunks(path, content) if chunk_type in _IMAGE_CHUNKS)
        copies[directory / path.name] = _PNG_SIGNATURE + b"".join(image)
    try:
        # Refuses a path that something took in the meantime.
        os.mkdir(directory)
    except OSError as exc:
        raise Refusal(f"cannot create {directory}: {exc.strerror}") from None
    for copy, content in copies.items():
        try:
            with open(copy, "xb") as file:
                file.write(content)
        except OSError as exc:
            message = f"cannot write {copy}: {exc.strerror}"
            try:
                shutil.rmtree(directory)
            except OSError as removal:
                message += f", and cannot remove {directory}, which holds part of the copies: {removal.strerror}"
            raise Refusal(message) from None
    return list(copies)


def parse_github_repository(remote_url: str) -> tuple[str, str]:
    """The owner and the name of the GitHub repository at `remote_url`, the URL of origin as configured."""
    match = _GITHUB_REMOTE.fullmatch(remote_url.strip())
    if match is None:
        raise Refusal(f"origin is not a GitHub repository: {remote_url.strip()!r}")
    return match["owner"], match["repository"]


def build_picture_url(owner: str, repository: str, commit: str, path: str) -> str:
    return f"https://github.com/{owner}/{repository}/blob/{commit}/{path}?raw=true"


def compile_picture_link(owner: str, repository: str) -> re.Pattern[str]:
    """A link to a picture of the branch, as `publish` writes it, or as raw content."""
    names = f"{re.escape(owner)}/{re.escape(repository)}"
    return re.compile(
        rf"(?:github\.com/{names}/(?:blob|raw)|raw\.githubusercontent\.com/{names})/[0-9a-f]{{40}}/pr-[0-9]+/",
        re.IGNORECASE,
    )


def _run(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise Refusal(f"cannot run {command[0]}: {exc.strerror}") from None
    if completed.returncode != 0:
        raise Refusal(f"{command[0]} {command[1]}: {completed.stderr.strip() or 'failed'}")
    return completed.stdout


def _run_git(*arguments: str, input_bytes: bytes | None = None, environment: Mapping[str, str] | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments], input=input_bytes, capture_output=True, env=environment, check=False
        )
    except OSError as exc:
        raise Refusal(f"cannot run git: {exc.strerror}") from None
    if completed.returncode != 0:
        message = completed.stderr.decode(errors="replace").strip() or f"exit status {completed.returncode}"
        raise Refusal(f"git {arguments[0]}: {message}")
    return completed.stdout.decode().strip()


def _read_config_values(key: str) -> list[str]:
    """The values of `key` in git's configuration, none when it is not set."""
    try:
        completed = subprocess.run(["git", "config", "--get-all", key], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise Refusal(f"cannot run git: {exc.strerror}") from None
    # git config exits with 1 when the key is not set.
    if completed.returncode not in (0, 1):
        raise Refusal(f"git config: {completed.stderr.strip()}")
    return completed.stdout.splitlines()


def find_origin_repository() -> tuple[str, str]:
    """The owner and the name of origin's GitHub repository, which the links name and where the branch lives."""
    # git fetches from origin's first URL, and pushes to its push URLs, or to all its URLs without one: they must all
    # name one repository, whatever their case, as GitHub reads it.
    urls = _read_config_values("remote.origin.url")
    if not urls:
        raise Refusal("this checkout has no origin")
    repositories = [parse_github_repository(url) for url in urls + _read_config_values("remote.origin.pushurl")]
    if len({(owner.lower(), name.lower()) for owner, name in repositories}) > 1:
        raise Refusal("origin's URLs name several repositories: set one URL for fetching and pushing")
    return repositories[0]


def _is_branch_on_origin() -> bool:
    try:
        listed = subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin", BRANCH_REF], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise Refusal(f"cannot run git: {exc.strerror}") from None
    # ls-remote --exit-code exits with 2 when no reference matches.
    if listed.returncode == 2:
        return False
    if listed.returncode != 0:
        raise Refusal(f"git ls-remote: {listed.stderr.strip()}")
    return True


def _fetch_branch() -> str | None:
    """The tip of the branch on origin, fetched, or None while the branch does not exist."""
    if not _is_branch_on_origin():
        return None
    _run_git("fetch", "--quiet", "--no-tags", "origin", f"+{BRANCH_REF}:{FETCHED_REF}")
    return _run_git("rev-parse", "--verify", f"{FETCHED_REF}^{{commit}}")


def _commit(parent: str | None, number: int, pictures: Mapping[str, bytes]) -> str:
    """A commit on `parent` that adds `pictures` under `pr-<number>/`, built in an index of its own."""
    with tempfile.TemporaryDirectory(prefix="pr-screenshots-") as directory:
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
            raise Refusal(f"two pictures are named {path.name}")
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
        raise Refusal(f"git push failed {PUSH_ATTEMPTS} times, the last with: {failure}")
    images = [
        f"![{Path(name).stem}]({build_picture_url(owner, repository, commit, f'pr-{number}/{name}')})"
        for name in pictures
    ]
    return images, _measure_branch_bytes(commit)


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
        raise Refusal(f"gh pr list printed no JSON: {exc}") from None
    # Anything but a list of pull requests would read as "no pull request links a picture", and the deletion go ahead.
    if not isinstance(pull_requests, list) or not all(isinstance(each, dict) for each in pull_requests):
        raise Refusal("gh pr list printed no list of pull requests")
    link = compile_picture_link(owner, repository)
    return sorted(
        int(pull_request["number"])
        for pull_request in pull_requests
        if link.search(str(pull_request.get("body") or ""))
    )


def run_publish(number: int, pictures: Sequence[Path]) -> int:
    images, branch_bytes = publish(number, pictures)
    print("\n".join(images))
    if branch_bytes > WARN_ABOVE_BYTES:
        print(
            f"warning: the {BRANCH} branch weighs {branch_bytes // (1024 * 1024)} MB: the maintainer cleans it with "
            "/clean-pr-screenshots",
            file=sys.stderr,
        )
    return 0


def run_strip(directory: Path, pictures: Sequence[Path]) -> int:
    for copy in strip(directory, pictures):
        print(copy)
    return 0


def run_clean(delete: bool) -> int:
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
    if not delete:
        print(f"Nothing was deleted: run again with --delete to delete the {BRANCH} branch on origin.")
        return 0
    _run(["git", "push", "--quiet", "origin", "--delete", BRANCH_REF])
    # The copy that a publication fetched, if this checkout has one.
    subprocess.run(["git", "update-ref", "-d", FETCHED_REF], capture_output=True, check=False)
    print(f"Deleted the {BRANCH} branch on origin.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Publishes the screenshots of pull requests on the {BRANCH} branch.")
    commands = parser.add_subparsers(dest="command", required=True)
    publishing = commands.add_parser("publish", help="publish pictures for the description of a pull request")
    publishing.add_argument("number", type=int, help="the number of the pull request")
    publishing.add_argument("pictures", type=Path, nargs="+", help="PNG files")
    stripping = commands.add_parser("strip", help="copy pictures with the chunks of their image only")
    stripping.add_argument("directory", type=Path, help="a path that does not exist yet, created for the copies")
    stripping.add_argument("pictures", type=Path, nargs="+", help="PNG files, left as they are")
    cleaning = commands.add_parser("clean", help=f"list what deleting the {BRANCH} branch breaks, and delete it")
    cleaning.add_argument("--delete", action="store_true", help="delete the branch on origin")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "publish":
            if arguments.number <= 0:
                publishing.error("the number of a pull request is positive")
            return run_publish(arguments.number, arguments.pictures)
        if arguments.command == "strip":
            return run_strip(arguments.directory, arguments.pictures)
        return run_clean(arguments.delete)
    except Refusal as refusal:
        print(f"error: {refusal}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
