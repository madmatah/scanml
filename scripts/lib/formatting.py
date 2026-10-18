#!/usr/bin/env python3
"""What scripts/check.sh hands to its formatters and linters: the shell scripts to check, and the copy that --fix lets
the formatters write (standard library only).

The formatters write only to a copy of the tracked files they format, so that nothing they create, and no link they
make, reaches the checkout, where the host would run or read it, and so that they never touch a file they do not format,
such as a vendored file, whose change git diff would not let a reader judge. bring-back then writes back the files whose
content they changed, or nothing at all: when a copied file is no longer a file, when a file they changed was also
changed in the checkout meanwhile (an edit would be lost), when it cannot be written, when it holds or would hold a
character a terminal does not show (such as a control character other than a tab or a line end the file already used, a
format character or a byte that is not UTF-8), when they added a character outside ASCII, which may look like another,
when they wrote a line far longer than the file's, which could push text out of sight, or when they grew it past twice
its size and 64 KiB; a write that fails midway says which files came back before it. git diff then shows everything they
changed, so check-hidden refuses the files it would not show, marked assume-unchanged or skip-worktree. Only the
directories of TREE may be handed to the formatters: DIGESTS is what bring-back trusts.

Usage: formatting.py shell-scripts ROOT
           prints the shell scripts of ROOT's working tree, tracked or not, each followed by a NUL
       formatting.py check-hidden ROOT DIRECTORY...
           fails if git diff would not show a change to a tracked file of those directories
       formatting.py make-copy ROOT TREE DIGESTS PATHSPEC...
           copies the files git tracks that match those pathspecs of ROOT to TREE, records their digests and sizes in
           DIGESTS, and prints the shell scripts among them, each followed by a NUL
       formatting.py bring-back ROOT TREE DIGESTS
           writes back to ROOT the files the formatters changed in TREE, or nothing, unless a write fails midway
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

# A byte that is not UTF-8 is read as a surrogate (Cs).
_HIDING_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
# Unicode's default-ignorable code points, which unicodedata does not list and which render as nothing (some of them
# letters or marks, valid in an identifier), and the Braille blank, which renders as blank space.
_INVISIBLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x2800, 0x2800),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
# Formatting barely changes a file's size, and no reader judges megabytes of diff.
_GROWTH_ALLOWANCE_BYTES = 64 * 1024
# A formatter writes no line longer than the file's longest beyond its width; a far longer one could push text out of
# sight of someone reading git diff.
_LINE_LENGTH_ALLOWANCE = 1000


class FormattingRefused(RuntimeError):
    pass


class CopiedFile(TypedDict):
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class CopyListing:
    shell_scripts: list[str]
    left_out_files: list[str]


def _list_git_entries(root: Path, *arguments: str) -> list[str]:
    git_run = subprocess.run(["git", "-C", str(root), "ls-files", "-z", *arguments], stdout=subprocess.PIPE, check=True)
    return list(dict.fromkeys(os.fsdecode(entry) for entry in git_run.stdout.split(b"\0") if entry))


def _is_plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _is_plain_file_reached_without_links(root: Path, path: str) -> bool:
    return _is_plain_file(root / path) and (root / path).resolve() == root.resolve() / path


def _hash_file(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="surrogateescape")


def _is_hiding(character: str) -> bool:
    code_point = ord(character)
    return character != "\t" and (
        unicodedata.category(character) in _HIDING_CATEGORIES
        or any(first <= code_point <= last for first, last in _INVISIBLE_RANGES)
    )


def _describe_character(character: str) -> str:
    code_point = ord(character)
    # A byte that is not UTF-8 is read as a surrogate from U+DC80 to U+DCFF.
    if 0xDC80 <= code_point <= 0xDCFF:
        return f"byte 0x{code_point - 0xDC00:02X}"
    return f"U+{code_point:04X}"


def _find_hiding_character(text: str, *, uses_carriage_return_line_ends: bool) -> str | None:
    if uses_carriage_return_line_ends:
        text = text.replace("\r\n", "\n")
    for line_number, line in enumerate(text.split("\n"), start=1):
        for character in line:
            if _is_hiding(character):
                return f"line {line_number}: {_describe_character(character)}"
    return None


def _measure_longest_line(text: str) -> int:
    return max(len(line) for line in text.split("\n"))


def _count_characters_outside_ascii(text: str) -> Counter[str]:
    return Counter(character for character in text if not character.isascii())


def _can_be_replaced(path: Path) -> bool:
    return os.access(path, os.W_OK) and os.access(path.parent, os.W_OK | os.X_OK)


def _replace_file(source: Path, target: Path) -> None:
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as temporary_file:
        temporary_path = Path(temporary_file.name)
    try:
        shutil.copyfile(source, temporary_path)
        shutil.copymode(target, temporary_path)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def list_shell_scripts(root: Path) -> list[str]:
    paths = _list_git_entries(root, "--cached", "--others", "--exclude-standard", "--", "*.sh")
    return [path for path in paths if (root / path).is_file()]


def list_hidden_files(root: Path, directories: list[str]) -> list[str]:
    # The tag of `ls-files -v`: lowercase for assume-unchanged, S for skip-worktree.
    tagged_paths = _list_git_entries(root, "-v", "--", *directories)
    return [tagged_path[2:] for tagged_path in tagged_paths if tagged_path[0].islower() or tagged_path[0] == "S"]


def make_copy(root: Path, tree: Path, digests_file: Path, pathspecs: list[str]) -> CopyListing:
    copied_files: dict[str, CopiedFile] = {}
    paths_behind_links = []
    for path in _list_git_entries(root, "--", *pathspecs):
        if not _is_plain_file_reached_without_links(root, path):
            if (root / path).exists():
                paths_behind_links.append(path)
            continue
        file_copy = tree / path
        file_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / path, file_copy)
        copied_files[path] = {"sha256": _hash_file(file_copy), "size_bytes": file_copy.stat().st_size}
    digests_file.write_text(json.dumps(copied_files), encoding="utf-8")
    return CopyListing(
        shell_scripts=[path for path in copied_files if path.endswith(".sh")],
        left_out_files=_list_git_entries(root, "--others", "--exclude-standard", "--", *pathspecs) + paths_behind_links,
    )


def _find_copy_problem(tree: Path, path: str, copied_file: CopiedFile) -> str | None:
    if not _is_plain_file_reached_without_links(tree, path):
        return f"a formatter turned {path} into something other than a file"
    if (tree / path).stat().st_size > 2 * copied_file["size_bytes"] + _GROWTH_ALLOWANCE_BYTES:
        allowance_kib = _GROWTH_ALLOWANCE_BYTES // 1024
        return f"a formatter grew {path} past twice its size and {allowance_kib} KiB, far more than formatting does"
    return None


def _find_change_problem(root: Path, tree: Path, path: str, copied_file: CopiedFile) -> str | None:
    checkout_file = root / path
    if not _is_plain_file_reached_without_links(root, path) or _hash_file(checkout_file) != copied_file["sha256"]:
        return f"{path} changed in the checkout while the formatters ran"
    checkout_text, formatted_text = _read_text(checkout_file), _read_text(tree / path)
    uses_carriage_return_line_ends = "\r\n" in checkout_text
    checkout_place = _find_hiding_character(
        checkout_text, uses_carriage_return_line_ends=uses_carriage_return_line_ends
    )
    if checkout_place:
        return (
            f"{path} holds a character a terminal does not show ({checkout_place}): write it as an escape, or remove "
            "it (.claude/rules/conventions.md > Characters a reader cannot see)"
        )
    formatted_place = _find_hiding_character(
        formatted_text, uses_carriage_return_line_ends=uses_carriage_return_line_ends
    )
    if formatted_place:
        return f"a formatter added to {path} a character a terminal does not show ({formatted_place})"
    if _count_characters_outside_ascii(formatted_text) - _count_characters_outside_ascii(checkout_text):
        return f"a formatter added to {path} characters outside ASCII, which may look like others"
    longest_line = _measure_longest_line(formatted_text)
    if longest_line > max(2 * _measure_longest_line(checkout_text), _LINE_LENGTH_ALLOWANCE):
        return f"a formatter wrote in {path} a line of {longest_line} characters, far longer than the file's"
    if not _can_be_replaced(checkout_file):
        return f"{path} cannot be written"
    return None


def bring_back(root: Path, tree: Path, digests_file: Path) -> None:
    copied_files: dict[str, CopiedFile] = json.loads(digests_file.read_text(encoding="utf-8"))
    problems, changed_paths = [], []
    for path, copied_file in copied_files.items():
        problem = _find_copy_problem(tree, path, copied_file)
        if problem is None:
            if _hash_file(tree / path) == copied_file["sha256"]:
                continue
            problem = _find_change_problem(root, tree, path, copied_file)
        if problem is None:
            changed_paths.append(path)
        else:
            problems.append(problem)
    if problems:
        raise FormattingRefused("nothing was brought back: " + "; ".join(problems))
    brought_back_paths: list[str] = []
    for path in changed_paths:
        try:
            _replace_file(tree / path, root / path)
        except OSError as exc:
            raise FormattingRefused(
                f"writing {path} failed ({exc}); brought back before it: {', '.join(brought_back_paths) or 'none'}"
            ) from exc
        brought_back_paths.append(path)


def _print_paths(paths: list[str]) -> None:
    sys.stdout.buffer.write(b"".join(os.fsencode(path) + b"\0" for path in paths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    shell_scripts_command = commands.add_parser("shell-scripts", help="the shell scripts of a working tree")
    shell_scripts_command.add_argument("root", type=Path)
    check_hidden_command = commands.add_parser("check-hidden", help="refuse the files git diff would not show")
    check_hidden_command.add_argument("root", type=Path)
    check_hidden_command.add_argument("directories", nargs="+")
    make_copy_command = commands.add_parser("make-copy", help="copy the files git tracks that match pathspecs")
    bring_back_command = commands.add_parser("bring-back", help="write back the files the formatters changed")
    for command in (make_copy_command, bring_back_command):
        command.add_argument("root", type=Path)
        command.add_argument("tree", type=Path)
        command.add_argument("digests_file", type=Path)
    make_copy_command.add_argument("pathspecs", nargs="+")
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "shell-scripts":
            _print_paths(list_shell_scripts(arguments.root))
        elif arguments.command == "check-hidden":
            hidden_files = list_hidden_files(arguments.root, arguments.directories)
            if hidden_files:
                raise FormattingRefused(
                    "git diff would not show what the formatters change in these files, marked assume-unchanged or "
                    f"skip-worktree: {', '.join(hidden_files)} "
                    "(git update-index --no-assume-unchanged --no-skip-worktree FILE)"
                )
        elif arguments.command == "make-copy":
            listing = make_copy(arguments.root, arguments.tree, arguments.digests_file, arguments.pathspecs)
            if listing.left_out_files:
                print(
                    "left out, as git does not track them or they lie behind a link (git add a new file to format it): "
                    f"{', '.join(listing.left_out_files)}",
                    file=sys.stderr,
                )
            _print_paths(listing.shell_scripts)
        else:
            bring_back(arguments.root, arguments.tree, arguments.digests_file)
    except FormattingRefused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"error: {' '.join(exc.cmd)} failed (see git's message above)", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
