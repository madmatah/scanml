"""Test support of the screenshot scripts of the skills: a bare origin that the scripts take for a GitHub repository,
a clone of it, PNG files and a stand-in for the GitHub CLI.
"""

from __future__ import annotations

import os
import struct
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PUBLISH = REPO / ".claude" / "skills" / "pull-request" / "scripts" / "publish_screenshots.py"
CLEAN = REPO / ".claude" / "skills" / "clean-pr-screenshots" / "scripts" / "clean_screenshots.py"
OWNER = "example"
REPOSITORY = "scanmylib"
#: origin's URL as the clone's configuration holds it, which git rewrites to the bare repository.
GITHUB_URL = f"git@github.com:{OWNER}/{REPOSITORY}.git"
BRANCH = "refs/heads/pr-screenshots"
FETCHED_REF = "refs/remotes/origin/pr-screenshots"


def make_png(*extra_chunks: tuple[bytes, bytes], shade: int = 0) -> bytes:
    """A PNG file of one gray pixel of `shade`, with `extra_chunks` (type, data) before its pixels."""

    def build_chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    chunks = [build_chunk(b"IHDR", header), *(build_chunk(*extra) for extra in extra_chunks)]
    chunks += [build_chunk(b"IDAT", zlib.compress(bytes([0, shade]))), build_chunk(b"IEND", b"")]
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


@dataclass(frozen=True)
class Run:
    returncode: int
    stdout: str
    stderr: str


class Remote:
    """A bare origin, and a clone whose origin is `GITHUB_URL`, rewritten to it, with a stand-in for `gh`.

    The stand-in logs its arguments to `gh.log` and prints `gh.json`, or fails when `gh.json` is missing.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.origin = directory / "origin.git"
        self.clone = directory / "clone"
        self.gh_log = directory / "gh.log"
        self.gh_answer = directory / "gh.json"
        home = directory / "home"
        tools = directory / "bin"
        home.mkdir()
        tools.mkdir()
        (tools / "gh").write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{self.gh_log}"\n'
            f'[ -f "{self.gh_answer}" ] || {{ echo "gh: not logged in" >&2; exit 1; }}\ncat "{self.gh_answer}"\n'
        )
        (tools / "gh").chmod(0o755)
        # The tests' own git: nothing from the caller's configuration, or from a `git rebase --exec` that runs them.
        inherited = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
        self.environment = {
            **inherited,
            "PATH": f"{tools}{os.pathsep}{os.environ.get('PATH', '')}",
            "HOME": str(home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            # Local repositories only: a URL that no insteadOf rule rewrites fails rather than reaching the network.
            "GIT_ALLOW_PROTOCOL": "file",
        }
        self.run_git("init", "--quiet", "--bare", str(self.origin))
        self.run_git("init", "--quiet", str(self.clone))
        self.run_git("-C", str(self.clone), "remote", "add", "origin", GITHUB_URL)
        self.run_git("-C", str(self.clone), "config", f"url.{self.origin}.insteadOf", GITHUB_URL)

    def run_git(self, *arguments: str, input_bytes: bytes | None = None) -> str:
        completed = subprocess.run(
            ["git", *arguments], input=input_bytes, capture_output=True, env=self.environment, check=True
        )
        return completed.stdout.decode().strip()

    def run_origin_git(self, *arguments: str, input_bytes: bytes | None = None) -> str:
        return self.run_git("--git-dir", str(self.origin), *arguments, input_bytes=input_bytes)

    def run(self, script: Path, *arguments: str) -> Run:
        completed = subprocess.run(
            ["python3", str(script), *arguments],
            cwd=self.clone,
            capture_output=True,
            text=True,
            env=self.environment,
            check=False,
        )
        return Run(completed.returncode, completed.stdout, completed.stderr)

    def write_picture(self, name: str, content: bytes) -> Path:
        """A file named `name` holding `content`, outside the clone, as a test's output would be."""
        path = self.directory / "pictures" / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        return path

    def read_branch_tip(self) -> str | None:
        completed = subprocess.run(
            ["git", "--git-dir", str(self.origin), "rev-parse", "--verify", "--quiet", BRANCH],
            capture_output=True,
            text=True,
            env=self.environment,
            check=False,
        )
        return completed.stdout.strip() or None

    def read_files(self, commit: str) -> dict[str, bytes]:
        """The files of `commit` on origin, by path."""
        paths = self.run_origin_git("ls-tree", "-r", "--name-only", commit).splitlines()
        return {path: self.read_blob(commit, path) for path in paths}

    def read_blob(self, commit: str, path: str) -> bytes:
        return subprocess.run(
            ["git", "--git-dir", str(self.origin), "show", f"{commit}:{path}"],
            capture_output=True,
            env=self.environment,
            check=True,
        ).stdout

    def read_parents(self, commit: str) -> list[str]:
        return self.run_origin_git("rev-list", "--parents", "--max-count=1", commit).split()[1:]

    def make_fork(self, url: str) -> Path:
        """A bare repository that `url` reaches from the clone: another repository than origin."""
        fork = self.directory / "fork.git"
        self.run_git("init", "--quiet", "--bare", str(fork))
        self.run_git("-C", str(self.clone), "config", f"url.{fork}.insteadOf", url)
        return fork

    def commit_on_origin(self, files: dict[str, bytes], parent: str | None = None) -> str:
        """A commit of `files` written straight into origin, on no branch: another publication, for instance."""
        index = self.directory / "index"
        environment = {**self.environment, "GIT_INDEX_FILE": str(index)}
        git_dir = ["git", "--git-dir", str(self.origin)]
        subprocess.run([*git_dir, "read-tree", "--empty"], env=environment, check=True)
        for path, content in files.items():
            blob = self.run_origin_git("hash-object", "-w", "--stdin", input_bytes=content)
            subprocess.run(
                [*git_dir, "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}"], env=environment, check=True
            )
        tree = subprocess.run(
            [*git_dir, "write-tree"], env=environment, capture_output=True, text=True, check=True
        ).stdout.strip()
        index.unlink()
        parents = [] if parent is None else ["-p", parent]
        return self.run_origin_git("commit-tree", tree, *parents, "-m", "Another publication")
