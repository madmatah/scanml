---
name: pull-request
description: Opens and updates the pull request of a ScanMyLib branch, shows in it the screens a change changes, and reviews someone else's pull request. Use when opening or updating a pull request, retargeting it to another base, putting screenshots of a visible change of the app or the web UI in it, or when the user asks to review a pull request. The pull request of a release is opened by the release skill instead.
---

# Pull request

`CLAUDE.md` > Workflow holds the rules this procedure applies, and, for every section but the review of someone else's
pull request, `.claude/skills/develop/SKILL.md` > Develop says what `<base>` and `<worktree>` are, how to write a file
whose text you write, and how a session that did not start in the branch's worktree runs each command below.

## Open the pull request

The branch is shaped, reviewed and pushed first, and its CI watched once the pull request is open, as
`.claude/skills/develop/SKILL.md` > Shape the history, > Review and > Push the branch and watch its CI say.

1. Write the body from `.github/pull_request_template.md`, which `gh pr create --body-file` does not apply: fill each
   section in place of its comment, and tick a checklist item only once it holds. Write the body in a file outside the
   repository: it is published, so it holds nothing that `.claude/rules/repository.md` > No personal information
   forbids. The pictures of a visible change need the pull request's number: they go in once it is open, as [Show a
   visible change](#show-a-visible-change) says.
2. Open the pull request against `main`, or against the base it is stacked on: write its title with the Write tool to a
   file in a directory that `mktemp -d` creates outside the worktree, then run
   `cd <worktree> && gh pr create --base <branch> --title "$(cat <title file>)" --body-file <file>`, since `gh` reads
   no title from a file and a title typed between double quotes runs its backquoted text. Without a terminal, `gh`
   needs both the title and the body. Remove the title file's directory once the pull request is open.

## Update the body

The body and the base of an open pull request change through GitHub's API: update the body from its file with
`cd <worktree> && gh api -X PATCH 'repos/{owner}/{repo}/pulls/<number>' -F body=@<file>`, and retarget the pull request
to another base with `cd <worktree> && gh api -X PATCH 'repos/{owner}/{repo}/pulls/<number>' -f base=<branch>`, where
`gh` fills in `{owner}` and `{repo}` from the checkout: `gh pr edit`, with `--body-file` or `--base`, fails on a
repository that still carries GitHub's retired Projects (classic).

## Show a visible change

A change that a screen shows, of the app or of the web UI, shows itself in its pull request, so that the reviewer sees
what it does without building it.

1. Take each screen that the change changes, of the app or of the web UI, after the change and, when it existed and
   `<base>` can show it, before it. Save each one as a PNG in a directory that `mktemp -d` creates outside the worktree,
   named for what it shows, such as `library-reading-dark-before.png` and `library-reading-dark-after.png`. They are
   published on a public branch, and a published picture stays readable by anyone who has its link, even after the
   cleanup, so they show invented data only, never a phone's screen capture, production or the user's library
   (`.claude/rules/repository.md` > No real document names and > No personal information).
2. Take the "before" on `<base>`, in a worktree of its own, `.claude/worktrees/<topic>-before`: create it with
   `cd ~/Dev/scanmylib && git worktree add --detach .claude/worktrees/<topic>-before <base>`, and run
   `cd ~/Dev/scanmylib/.claude/worktrees/<topic>-before && scripts/dev-env.sh`; then take the app's screenshot test of
   the screen there, each command prefixed with the same `cd`, or the web UI on the development stack, whose slot
   `cd ~/Dev/scanmylib/.claude/worktrees/<topic>-before && scripts/dev.sh up` takes over. Hand the slot back with
   `cd <worktree> && scripts/dev.sh up`, then remove that worktree with
   `cd ~/Dev/scanmylib && git worktree remove --force .claude/worktrees/<topic>-before`: a build or a run leaves
   untracked output there, which a plain `remove` refuses to delete, and this detached checkout of `<base>` holds
   nothing else of value. When `<base>` cannot show a screen, take its "after" only, and say why in
   the "Screenshots" section: a branch that changes the database's schema, for instance, since `<base>`'s api refuses
   the development stack's newer database.
3. Once the pull request is open, publish them:
   `cd <worktree> && python3 ${CLAUDE_SKILL_DIR}/scripts/pr_screenshots.py publish <number> <picture>...`. It refuses a
   picture that holds anything other than its pixels, such as text, a time or a color profile, which capture tools often
   add: on that refusal, run `python3 ${CLAUDE_SKILL_DIR}/scripts/pr_screenshots.py strip <dir> <picture>...`, where
   `<dir>` is a path that does not exist yet, such as `stripped` inside the directory that holds the pictures; it
   creates that directory, writes there a copy of each picture with its image only, leaves the pictures as they are and
   prints the path of each copy: publish the copies. It refuses a `<dir>` that exists, so that it never overwrites a
   file. The publication commits the pictures on the `pr-screenshots` branch of origin, under `pr-<number>/`, without
   touching the worktree, and prints a Markdown image for each, linked by that commit, so that a later publication
   never changes what the description shows. Remove the directories of the pictures once they are published.
4. Put the images in the body's "Screenshots", and update the pull request as [Update the body](#update-the-body)
   says.
5. If the script warns that the branch is heavy, tell the user: the maintainer cleans it with `/clean-pr-screenshots`.

## Review someone else's pull request

From the main checkout, run `/expert-review <number>`. The skill checks the pull request out in a temporary directory
outside the repository, so it never touches a session's worktree.
