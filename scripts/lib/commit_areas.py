"""The areas of the gate that the last commit touches, for `scripts/check.sh --last-commit`.

A commit is checked on the areas that read the files it changes: an area that reads none of them gives the result it
gave on the commit before. The integration tests of the scripts run for the scripts they run, and not for the modules
that unit tests cover alone (`CLAUDE.md` > Workflow, "Commits"). A path that no rule below knows reaches every area, so
that a file nobody thought of is checked rather than skipped.

Standard library and git only:
    python3 scripts/lib/commit_areas.py ROOT
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

GATE_AREAS = ("lint", "scripts", "web", "server", "ocr", "android", "integration")
# A narrower prefix comes before the wider one it sits in, since the first that matches wins. A prefix is an fnmatch
# pattern: its `*` matches any characters, `/` included.
PATH_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # The scripts that skills keep: the lint area checks them, and their tests are integration tests.
    (".claude/skills/*/scripts/", ("lint", "integration")),
    (".claude/", ()),
    ("docs/", ()),
    ("CLAUDE.md", ()),
    ("README.md", ()),
    ("CREDITS.md", ()),
    ("CHANGELOG.md", ()),
    ("LICENSE", ()),
    (".github/pull_request_template.md", ()),
    # scripts/tests/test_workflows.py reads the workflows.
    (".github/workflows/", ("lint", "scripts")),
    ("android/", ("android",)),
    ("ocr/", ("lint", "ocr")),
    ("server/scanmylib/web/", ("lint", "web", "server")),
    ("server/", ("lint", "server")),
    # check.sh runs every area, and every area runs with common.sh.
    ("scripts/check.sh", GATE_AREAS),
    ("scripts/lib/common.sh", GATE_AREAS),
    # The android area runs build-apk.sh, which runs stack.py and version.py.
    ("scripts/build-apk.sh", ("lint", "scripts", "android", "integration")),
    ("scripts/lib/stack.py", ("lint", "scripts", "android", "integration")),
    ("scripts/lib/version.py", ("lint", "scripts", "android", "integration")),
    ("scripts/lint/", ("lint",)),
    ("scripts/tests/", ("lint", "scripts")),
    ("scripts/integration_tests/", ("lint", "integration")),
    # No integration test runs them.
    ("scripts/release.py", ("lint", "scripts")),
    ("scripts/vendor-katex.sh", ("lint",)),
    # The integration tests run the other scripts and their modules.
    ("scripts/", ("lint", "scripts", "integration")),
    ("ruff.toml", ("lint",)),
    ("mypy.ini", ("lint",)),
    (".shellcheckrc", ("lint",)),
)


def find_rule(path: str) -> tuple[str, tuple[str, ...]] | None:
    for prefix, areas in PATH_RULES:
        if path == prefix or (prefix.endswith("/") and fnmatch.fnmatchcase(path, f"{prefix}*")):
            return prefix, areas
    return None


def _find_areas_reached(path: str) -> tuple[str, ...]:
    rule = find_rule(path)
    if rule is None:
        return GATE_AREAS
    # The lint area checks every shell script of the repository, wherever it lies.
    shell_lint = ("lint",) if path.endswith(".sh") else ()
    return (*shell_lint, *rule[1])


def list_areas_touched(paths: Iterable[str]) -> list[str]:
    reached = {area for path in paths for area in _find_areas_reached(path)}
    return [area for area in GATE_AREAS if area in reached]


def _list_paths_of_last_commit(root: Path) -> list[str] | None:
    parent = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", "HEAD^"], capture_output=True, check=False
    )
    if parent.returncode != 0:
        return None
    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "--no-renames", "-z", "HEAD^", "HEAD"],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    return [path for path in diff.stdout.split("\0") if path]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prints the areas of the gate that the last commit touches.")
    parser.add_argument("root", type=Path)
    arguments = parser.parse_args(argv)
    try:
        paths = _list_paths_of_last_commit(arguments.root)
    except subprocess.CalledProcessError:
        # git printed its error.
        return 1
    for area in GATE_AREAS if paths is None else list_areas_touched(paths):
        print(area)
    return 0


if __name__ == "__main__":
    sys.exit(main())
