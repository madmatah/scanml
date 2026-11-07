---
name: develop
description: Takes a piece of work in ScanMyLib from a new branch to a merged pull request, in a worktree with its own development stack. Use when starting a feature, a fix or any piece of work, planning it, writing its code, pushing its branch, dealing with review findings, or rebasing a branch whose base changed or was merged. A release is prepared by the release skill instead.
---

# Develop

`CLAUDE.md` > Workflow holds the rules this procedure applies. Below, `<base>` is `origin/main`, or the unmerged branch
the work is stacked on, and `<worktree>` the branch's worktree, `~/Dev/scanmylib/.claude/worktrees/<topic>`. Every
command of the branch below starts with `cd <worktree> &&`, as `.claude/rules/configuration.md` > Claude Code
automation, "An agent given a worktree works only there" says, which a session that did not start in the branch's
worktree reads before its first command. Write each file whose text you write, such as a plan, the findings of a round
or a commit message, with the Write tool, never through a shell: in a heredoc, or in `git commit -m "…"`, the
backquoted text that findings, plans and messages quote runs as commands. A command's output goes to its file by
redirection. Give git a message from a file in a directory that `mktemp -d` creates outside the worktree, with
`git commit -F <file>`.

## Start a branch

1. From the main checkout, run `git fetch origin`, then
   `git worktree add --no-track -b <type>/<topic> .claude/worktrees/<topic> origin/main`, with a type from `CLAUDE.md` >
   Workflow, "Each piece of work has its own short-lived branch, `<type>/<topic>`, in its own worktree". The main
   checkout keeps its HEAD, as `CLAUDE.md` > Production says.
2. If the session started with `claude --worktree <name>` instead, `<worktree>` is
   `~/Dev/scanmylib/.claude/worktrees/<name>`, on a branch `worktree-<name>`: rename the branch with
   `cd <worktree> && git branch -m <type>/<topic>`, then check that it starts from `origin/main`:
   `cd <worktree> && git fetch origin && git rev-parse HEAD origin/main` prints the same commit twice; if it does not,
   `cd <worktree> && git reset --hard origin/main`, while the branch has no commit of its own.
3. Run `cd <worktree> && scripts/dev-env.sh` once, before `scripts/dev.sh` or `scripts/build-apk.sh`, as `CLAUDE.md` >
   Workflow, "The development stack" says.

## Plan the work

Plan the work as `CLAUDE.md` > Workflow, "Plan before writing code" says, and revise the plan the same way when the code
or a review shows it wrong:

1. Spawn the `planner` agent with its brief: the worktree and its base, the goal and where it comes from, the
   constraints and the decisions you know, and, when your instructions keep the project-management material somewhere,
   its path and that of its decision log. For a revision, add the path of the plan, what showed it wrong, such as the
   findings of a review, and the commits of the branch with their files, from
   `cd <worktree> && git log --format='%h %s' --name-only <base>..HEAD`. Write each plan it returns, without its
   `Answers` section, where your instructions keep the plan of a branch, and commit it as they say.
2. Spawn the `plan-critic` agent with the worktree, its base, the goal, the constraints, the decisions and the user's
   answers you know, and the path of the plan, and, for a revision, what showed the plan wrong and the commits of the
   branch, as the planner got them. Resume the planner with the critic's blocking and should-fix points, rather than
   spawning a new one that would read the code again, then resume the critic with the planner's answers. Go on until
   the critic says `ready`. After three rounds, ask the user about what remains, or, when the user does not follow the
   work, stop and give the plan and its open points in your final report.
3. When the user follows the work, show them the plan and its open questions, and wait for their approval: a change
   they ask for goes to the planner, then to the critic. Otherwise, take the answer that the plan recommends to each
   open question, and name it in the pull request.

## Write the code

Write the code from the plan, or give it to an agent on Opus at `high`, as `.claude/rules/configuration.md` > Claude
Code automation says, with the worktree, its base and the path of the plan, and the bound that
`.claude/rules/configuration.md` > Claude Code automation, "An agent given a worktree works only there" sets, which it
reads before its first command, as the `fixer` agent does: it reads the plan, and writes each commit message as
`.claude/skills/develop/SKILL.md` > Develop says. When the plan proves wrong, stop, and revise it as [Plan the
work](#plan-the-work) says. If an agent was writing the code, commit or drop its work in progress, as the revised plan
says, then give the rest to a new agent, with the revised plan and the commits so far: the one that stopped carries a
context that only grows.

## Stack on an unmerged branch

- **A branch may start from another unmerged branch whose work it needs:** give that branch instead of `origin/main` to
  `git worktree add`. Until it is merged, it is `<base>`: review against it, as [Review](#review) says, autosquash onto
  it, and open the pull request against it, naming it in the Proposal.
- **Whenever the base is rewritten,** by its review fixes or by its merge, move only your own commits:
  `cd <worktree> && git rebase --onto <new base> $(git merge-base --fork-point <branch> HEAD)`. The new base is the
  branch itself, or `origin/main` once it is merged; the old copies of its commits would conflict with the new ones.
  Once the base is merged, retarget the pull request to `main`, as `.claude/skills/pull-request/SKILL.md` > Update the
  body says.
- **The owner of a base keeps it until the branches built on it have moved.** Each of those branches is moved by its own
  owner.

## Shape the history

1. Before pushing, rewrite the branch into atomic commits, as `CLAUDE.md` > Workflow, "Commits" asks, and write each
   message with the `writing-commits` skill, which holds the rules of a commit message. Interactive editors are
   unavailable: fold a change into its commit with `cd <worktree> && git commit --fixup=<commit>`, then
   `cd <worktree> && GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <base>`.
2. Check every commit as `CLAUDE.md` > Workflow, "Commits" asks: each one on the areas it touches, with
   `cd <worktree> && git rebase --exec 'scripts/check.sh --last-commit' <base>`, then the last one on every area, with
   `cd <worktree> && scripts/check.sh`.

## Review

1. Check a visible change, as `CLAUDE.md` > Workflow, "Check a visible change" says: of the web UI in a browser, on the
   development stack; of the app in its screenshot tests, with `cd <worktree> && scripts/build-apk.sh
   testDebugUnitTest`, then a look at the pictures under `android/app/build/outputs/roborazzi/`. Run the tests that the
   gate skips and the change calls for, as the `running-tests` skill says.
2. Run `/expert-review <branch>`, or `/expert-review <base>...<branch>` when it is stacked, naming the branch rather
   than `HEAD`: the review runs in the session's directory, whose `HEAD`, in the main checkout, is production's release.
   Run one review at a time in a session: one started while another runs waits in the foreground, where it can hand
   back before its agents answer. The review runs in the background, and its report reaches you as a message; under
   `claude -p`, or with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` set, it runs in the foreground, and its report is the
   result of the call. Wait for it before you settle anything. A report that says its triage or an expert still runs
   was handed back too soon, as "A review that hands back too soon" below says. Claude Code loads the skills and agents
   of the session's directory, not the branch's: a session that did not start in the branch's worktree reviews and
   fixes it with its own definitions, and one started there with the branch's own. When the branch changes the skills
   or agents that review or fix it, the pull request names the definitions that reviewed it, and says when they are not
   the branch's.
3. Settle each finding as `CLAUDE.md` > Workflow, "Review before pushing" says. Give the findings to fix to a new
   `fixer` agent, with its brief: the worktree and its base, the purpose of the branch, each verified finding, and the
   commit each fix belongs to. It commits each fix as a `fixup!` commit, or as an `amend!` commit for a commit message,
   as [Fold review fixes](#fold-review-fixes) shows. A fix commit whose check failed is a finding of the round, given
   to a new fixer like the others, even when its fix brought it, and never answered in the pull request. Before you
   fold them, review the fixes alone, against the findings they answer: write those findings, as the review reported
   them, and each failed check with its output, with the Write tool, to a file in a directory that `mktemp -d` creates
   outside the worktree, and run
   `/expert-review <the commit before the first fix of the round>...<branch> --fixes <file>`. Remove the directory once
   the review of the fixes has handed back its report and you have settled each of its findings: given to a fixer,
   answered in the pull request, or carried into a revised plan. A finding that needs a change of design, or that a fix
   brought into the code it fixed, other than a failed check, ends the round instead: revise the plan of the branch
   with all the findings of the round, as [Plan the work](#plan-the-work) says, give the change to a new agent, as
   [Write the code](#write-the-code) says, shape the history again, as [Shape the history](#shape-the-history) says,
   and review the whole branch again, as the first round does. Keep the cost of each round, from its report, for the
   decision that `CLAUDE.md` > Workflow, "Rounds of review converge, or the user decides" leaves to the user. Go on
   round by round as `CLAUDE.md` > Workflow, "Review before pushing" and "Rounds of review converge, or the user
   decides" say, then fold the fixes.
4. **A review that hands back too soon:** if the review hands back a report that says its triage or an expert still
   runs, or an answer of its triage or of an expert reaches you rather than the review, the review handed back too
   soon: set its report aside and act on none of it. Stop, and tell the user, or, when the user does not follow the
   work, say in your final report: the answers that reached you, what you already started from that report, such as a
   fixer and its commits, in a round of fixes the path of its `--fixes` file, and the detached worktrees outside the
   repository that `cd <worktree> && git worktree list` shows, which this review or another one still running may use.
   Remove none of them and run no review again: the review's agents may still be running, and only the user decides
   what happens next.

## Push the branch and watch its CI

1. Push the branch: `cd <worktree> && git push -u origin HEAD` the first time.
2. Open the pull request as `.claude/skills/pull-request/SKILL.md` > Open the pull request says.
3. Make sure CI (`scripts/check.sh` on GitHub Actions, one job per area) passes on it: `gh pr checks <number> --watch`.

## Fold review fixes

1. Commit each fix with `cd <worktree> && git commit --fixup=<commit>`, naming the commit it belongs to. A fix to the
   message of a commit goes in an `amend!` commit, since a `fixup!` commit keeps the message of its target: in a
   directory that `mktemp -d` creates outside the worktree, write, with the Write tool, a file whose first line is
   `amend! ` followed by the header of the commit, whole, as `git log -1 --format=%s <commit>` prints it, since
   autosquash matches that line, then a blank line and the whole new message; run
   `cd <worktree> && GIT_EDITOR="cp <file>" git commit --fixup=reword:<commit>`, or `--fixup=amend:<commit>` to fold the
   staged changes with it, and remove the directory. Neither `-m` nor `-F` combines with these forms.
2. Run `cd <worktree> && GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <base>`. Git before 2.44 ignores
   `--autosquash` without `-i`, and the `-i` form works with every version.
3. Check that `cd <worktree> && git log --format='%h %s' <base>..HEAD` lists no `fixup!`, `amend!` or `squash!`
   commit. One that is left names, by its first line, no whole header of `<base>..HEAD`: find the commit it fixes by
   meaning, in that list or, on a stacked branch, in `cd <worktree> && git log --format='%h %s' origin/main..<base>`.
   Take the leftovers one at a time, each from a fresh listing and with its own directory that `mktemp -d` creates
   outside the worktree, since each drop rewrites the commits after it. `<leftover>`, and `<that commit>` below, the
   commit it fixes, are each the abbreviated hash that its listing prints, and nothing else of its line, since the rest
   is a commit's message. For each `<leftover>`:
   - **save it:** its change with `cd <worktree> && git diff --binary <leftover>^ <leftover> > "<dir>/fix.patch"`, and
     the message of an `amend!` or `squash!` commit with
     `cd <worktree> && git log -1 --format=%B <leftover> > "<dir>/message"`;
   - **drop it:** `cd <worktree> && git rebase --onto <leftover>^ <leftover>`;
   - **when it fixes a commit of `<base>..HEAD`,** commit the fix again:
     `cd <worktree> && git apply --3way "<dir>/fix.patch"`, skipped when the patch is empty, as a reworded message
     leaves it, then `cd <worktree> && git commit --fixup=<that commit>`, or, for an `amend!` commit, the `amend!` form
     above, from the saved message under a corrected first line, and for a `squash!` commit the same form, from the
     message of that commit, `cd <worktree> && git log -1 --format=%B <that commit>`, followed by the saved message
     without its first line; fold again, and remove `<dir>`;
   - **when it fixes a commit of the branch this one is stacked on,** the fix belongs to that branch: its owner commits
     it there as above and folds it, then this branch moves, as [Stack on an unmerged
     branch](#stack-on-an-unmerged-branch) says. When another session owns that branch, keep `<dir>`, put the finding
     and the paths of `fix.patch`, and of `message` when one was saved, in your final report, for the coordinating
     session to pass on to that owner, and name the finding in the pull request. A check of this branch that fails for
     want of that fix waits for the move;
   - **when a step conflicts or fails,** such as `git apply --3way`, which exits with an error and no conflict when the
     file it patches was deleted, undo it and keep `<dir>`: `cd <worktree> && git rebase --abort` when the drop stops,
     which leaves the leftover on the branch, or when the fold stops, which leaves the fix as a commit;
     `cd <worktree> && git reset --merge` when `git apply --3way` leaves conflicts or fails, which leaves the fix in
     `<dir>/fix.patch` only. Resolve nothing, stop [Fold review fixes](#fold-review-fixes) and push nothing: tell the
     user, or, when the user does not follow the work, put in your final report the finding, where its fix now lives
     and the paths of `fix.patch`, and of `message` when one was saved.

   Repeat this check until it lists none, then check the commits again, as [Shape the history](#shape-the-history)
   does.
4. Push with `cd <worktree> && git push --force-with-lease`, then keep the body true: update every section the fixes
   changed, and the "Screenshots" section, with pictures taken and published as `.claude/skills/pull-request/SKILL.md` >
   Show a visible change says. A screen whose change the fixes alter is published again, and its new "after" takes the
   place of the former one; a screen that they change for the first time gets its "before" too; a screen whose change
   they undo loses its images. Then update the body once, as `.claude/skills/pull-request/SKILL.md` > Update the body
   says.

## Merge

- **The user merges the pull request,** as `CLAUDE.md` > Workflow, "A branch reaches `main` only through a pull request
  whose CI passes" says.
- **After the merge,** keep the branch until the branches stacked on it have moved, as [Stack on an unmerged
  branch](#stack-on-an-unmerged-branch) says. Then stop its development stack if it still runs
  (`cd <worktree> && scripts/dev.sh down`), and remove the worktree and the branch from the main checkout:
  `cd ~/Dev/scanmylib && git worktree remove <worktree> && git branch -D <type>/<topic>`.
