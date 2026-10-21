---
name: pull-request
description: Takes a change to ScanMyLib from a new branch to a merged pull request, in a worktree with its own development stack, and reviews someone else's pull request. Use when starting a piece of work, before pushing a branch, when opening or updating a pull request, when showing screenshots of a change in its pull request, after its base branch changes or is merged, or when the user asks to review a pull request. A release is prepared by the release skill instead.
---

# Pull request

`CLAUDE.md` > Workflow holds the rules this procedure applies. Below, `<base>` is `origin/main`, or the unmerged branch
the work is stacked on, and `<worktree>` the branch's worktree, `~/Dev/scanmylib/.claude/worktrees/<topic>`. The shell
may be back in the main checkout between two calls, where a rebase or a commit would move production's release
(`CLAUDE.md` > Production): every command of the branch below starts with `cd <worktree> &&`.

## Start a branch

1. From the main checkout, run `git fetch origin`, then
   `git worktree add --no-track -b <type>/<topic> .claude/worktrees/<topic> origin/main`, with a type from `CLAUDE.md` >
   Workflow, "Commits". The main checkout keeps its HEAD, as `CLAUDE.md` > Production says.
2. If the session started with `claude --worktree <name>` instead, `<worktree>` is
   `~/Dev/scanmylib/.claude/worktrees/<name>`, on a branch `worktree-<name>`: rename the branch with
   `cd <worktree> && git branch -m <type>/<topic>`, then check that it starts from `origin/main`:
   `cd <worktree> && git fetch origin && git rev-parse HEAD origin/main` prints the same commit twice; if it does not,
   `cd <worktree> && git reset --hard origin/main`, while the branch has no commit of its own.
3. Run `cd <worktree> && scripts/dev-env.sh` once, before `scripts/dev.sh` or `scripts/build-apk.sh`, as `CLAUDE.md` >
   Workflow, "The development stack" says.

## Stack on an unmerged branch

- **A branch may start from another unmerged branch whose work it needs:** give that branch instead of `origin/main` to
  `git worktree add`. Until it is merged, it is `<base>`: review with `/expert-review <branch>...HEAD`, autosquash onto
  it, and open the pull request against it, naming it in the Proposal.
- **Whenever the base is rewritten,** by its review fixes or by its merge, move only your own commits:
  `cd <worktree> && git rebase --onto <new base> $(git merge-base --fork-point <branch> HEAD)`. The new base is the
  branch itself, or `origin/main` once it is merged; the old copies of its commits would conflict with the new ones.
  Once the base is merged, retarget the pull request to `main`.
- **The owner of a base keeps it until the branches built on it have moved.** Each of those branches is moved by its own
  owner.

## Shape the history

1. Before pushing, rewrite the branch into atomic commits, as `CLAUDE.md` > Workflow, "Commits" and "A commit message
   says why" ask, and write each message with the `writing-commits` skill. Interactive editors are unavailable: fold a
   change into its commit with `cd <worktree> && git commit --fixup=<commit>`, then
   `cd <worktree> && GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <base>`.
2. Check every commit as `CLAUDE.md` > Workflow, "Commits" asks: each one on the areas it touches, with
   `cd <worktree> && git rebase --exec 'scripts/check.sh --last-commit' <base>`, then the last one on every area, with
   `cd <worktree> && scripts/check.sh`.

## Review

1. Check a visible change, as `CLAUDE.md` > Workflow, "Check a visible change" says: of the web UI in a browser, on the
   development stack; of the app in its screenshot tests, with `cd <worktree> && scripts/build-apk.sh
   testDebugUnitTest`, then a look at the pictures under `android/app/build/outputs/roborazzi/`. Run the tests that the
   gate skips and the change calls for, as the `running-tests` skill says.
2. Run `/expert-review` on the branch, or `/expert-review <base>...HEAD` when it is stacked. While it reads the
   worktree, run nothing that moves the worktree between commits, such as `git rebase --exec`: the experts would read
   another revision than the one under review.
3. Settle each finding as `CLAUDE.md` > Workflow, "Review before pushing" says, committing each fix as a `fixup!`
   commit, as [Fold review fixes](#fold-review-fixes) shows. Before you fold them, review the fixes alone, against the
   findings they answer: write those findings, as the review reported them, with the Write tool, to a file in a
   directory that `mktemp -d` creates outside the worktree, and run
   `/expert-review <the commit before the first fix of the round>...HEAD --fixes <file>`. Remove the directory once the
   round's report arrives. Then fold them.
4. If an answer of its triage or of an expert reaches you rather than the review, the review handed back its report
   too soon: set that report aside, send the answer to the review with SendMessage, addressed to the agent ID that its
   invocation returned, or else to the name it runs under, such as `expert-review`, and act only on the report it hands
   back next.

## Push and open the pull request

1. Push the branch: `cd <worktree> && git push -u origin HEAD` the first time.
2. Write the body from `.github/pull_request_template.md`, which `gh pr create --body-file` does not apply: fill each
   section in place of its comment, and tick a checklist item only once it holds. Write the body in a file outside the
   repository: it is published, so it holds nothing that `.claude/rules/repository.md` > No personal information
   forbids.
3. Open the pull request against `main`, or against the base it is stacked on:
   `cd <worktree> && gh pr create --base <branch> --title "<title>" --body-file <file>`. Without a terminal, `gh` needs
   both the title and the body.
4. Make sure CI (`scripts/check.sh` on GitHub Actions, one job per area) passes on it: `gh pr checks <number> --watch`.

## Show a visible change

A change that a screen shows, of the app or of the web UI, shows itself in its pull request, so that the reviewer sees
what it does without building it.

1. Take each screen that the change changes, of the app or of the web UI, after the change and, when it existed, before
   it. Name each PNG for what it shows, such as `library-reading-dark-before.png` and `library-reading-dark-after.png`.
   They are published on a public branch, so they show invented data only, never a phone's screen capture, production
   or the user's library (`.claude/rules/repository.md` > No real document names and > No personal information).
2. Take the "before" on `<base>`, in a worktree of its own (`git worktree add --detach <path> <base>`, then
   `scripts/dev-env.sh` there): the app's screenshot test of the screen, or the web UI on the development stack, whose
   slot `scripts/dev.sh up` there takes over; take the slot back with `scripts/dev.sh up` in `<worktree>`, and remove
   that worktree. A branch that changes the database's schema shows its "after" only, since `<base>`'s api refuses the
   development stack's newer database.
3. Once the pull request is open, publish them:
   `cd <worktree> && ${CLAUDE_SKILL_DIR}/scripts/publish_screenshots.py <number> <picture>...`. It commits them on the
   `pr-screenshots` branch of origin, under `pr-<number>/`, without touching the worktree, and prints a Markdown image
   for each, linked by that commit, so that a later publication never changes what the description shows.
4. Put the images in the body's "Screenshots", and update the pull request:
   `cd <worktree> && gh api -X PATCH 'repos/{owner}/{repo}/pulls/<number>' -F body=@<file>`, where `gh` fills in
   `{owner}` and `{repo}`: `gh pr edit` fails on the GraphQL fields of GitHub's retired Projects (classic).
5. If the script warns that the branch is heavy, tell the user: the maintainer cleans it with `/clean-pr-screenshots`.

## Fold review fixes

1. Commit each fix with `cd <worktree> && git commit --fixup=<commit>`, naming the commit it belongs to.
2. Run `cd <worktree> && GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <base>`. Git before 2.44 ignores
   `--autosquash` without `-i`, and the `-i` form works with every version.
3. Check the commits again, as [Shape the history](#shape-the-history) does.
4. Push with `cd <worktree> && git push --force-with-lease`, then keep the body true: update every section the fixes
   changed.

## Merge

- **The user merges the pull request,** as `CLAUDE.md` > Workflow, "A branch reaches `main` only through a pull request
  whose CI passes" says.
- **After the merge,** keep the branch until the branches stacked on it have moved, as [Stack on an unmerged
  branch](#stack-on-an-unmerged-branch) says. Then stop its development stack if it still runs
  (`cd <worktree> && scripts/dev.sh down`), and remove the worktree and the branch from the main checkout:
  `cd ~/Dev/scanmylib && git worktree remove <worktree> && git branch -D <type>/<topic>`.

## Review someone else's pull request

From the main checkout, run `/expert-review <number>`. The skill checks the pull request out in a temporary directory
outside the repository, so it never touches a session's worktree.
