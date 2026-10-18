#!/usr/bin/env python3
"""The version of a build of ScanMyLib, for the scripts of scripts/ (standard library only).

A release is the version in VERSION, MAJOR.MINOR.PATCH with minor and patch below 100, tagged
vMAJOR.MINOR.PATCH. Its Android versionCode is major * 10000 + minor * 100 + patch, so that every
release installs over the previous one.

Anything else is a development build (the development stack, the dev app, CI). Its version comes
from git: a SemVer pre-release of the next patch, since SemVer orders 0.2.3-dev before 0.2.3.

    MAJOR.MINOR.<PATCH + 1>-dev.<commits since the tag vVERSION>+g<commit>[.dirty]

For example 0.2.4-dev.27+g1a2b3c4d5e6f is 27 commits after v0.2.3, at commit 1a2b3c4d5e6f;
".dirty" says that tracked files differ from that commit. Without the tag (a shallow clone), the
count is left out; outside a git checkout, the build metadata too. The dev app's versionCode is
the time of the build, in minutes since 2026-01-01 UTC, and above the versionCode of the APK
already published (its scanmylib.json), so that each build installs over the previous one,
whichever branch it comes from (Android refuses a lower versionCode).

Usage: version.py release ROOT                   prints "<version> <versionCode>" of the release
                                                 in ROOT/VERSION
       version.py dev ROOT [PUBLISHED_METADATA]  prints "<version> <versionCode>" of a development
                                                 build of ROOT, its versionCode above the one in
                                                 PUBLISHED_METADATA (scanmylib.json), if any
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_RELEASE = re.compile(r"(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]?)\.(0|[1-9][0-9]?)")
_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_COUNT = re.compile(r"[0-9]{1,9}")

#: The dev app's versionCode counts the minutes since this time.
DEV_CODE_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
#: The largest versionCode Android accepts.
MAX_VERSION_CODE = 2_100_000_000

Release = tuple[int, int, int]


def parse_release(text: str) -> Release:
    """The version MAJOR.MINOR.PATCH of `text` (VERSION's content); ValueError if it is not one."""
    match = _RELEASE.fullmatch(text.strip())
    if not match:
        raise ValueError(f"VERSION must be MAJOR.MINOR.PATCH, minor and patch below 100, not {text.strip()!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def read_release(root: Path) -> Release:
    """The release in `root`/VERSION."""
    return parse_release((root / "VERSION").read_text(encoding="utf-8"))


def format_release(release: Release) -> str:
    return ".".join(str(part) for part in release)


def release_code(release: Release) -> int:
    """The Android versionCode of a release: major * 10000 + minor * 100 + patch."""
    major, minor, patch = release
    return major * 10000 + minor * 100 + patch


def _git(root: Path, *args: str) -> str | None:
    """The output of git in `root`, or None if git fails or is missing."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def dev_version(root: Path, release: Release) -> str:
    """The version of a development build of the checkout `root`, whose last release is `release`."""
    major, minor, patch = release
    version = f"{major}.{minor}.{patch + 1}-dev"
    commit = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    if commit is None or not _COMMIT.fullmatch(commit):
        return version
    tag = f"refs/tags/v{format_release(release)}"
    if _git(root, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}") is not None:
        count = _git(root, "rev-list", "--count", f"{tag}..{commit}")
        if count is not None and _COUNT.fullmatch(count):
            version += f".{int(count)}"
    metadata = f"g{commit[:12]}"
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        metadata += ".dirty"
    return f"{version}+{metadata}"


def dev_code(now: datetime, published: int | None = None) -> int:
    """The dev app's versionCode at `now`: the minutes since DEV_CODE_EPOCH, and above the
    versionCode `published` already, if any (two builds in the same minute)."""
    minutes = int((now - DEV_CODE_EPOCH).total_seconds() // 60)
    if not 0 < minutes <= MAX_VERSION_CODE:
        raise ValueError(f"the clock says {now.isoformat()}: no dev versionCode then")
    if published is not None and published >= minutes:
        minutes = published + 1
    if minutes > MAX_VERSION_CODE:
        raise ValueError(f"no versionCode above {published} is left")
    return minutes


def published_code(metadata: Path) -> int | None:
    """The versionCode in the metadata of a published APK (scanmylib.json); None if there is none
    that holds up."""
    try:
        code = json.loads(metadata.read_text(encoding="utf-8")).get("version_code")
    except (OSError, UnicodeDecodeError, ValueError, AttributeError, RecursionError):
        return None
    if isinstance(code, bool) or not isinstance(code, int) or not 0 < code <= MAX_VERSION_CODE:
        return None
    return code


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not (args[:1] == ["release"] and len(args) == 2 or args[:1] == ["dev"] and len(args) in (2, 3)):
        print(__doc__[__doc__.index("Usage:") :].rstrip(), file=sys.stderr)
        return 2
    root = Path(args[1])
    try:
        release = read_release(root)
        if args[0] == "release":
            print(format_release(release), release_code(release))
        else:
            published = published_code(Path(args[2])) if len(args) == 3 else None
            print(dev_version(root, release), dev_code(datetime.now(timezone.utc), published))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
