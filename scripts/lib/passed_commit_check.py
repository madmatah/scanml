"""The commits that `scripts/check.sh --last-commit` skips: those that already passed it, and fixups.

Standard library and git only:
    python3 scripts/lib/passed_commit_check.py check ROOT
    python3 scripts/lib/passed_commit_check.py record ROOT KEY clean|dirty

`check` exits 0, after saying why, when the commit is skipped, and 3, printing its key and `clean` or `dirty` on one
line, when its areas must run; any other status is an error, on which the caller must not skip.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

_MUST_CHECK_STATUS = 3
_RECORD_NAME = "passed-commit-check"
_FIXUP_PREFIXES = ("fixup! ", "amend! ", "squash! ")
_ROOT_PARENT = "root"
_CLEAN = "clean"
_DIRTY = "dirty"
_OBJECT_NAME = r"[0-9a-f]{40}(?:[0-9a-f]{24})?"
_KEY_PATTERN = re.compile(rf"{_OBJECT_NAME} (?:{_OBJECT_NAME}|{_ROOT_PARENT})")


def _run_git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], stdout=subprocess.PIPE, text=True, check=True
    ).stdout.strip()


def _read_commit_key(root: Path) -> str:
    tree = _run_git(root, "rev-parse", "--verify", "HEAD^{tree}")
    parent_tree_lookup = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--quiet", "--verify", "HEAD~1^{tree}"],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    parent_tree = parent_tree_lookup.stdout.strip() if parent_tree_lookup.returncode == 0 else _ROOT_PARENT
    return f"{tree} {parent_tree}"


def _has_hidden_changes(root: Path) -> bool:
    # git status does not compare a file marked assume-unchanged (a lowercase tag) or skip-worktree (S) with HEAD.
    return any(re.match(r"[a-zS] ", line) for line in _run_git(root, "ls-files", "-v").splitlines())


def _is_working_tree_clean(root: Path) -> bool:
    return _run_git(root, "status", "--porcelain", "--untracked-files=normal") == "" and not _has_hidden_changes(root)


def find_record(root: Path) -> Path:
    return Path(_run_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")) / _RECORD_NAME


def _is_recorded(record: Path, key: str) -> bool:
    try:
        return key in record.read_text().splitlines()
    except FileNotFoundError:
        return False


def _check(root: Path) -> int:
    # The fold puts a fixup into its commit, which the areas then check: a check of the fixup alone would be lost.
    if _run_git(root, "log", "-1", "--format=%s").startswith(_FIXUP_PREFIXES):
        print("Skipped: a fixup is checked once folded into its commit.")
        return 0
    key = _read_commit_key(root)
    is_clean = _is_working_tree_clean(root)
    if is_clean and _is_recorded(find_record(root), key):
        print("Skipped: this commit already passed the check.")
        return 0
    print(key, _CLEAN if is_clean else _DIRTY)
    return _MUST_CHECK_STATUS


def _record(root: Path, key: str, tree_state: str) -> int:
    if tree_state == _DIRTY:
        print("Not recorded: the working tree has changes or untracked files.")
        return 0
    with find_record(root).open("a") as record_file:
        record_file.write(f"{key}\n")
    return 0


def _parse_key(text: str) -> str:
    if _KEY_PATTERN.fullmatch(text) is None:
        raise argparse.ArgumentTypeError(f"not a tree and its parent's tree, or {_ROOT_PARENT}: {text!r}")
    return text


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skips, or records, a commit that passed check.sh --last-commit.")
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check", help="whether the last commit may be skipped")
    check_parser.add_argument("root", type=Path)
    record_parser = commands.add_parser("record", help="records a commit whose areas passed")
    record_parser.add_argument("root", type=Path)
    record_parser.add_argument("key", type=_parse_key)
    record_parser.add_argument("tree_state", choices=(_CLEAN, _DIRTY))
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "check":
            return _check(arguments.root)
        return _record(arguments.root, arguments.key, arguments.tree_state)
    except subprocess.CalledProcessError:
        # git printed its error.
        return 1


if __name__ == "__main__":
    sys.exit(main())
