---
name: pull-request
description: Takes a change to ScanMyLib from a new branch to a merged pull request, in a worktree with its own development stack, and reviews someone else's pull request. Use when starting a piece of work, before pushing a branch, when opening or updating a pull request, after its base branch changes or is merged, or when the user asks to review a pull request. A release is prepared by the release skill instead.
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
2. Check that every commit passes: `cd <worktree> && git rebase --exec 'scripts/check.sh <areas>' <base>`, with the
   areas the branch changes (`lint`, `scripts`, `web`, `server`, `ocr`, `android`), then
   `cd <worktree> && scripts/check.sh` on the last commit, every area.

## Review

1. Check a visible change of the web UI in a browser, on the development stack, as `CLAUDE.md` > Workflow, "Check a
   visible change in a browser" says, and try a change to the `ocr` service on the development stack with
   `cd <worktree> && scripts/verify-sandbox.sh`. For a change under `ocr/`, also run the sandbox's tests with the
   engine's environment, as `CLAUDE.md` > Commands shows.
2. Run `/expert-review` on the branch, or `/expert-review <base>...HEAD` when it is stacked.
3. Settle each finding as `CLAUDE.md` > Workflow, "Review before pushing" says, folding each fix into its commit as
   [Fold review fixes](#fold-review-fixes) shows.
4. If the review returns while experts are still running, its message says how to finish it when their reports arrive.

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

## Fold review fixes

1. Commit each fix with `cd <worktree> && git commit --fixup=<commit>`, naming the commit it belongs to.
2. Run `cd <worktree> && GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <base>`. Git before 2.44 ignores
   `--autosquash` without `-i`, and the `-i` form works with every version.
3. Push with `cd <worktree> && git push --force-with-lease`, then keep the body true: update every section the fixes
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
