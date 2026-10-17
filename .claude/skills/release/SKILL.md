---
name: release
description: Prepares a new ScanMyLib release for GitHub, from what main holds since the last one, as a pull request that the user merges and a workflow then publishes. Use when the user wants to release, ship or publish a new version, asks which version comes next, or a release could not be published and has to be completed. Not for deploying a release to an installation.
argument-hint: "[major|minor|patch]"
---

# Prepare a release

A release is the maintainer's work on GitHub: a pull request of its own, `chore(release): X.Y.Z`, with one commit
that sets `VERSION` and adds the release's section to `CHANGELOG.md`. Once the user merges it,
`.github/workflows/release.yml` tags `vX.Y.Z` on its release commit (or on the last edit of its notes right after it)
and publishes a GitHub release with that section as its notes. This skill prepares that pull request and stops there.
Deploying is not part of it: each installation deploys the releases it chooses (`scripts/deploy.sh`), when its owner
asks. Its worktree is removed after the merge, as any other.

If the user gave an increment (`$ARGUMENTS`: `major`, `minor` or `patch`), use it instead of the one the commits give
(`--bump`).

## 1. Check that a release can start

```bash
git -C ~/Dev/scanmylib fetch --tags origin
gh run list --workflow ci.yml --branch main --limit 1    # CI green on the last commit of main
gh run list --workflow release.yml --limit 1             # the last release's publication
gh pr list --state open                                  # no release pull request open yet
```

Stop and tell the user if CI is not green on the last commit of `main`, or if a release pull request is already
open. A failed release run is not a reason to stop: its release could not be published, and this procedure completes
it (step 2). Name the other open pull requests: they are not in this release, and must not be merged while its pull
request is open. If the worktree `../scanmylib-worktrees/release` or the branch `release` still exists, it is a
previous release's that was not removed after its merge: tell the user, and remove it with their agreement.

## 2. Propose the version

From the primary checkout, a worktree on `main` as on `origin`:

```bash
git worktree add --no-track -b release ../scanmylib-worktrees/release origin/main
cd ../scanmylib-worktrees/release
scripts/release.py                                   # or: scripts/release.py --bump LEVEL
```

It prints the last release, the commits since, the next version and why, the draft of the release's section of
`CHANGELOG.md` (Keep a Changelog: features under Added, fixes under Fixed, breaking changes under Changed), and the
commits it leaves out (refactor, test, build, ci, docs, chore). It changes nothing. It refuses when there is nothing
to release, or when commits are still to fold (`fixup!`, `amend!`): those are folded in their pull request before it
is merged; if one reached `main` anyway, `main` is never rewritten, and with the user's agreement `--allow-unfolded`
releases it as it is. It warns about commits that do not follow Conventional Commits: look at what they change before
settling the increment.

If `VERSION` has no tag although its release commit is merged, that release could not be published: features, fixes
or breaking changes were merged between the commit its notes were written on and it, or its section has no entry (the
workflow's run says which). `scripts/release.py` then completes it, in a new pull request for the same version: it
drafts the commits merged since the notes were written, which step 3 adds to the release's section, or, for a section
without entries, the whole section again from the release's commits. If the release can be published as it is, it
says so: it is waiting for its run, or its tag is not fetched.

Show the user the version, the reason, the draft and the commits left out, in their language. Wait for their
go-ahead, another increment, or changes to the draft: entries reworded, merged or removed, a left-out commit that
matters to the readers added, a Security or Removed section.

## 3. Open the release pull request

```bash
scripts/release.py --commit > /path/to/release-pr.md    # same --bump as accepted; a file outside the repository
```

It writes `VERSION` and the section (dated today, UTC), commits them as `chore(release): X.Y.Z` with the commit the
notes were written on (trailer `Release-Base`), and prints the pull request's description, which points to the
section rather than copying it. Apply the changes the user asked for to `CHANGELOG.md`, then
`git add CHANGELOG.md && git commit --amend --no-edit`: the release stays one commit, with its trailer. Then:

```bash
git push --set-upstream origin release
gh pr create --base main --title "chore(release): X.Y.Z" --body-file /path/to/release-pr.md
```

Give the user the link. Later changes to the notes are made the same way (then `git push --force-with-lease`), or as
commits that change `CHANGELOG.md` only, such as suggestions on GitHub. Remind the user to merge nothing else before
it: a feature, fix or breaking change merged in between is missing from the notes, and the workflow then publishes
nothing.

## 4. Once the user says it is merged

```bash
gh run list --workflow release.yml --limit 1
gh release view vX.Y.Z
```

Tell the user whether the release is published, with its link, or what the workflow reported. If it published
nothing (features, fixes or breaking changes merged in between, or an empty section), the release is completed by
this procedure again, from step 1. Commits merged after the release commit, other than edits of its notes, belong to
the next release.

## Rules

- Only a release pull request changes `VERSION`, with `scripts/release.py --commit`; tags and GitHub releases come
  from `.github/workflows/release.yml` only.
- This procedure never merges, deploys, or touches production.
- An urgent fix follows the same path: its own pull request, then a release. A patch, unless `main` already holds
  unreleased features, which ship with it.
