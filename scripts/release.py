#!/usr/bin/env python3
"""Prepares the next release of ScanMyLib, from the commits since the last one.

The last release is VERSION, tagged vVERSION. The commits since that tag follow Conventional
Commits (CLAUDE.md, "Commits"), which give the next version as SemVer reads them:
  - a breaking change ("type!: ..." or a "BREAKING CHANGE:" footer): the next major version, or
    the next minor one while the major version is 0;
  - else a feature ("feat"): the next minor version;
  - else (fixes and any other change): the next patch.
They also give the draft of the release's section of CHANGELOG.md (Keep a Changelog): features
under "Added", fixes under "Fixed", breaking changes under "Changed", marked as such. The other
commits (refactor, test, build, ci, docs, chore, and those that do not follow Conventional
Commits) are left out and listed, so that the release pull request adds the ones that matter to
the readers; it is where the section is edited.

Without --commit, it prints the next version, why, the section and the commits left out, and
changes nothing. With --commit, on the release's own branch, it writes VERSION and the section, and
commits them as "chore(release): X.Y.Z" with the commit the notes were written on (trailer
"Release-Base: <commit>"); it prints the description of the release pull request: what merging it
does, then the notes it publishes. --description prints it again, from the section as committed,
once the notes are edited.

If VERSION has no tag yet because its release cannot be published (see --to-publish), it is
completed instead, with another "chore(release): X.Y.Z". If its notes miss features, fixes or
breaking changes merged after they were written, the commits merged since are drafted, and --commit
adds them to the release's section. If its section has no entry, or is missing, the section is
drafted again from the commits since the last release, and --commit writes it in place. Commits
that only edit CHANGELOG.md are left out.

With --to-publish, .github/workflows/release.yml asks which release a commit of main publishes,
and on which commit: the version of VERSION if it is not tagged yet, on its latest release commit
followed by the commits right after it that only edit CHANGELOG.md (the notes edited in the release
pull request; later commits belong to the next release); none if VERSION is tagged on another
commit. It refuses when features, fixes or breaking changes were merged between the commit the
notes were written on and that release commit (the notes miss them), or when the release's section
is empty: the release is then to be completed. It prints the version and the commit to tag, and
writes the release's section of the changelog, its notes.

It refuses commits still to fold (fixup!, amend!, squash!), and names the ones that do not follow
Conventional Commits. Run it in a checkout; standard library only.

Usage: scripts/release.py [--ref REF] [--bump major|minor|patch] [--allow-unfolded]
                          [--version-only | --notes-only | --commit | --description | --to-publish NOTES]
  --ref REF         the commit to release (default: HEAD)
  --bump LEVEL      another increment than the commits give, e.g. for a breaking change they do
                    not mark as such
  --allow-unfolded  release commits still to fold that reached main anyway (main's history is
                    never rewritten), as other changes
  --version-only    print the next version only
  --notes-only      print the release's section of the changelog only, without its heading
  --commit          write VERSION and CHANGELOG.md and commit them (HEAD, on a branch other than
                    main); prints the description of the release pull request
  --description     print the description of the release pull request at REF, from its section of
                    CHANGELOG.md as committed
  --to-publish NOTES  the release REF publishes, if any (its version is printed, its notes written
                    to the file NOTES), for .github/workflows/release.yml
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from version import Release, format_release, parse_release  # noqa: E402

_SUBJECT = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9-]+)\))?(?P<breaking>!)?: (?P<summary>\S.*)")
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
_TO_FOLD = re.compile(r"(fixup|amend|squash)! ")
LEVELS = ("major", "minor", "patch")
#: The kinds of changes, and how the summary counts them.
KINDS = {
    "breaking": ("breaking change", "breaking changes"), "feature": ("feature", "features"),
    "fix": ("fix", "fixes"), "other": ("other change", "other changes"),
}
#: The sections of the changelog the commits give, in Keep a Changelog's order; Deprecated,
#: Removed and Security are written by hand.
SECTIONS = ("Added", "Changed", "Fixed")
#: Keep a Changelog's order of the subsections of a release.
ORDER = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
#: How a commit's scope reads in the changelog; another scope reads capitalized.
SCOPES = {"android": "App", "server": "Server", "web": "Web UI", "ocr": "OCR", "scripts": "Scripts"}
CHANGELOG = "CHANGELOG.md"
#: The trailer of a release commit: the commit its notes were written on.
TRAILER = "Release-Base"
_TRAILER_LINE = re.compile(rf"^{TRAILER}: (?P<commit>[0-9a-f]{{40}})$", re.MULTILINE)
_UNRELEASED = "## [Unreleased]"
_UNRELEASED_LINK = re.compile(r"^\[unreleased\]: (?P<base>https://\S+)/compare/v(?P<version>\S+)\.\.\.HEAD$",
                              re.MULTILINE)


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class Change:
    """A commit, as Conventional Commits reads its message; `type` is None if it does not follow them."""

    commit: str
    subject: str
    type: str | None
    scope: str | None
    summary: str
    breaking: bool

    @classmethod
    def parse(cls, commit: str, subject: str, body: str) -> Change:
        footer = bool(_BREAKING_FOOTER.search(body))
        match = _SUBJECT.fullmatch(subject)
        if not match:
            return cls(commit, subject, None, None, subject, footer)
        return cls(commit, subject, match["type"], match["scope"], match["summary"],
                   bool(match["breaking"]) or footer)

    @property
    def kind(self) -> str:
        if self.breaking:
            return "breaking"
        return {"feat": "feature", "fix": "fix"}.get(self.type or "", "other")

    @property
    def section(self) -> str | None:
        """The section of the changelog the change is drafted in; None if it is left out."""
        if _TO_FOLD.match(self.subject):
            return None
        return {"breaking": "Changed", "feature": "Added", "fix": "Fixed"}.get(self.kind)

    def entry(self) -> str:
        if self.scope:
            text = f"{SCOPES.get(self.scope, self.scope.capitalize())}: {self.summary}"
        else:
            text = self.summary[:1].upper() + self.summary[1:]
        return f"- **Breaking:** {text}" if self.breaking else f"- {text}"


def increment(changes: list[Change], release: Release) -> str:
    """The increment the changes give after `release`: major, minor or patch."""
    if any(change.breaking for change in changes):
        return "major" if release[0] > 0 else "minor"
    if any(change.type == "feat" for change in changes):
        return "minor"
    return "patch"


def bump(release: Release, level: str) -> Release:
    """The release after `release` at `level`; ReleaseError past the limits of VERSION."""
    major, minor, patch = release
    following = {"major": (major + 1, 0, 0), "minor": (major, minor + 1, 0), "patch": (major, minor, patch + 1)}[level]
    if following[0] > 999 or following[1] > 99 or following[2] > 99:
        raise ReleaseError(f"{format_release(following)} is past what VERSION allows (minor and patch below 100): "
                           "choose another increment with --bump")
    return following


def notes(changes: list[Change]) -> str:
    """The draft of the release's section of the changelog, without its heading: one subsection per
    section, the commits in order. With nothing to draft, the commits left out go under Changed."""
    if any(change.section for change in changes):
        sections = {section: [change.entry() for change in changes if change.section == section]
                    for section in SECTIONS}
    else:
        sections = {"Changed": [change.entry() for change in changes if not _TO_FOLD.match(change.subject)]}
    lines = []
    for section, entries in sections.items():
        if entries:
            lines += [f"### {section}", "", *entries, ""]
    return "\n".join(lines).rstrip() + "\n"


def left_out(changes: list[Change]) -> list[str]:
    """The commits the draft leaves out, one line each."""
    if not any(change.section for change in changes):
        return [f"- `{change.commit[:12]}` {change.subject}" for change in changes if _TO_FOLD.match(change.subject)]
    return [f"- `{change.commit[:12]}` {change.subject}" for change in changes if not change.section]


def summary(changes: list[Change]) -> str:
    counts = {kind: sum(change.kind == kind for change in changes) for kind in KINDS}
    return ", ".join(f"{count} {KINDS[kind][count > 1]}" for kind, count in counts.items() if count)


def _section_lines(lines: list[str], version: str) -> tuple[int, int]:
    """Where the section of `version` starts (its heading) and ends in the changelog's lines."""
    heading = f"## [{version}]"
    start = next((i for i, line in enumerate(lines) if line == heading or line.startswith(f"{heading} ")), None)
    if start is None:
        raise ReleaseError(f"{CHANGELOG} has no section {heading}")
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("## ") or re.match(r"\[[^\]]+\]: ", lines[i])), len(lines))
    return start, end


def add_release(changelog: str, version: str, previous: str, date: str, body: str) -> str:
    """The changelog with the section of `version` right after [Unreleased], and its link."""
    lines = changelog.split("\n")
    if _UNRELEASED not in lines:
        raise ReleaseError(f"{CHANGELOG} has no '{_UNRELEASED}' heading")
    if any(line == f"## [{version}]" or line.startswith(f"## [{version}] ") for line in lines):
        raise ReleaseError(f"{CHANGELOG} already has a section [{version}]")
    start, end = _section_lines(lines, "Unreleased")
    if any(line.strip() for line in lines[start + 1:end]):
        raise ReleaseError(f"{CHANGELOG} has entries under [Unreleased]: the changelog is written at release "
                           "time, in the release pull request; move them out first")
    link = _UNRELEASED_LINK.search(changelog)
    if not link:
        raise ReleaseError(f"{CHANGELOG} has no '[unreleased]: <repository>/compare/vX.Y.Z...HEAD' link")
    if link["version"] != previous:
        raise ReleaseError(f"the [unreleased] link of {CHANGELOG} compares from v{link['version']}, "
                           f"not from the last release v{previous}")
    lines[start + 1:end] = ["", f"## [{version}] - {date}", "", *body.rstrip("\n").split("\n"), ""]
    base = link["base"]
    return "\n".join(lines).replace(link.group(0), f"[unreleased]: {base}/compare/v{version}...HEAD\n"
                                                   f"[{version}]: {base}/compare/v{previous}...v{version}", 1)


def write_section(changelog: str, version: str, date: str, body: str) -> str:
    """The changelog with the section of `version` written again: `body` in place of its content, or,
    if it is missing, the section re-created right after [Unreleased]."""
    lines = changelog.split("\n")
    entries = body.rstrip("\n").split("\n")
    try:
        start, end = _section_lines(lines, version)
        lines[start + 1:end] = ["", *entries, ""]
    except ReleaseError:
        if _UNRELEASED not in lines:
            raise ReleaseError(f"{CHANGELOG} has no '{_UNRELEASED}' heading") from None
        start, end = _section_lines(lines, "Unreleased")
        lines[end:end] = [f"## [{version}] - {date}", "", *entries, ""]
    return "\n".join(lines)


def complete_release(changelog: str, version: str, body: str) -> str:
    """The changelog with the entries of `body` added to the section of `version`, each at the end
    of its subsection (created in Keep a Changelog's order if missing)."""
    lines = changelog.split("\n")
    added = {}
    for line in body.split("\n"):
        if line.startswith("### "):
            heading = line
        elif line.strip():
            added.setdefault(heading, []).append(line)
    for heading, entries in added.items():
        start, end = _section_lines(lines, version)
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        headings = [i for i in range(start + 1, end) if lines[i].startswith("### ")]
        at = next((i for i in headings if lines[i] == heading), None)
        if at is not None:
            following = next((i for i in headings if i > at), end)
            while not lines[following - 1].strip():
                following -= 1
            lines[following:following] = ["", *entries] if following == at + 1 else entries
            continue
        order = [f"### {section}" for section in ORDER]
        rank = order.index(heading) if heading in order else len(order)
        before = next((i for i in headings if lines[i] in order and order.index(lines[i]) > rank), None)
        if before is None:
            lines[end:end] = ["", heading, "", *entries]
        else:
            lines[before:before] = [heading, "", *entries, ""]
    return "\n".join(lines)


def git(*args: str) -> str:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError as error:
        raise ReleaseError(f"cannot run git: {error}") from error
    if result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {result.stderr.strip() or 'failed'}")
    return result.stdout


def changes_since(base: str, ref: str) -> list[Change]:
    """The commits of `ref` since `base`, oldest first."""
    fields = git("log", "--reverse", "--format=%H%x00%s%x00%b%x00", f"{base}..{ref}").split("\x00")
    return [Change.parse(commit.strip(), subject, body)
            for commit, subject, body in zip(fields[0::3], fields[1::3], fields[2::3]) if commit.strip()]


def release_base(message: str) -> str | None:
    """The commit a release commit's notes were written on, from its message."""
    match = _TRAILER_LINE.search(message)
    return match["commit"] if match else None


def release_commits(version: str, ref: str) -> list[str]:
    """The release commits of `version` in the history of `ref`, newest first."""
    subject = f"chore(release): {version}"
    return [commit for commit, _, line_subject in
            (line.partition("\x00") for line in git("log", "--format=%H%x00%s", ref).splitlines())
            if line_subject == subject]


def is_ancestor(ancestor: str, commit: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, commit], capture_output=True,
                          check=False).returncode == 0


def missed(release_commit: str) -> tuple[str, list[Change]]:
    """The commit the notes of a release commit were written on, and the commits merged between that
    commit and the release commit that its notes would have listed: features, fixes, breaking
    changes, other than edits of CHANGELOG.md alone."""
    base = release_base(git("log", "-1", "--format=%B", release_commit))
    if base is None:
        raise ReleaseError(f"the release commit {release_commit[:12]} has no '{TRAILER}' trailer")
    if not is_ancestor(base, release_commit):
        raise ReleaseError(f"{base[:12]}, the {TRAILER} of {release_commit[:12]}, is not in its history")
    edits = changelog_only(base, f"{release_commit}~1")
    return base, [change for change in changes_since(base, f"{release_commit}~1")
                  if change.section and change.commit not in edits]


def changelog_only(base: str, ref: str) -> set[str]:
    """The commits of `ref` since `base` that change CHANGELOG.md and nothing else."""
    files: dict[str, set[str]] = {}
    commit = ""
    for line in git("log", "--format=%x00%H", "--name-only", f"{base}..{ref}").splitlines():
        if line.startswith("\x00"):
            commit = line[1:]
            files[commit] = set()
        elif line.strip():
            files[commit].add(line.strip())
    return {commit for commit, names in files.items() if names == {CHANGELOG}}


def tagged_commit(tag: str) -> str | None:
    try:
        return git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}").strip()
    except ReleaseError:
        return None


def section_of(changelog: str, version: str) -> str:
    """The section of `version` in the changelog, without its heading."""
    lines = changelog.split("\n")
    start, end = _section_lines(lines, version)
    return "\n".join(lines[start + 1:end]).strip("\n") + "\n"


@dataclass(frozen=True)
class Publication:
    """How the release `version` is published from a commit of main: the tag goes on `point`, its
    latest release commit followed by the commits right after it that only edit CHANGELOG.md (the
    notes edited in its pull request); later commits belong to the next release. `problem` says why
    it cannot be published, if so."""

    version: str
    release_commit: str
    point: str
    base: str | None
    notes: str
    problem: str | None
    rewrite: bool = False


def publication_point(release_commit: str, ref: str) -> str:
    """The commit a release is tagged on, in the history of `ref`: its release commit, or the last of
    the commits right after it that only edit CHANGELOG.md."""
    point = release_commit
    edits = changelog_only(release_commit, ref)
    for commit in git("rev-list", "--reverse", "--first-parent", f"{release_commit}..{ref}").split():
        if commit not in edits:
            break
        point = commit
    return point


def publication(version: str, ref: str) -> Publication | None:
    """How the release `version` is published from `ref`; None without a release commit of it."""
    releases = release_commits(version, ref)
    if not releases:
        return None
    release_commit = releases[0]
    point = publication_point(release_commit, ref)
    try:
        notes = section_of(git("show", f"{point}:{CHANGELOG}"), version)
    except ReleaseError:
        notes = ""
    # Its notes need at least one entry; whatever they miss can be added, but not to nothing.
    if not any(line.strip() and not line.startswith("### ") for line in notes.splitlines()):
        return Publication(version, release_commit, point, None, notes,
                           f"the section [{version}] of {CHANGELOG} has no entry, or is missing, at {point[:12]}",
                           rewrite=True)
    try:
        base, missing = missed(release_commit)
    except ReleaseError as error:
        return Publication(version, release_commit, point, None, notes, str(error), rewrite=True)
    if missing:
        return Publication(version, release_commit, point, base, notes,
                           f"the notes of the release commit {release_commit[:12]} miss features, fixes or breaking "
                           f"changes merged after {base[:12]}, the commit they were written on:\n"
                           + "\n".join(f"  {change.commit[:12]} {change.subject}" for change in missing))
    return Publication(version, release_commit, point, base, notes, None)


def release_version(commit: str) -> Release:
    try:
        return parse_release(git("show", f"{commit}:VERSION"))
    except ValueError as error:
        raise ReleaseError(f"VERSION of {commit[:12]}: {error}") from error


@dataclass(frozen=True)
class Plan:
    """The release to prepare at `base`: `following`, after the published release `last`. When
    `completing`, `following` is VERSION, whose release commit is merged but not published, and the
    changes are the commits its notes miss; or, when `rewrite`, the commits of the release, whose
    section is written again."""

    last: Release
    following: Release
    level: str | None
    chosen: str | None
    changes: list[Change]
    warnings: list[str]
    base: str
    completing: bool
    rewrite: bool = False


def plan(ref: str, chosen: str | None, allow_unfolded: bool = False) -> Plan:
    commit = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    current = release_version(commit)
    tag = f"v{format_release(current)}"
    tagged = tagged_commit(tag)
    warnings: list[str] = []
    if tagged:
        if not is_ancestor(tagged, commit):
            raise ReleaseError(f"{tag} is not in the history of {ref}")
        last, since, completing = current, tagged, False
        changes = changes_since(since, commit)
        if not changes:
            raise ReleaseError(f"nothing to release: {ref} is {tag}")
    else:
        # VERSION is set by a release commit, which the release workflow did not publish (yet).
        version = format_release(current)
        releases = release_commits(version, commit)
        if not releases:
            raise ReleaseError(f"VERSION is {version}, but there is no tag {tag} nor a release commit "
                               f"'chore(release): {version}' in the history of {ref}; or the tags are not fetched "
                               "(git fetch --tags origin)")
        last = release_version(f"{releases[-1]}~1")
        if not tagged_commit(f"v{format_release(last)}"):
            raise ReleaseError(f"no tag v{format_release(last)}, the release before {version} (git fetch --tags origin)")
        if chosen:
            raise ReleaseError(f"the release {version} is completed, not chosen again: no --bump")
        published = publication(version, commit)
        if not published.problem:
            raise ReleaseError(f"the release {version} can be published as it is, on {published.point[:12]}: "
                               ".github/workflows/release.yml publishes it (git fetch --tags origin for its tag, or "
                               "see its run on GitHub, and run it again if it failed)")
        # The notes of the latest release commit cover the commits up to the one they were written on;
        # without notes to add to (or that commit), the section is written again from the last release.
        completing, rewrite = True, published.rewrite
        since = f"v{format_release(last)}" if rewrite else published.base
        notes_edits = changelog_only(since, commit)
        changes = [change for change in changes_since(since, commit)
                   if change.subject != f"chore(release): {version}" and change.commit not in notes_edits]
        if not changes:
            raise ReleaseError(f"{published.problem}\nNo commit to draft: write the section of {version} by hand, in "
                               f"a pull request that changes {CHANGELOG} only")
    to_fold = [change for change in changes if _TO_FOLD.match(change.subject)]
    if to_fold and not allow_unfolded:
        raise ReleaseError("commits still to fold into the ones they fix (git rebase -i --autosquash):\n"
                           + "\n".join(f"  {change.commit[:12]} {change.subject}" for change in to_fold)
                           + "\n(--allow-unfolded if they are on main for good)")
    warnings += [f"released as it is, not folded: {change.commit[:12]} {change.subject}" for change in to_fold]
    warnings += [f"not a Conventional Commit, released as a patch: {change.commit[:12]} {change.subject}"
                 for change in changes if change.type is None and change not in to_fold]
    if completing:
        everything = [change for change in changes_since(f"v{format_release(last)}", commit)
                      if not change.subject.startswith("chore(release): ")]
        expected = bump(last, increment(everything, last))
        if expected > current:
            warnings.append(f"with the commits added, the release after {format_release(last)} would be "
                            f"{format_release(expected)}, not {format_release(current)}: a completed release keeps its "
                            "version")
        return Plan(last, current, None, None, changes, warnings, commit, True, rewrite)
    level = increment(changes, current)
    return Plan(current, bump(current, chosen or level), level, chosen if chosen != level else None, changes,
                warnings, commit, False)


def to_publish(ref: str) -> tuple[str, str, str] | None:
    """The version `ref` publishes, its notes and the commit to tag (see Publication): None if VERSION
    is tagged on another commit, or released before release commits. ReleaseError if it cannot be
    published."""
    commit = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    version = format_release(release_version(commit))
    tagged = tagged_commit(f"v{version}")
    if tagged:
        # Tagged by a run that did not finish: the release itself is still to publish.
        releases = release_commits(version, commit)
        if not releases or publication_point(releases[0], commit) != tagged:
            return None
        return version, section_of(git("show", f"{tagged}:{CHANGELOG}"), version), tagged
    published = publication(version, commit)
    if published is None:
        raise ReleaseError(f"VERSION {version} is not released, and no release commit 'chore(release): {version}' "
                           f"(scripts/release.py --commit) is in the history of {commit[:12]}")
    if published.problem:
        raise ReleaseError(f"{published.problem}\nRun scripts/release.py again on main (.claude/skills/release): it "
                           f"completes the release {version} in a pull request of its own")
    return version, published.notes, published.point


def pull_request(ref: str = "HEAD") -> str:
    """The description of the release pull request at `ref`: what merging it does, then the notes it
    publishes, as its section of the changelog holds them there, under the section's heading with its
    compare link."""
    commit = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    version = format_release(release_version(commit))
    if tagged_commit(f"v{version}"):
        raise ReleaseError(f"{version} is released already (v{version}): {ref} is not a release pull request's")
    changelog = git("show", f"{commit}:{CHANGELOG}")
    start, _ = _section_lines(changelog.split("\n"), version)
    heading = changelog.split("\n")[start]
    if not any(line.strip() and not line.startswith("### ")
               for line in section_of(changelog, version).splitlines()):
        raise ReleaseError(f"the section [{version}] of {CHANGELOG} has no entry: the release would publish nothing")
    link = re.search(rf"^\[{re.escape(version)}\]: (\S+)$", changelog, re.MULTILINE)
    if link:
        heading = f"## [{version}]({link[1]}){heading[len(f'## [{version}]'):]}"
    return (f"Merging this pull request publishes ScanMyLib {version}: `.github/workflows/release.yml` tags "
            f"`v{version}` and creates the GitHub release with the notes below. Merge nothing else before it.\n\n"
            f"{heading}\n\n{section_of(changelog, version)}")


def commit_release(release: Plan, section: str, date: str) -> None:
    """Writes VERSION and the changelog in the checkout and commits them (HEAD, not on main)."""
    branch = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], capture_output=True, text=True,
                            check=False).stdout.strip()
    version, last = format_release(release.following), format_release(release.last)
    if not branch or branch == "main":
        raise ReleaseError(f"prepare the release on its own branch, not on {branch or 'a detached HEAD'} (git "
                           f"switch -c release/v{version})")
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise ReleaseError("commit or stash the changes of this checkout first (git status)")
    # The commit the notes are written on must stay in main's history: "Rebase and merge" rewrites the
    # commits of the pull request, so the release commit is the only one it may hold.
    head = git("rev-parse", "HEAD").strip()
    if not is_ancestor(head, "refs/remotes/origin/main"):
        raise ReleaseError(f"HEAD {head[:12]} is not in origin/main: prepare the release on main as on origin, with "
                           "nothing but its release commit on its branch (git fetch origin)")
    root = Path(git("rev-parse", "--show-toplevel").strip())
    changelog = (root / CHANGELOG).read_text() if (root / CHANGELOG).is_file() else None
    if changelog is None:
        raise ReleaseError(f"no {CHANGELOG} in {root}")
    if release.rewrite:
        updated = write_section(changelog, version, date, section)
        body = (f"The release commit of {version} could not be published: its section of {CHANGELOG} has no entry, "
                f"or its notes cannot be checked. It is written again from the commits since v{last}.")
    elif release.completing:
        updated = complete_release(changelog, version, section)
        body = (f"The release commit of {version} could not be published: features, fixes or breaking changes "
                f"were merged between its notes and it. They are added to its section of {CHANGELOG}.")
    else:
        updated = add_release(changelog, version, last, date, section)
        increment_text = (f"a {release.chosen} release chosen by hand" if release.chosen
                          else f"a {release.level} release")
        body = (f"Release {version} ({increment_text}): {summary(release.changes)} since v{last}. Its notes are its "
                f"section of {CHANGELOG}.")
        (root / "VERSION").write_text(version + "\n")
    (root / CHANGELOG).write_text(updated)
    git("-C", str(root), "add", "VERSION", CHANGELOG)
    git("-C", str(root), "commit", "--quiet", "--message", f"chore(release): {version}", "--message", body,
        "--message", f"{TRAILER}: {release.base}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--ref", default="HEAD", help="the commit to release (default: HEAD)")
    parser.add_argument("--bump", choices=LEVELS, help="another increment than the commits give")
    parser.add_argument("--allow-unfolded", action="store_true",
                        help="release commits still to fold that reached main anyway, as other changes")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--version-only", action="store_true", help="print the next version only")
    output.add_argument("--notes-only", action="store_true",
                        help="print the release's section of the changelog only, without its heading")
    output.add_argument("--commit", action="store_true",
                        help="write VERSION and CHANGELOG.md and commit them; prints the pull request's description")
    output.add_argument("--description", action="store_true",
                        help="print the description of the release pull request at REF")
    output.add_argument("--to-publish", metavar="NOTES", type=Path,
                        help="print the version REF publishes, if any, and write its notes to NOTES")
    args = parser.parse_args(argv)
    if args.description:
        try:
            print(pull_request(args.ref), end="")
        except ReleaseError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        return 0
    if args.to_publish:
        try:
            published = to_publish(args.ref)
        except ReleaseError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        if published is None:
            print("VERSION is released already, on another commit: nothing to publish", file=sys.stderr)
        else:
            args.to_publish.write_text(published[1])
            print(published[0], published[2])
        return 0
    date = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        if args.commit and args.ref != "HEAD":
            raise ReleaseError("--commit prepares HEAD: no --ref")
        release = plan(args.ref, args.bump, args.allow_unfolded)
        section = notes(release.changes)
        if args.commit:
            commit_release(release, section, date)
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in release.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    version, last = format_release(release.following), format_release(release.last)
    if args.version_only:
        print(version)
    elif args.notes_only:
        print(section, end="")
    elif args.commit:
        print(pull_request(), end="")
    elif release.completing:
        print(f"Release to complete: {version} (VERSION, not tagged: its release commit could not be published)")
        if release.rewrite:
            print(f"Commits since v{last}: {len(release.changes)} ({summary(release.changes)})")
            print()
            print(f"Its section of {CHANGELOG}, written again:")
        else:
            print(f"Commits its notes miss: {len(release.changes)} ({summary(release.changes)})")
            print()
            print(f"To add to its section of {CHANGELOG}:")
        print()
        print(section, end="")
    else:
        why = {"major": "breaking changes", "minor": "new features", "patch": "fixes and other changes"}[release.level]
        if release.level == "minor" and any(change.breaking for change in release.changes):
            why = "breaking changes, before 1.0"
        level = args.bump or release.level
        chosen = f"--bump {args.bump}; the commits give a {release.level} release" if level != release.level else why
        print(f"Last release: {last} (v{last})")
        print(f"Commits since: {len(release.changes)} ({summary(release.changes)})")
        print(f"Next release: {version}, a {level} release ({chosen})")
        print()
        print(f"## [{version}] - {date}")
        print()
        print(section, end="")
    if not args.version_only and not args.notes_only and not args.commit:
        omitted = left_out(release.changes)
        if omitted:
            print()
            print("Not in the changelog (the release pull request adds the ones that matter to the readers):")
            print("\n".join(omitted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
