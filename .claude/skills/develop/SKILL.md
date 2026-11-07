---
name: develop
description: Takes a piece of work in ScanMyLib from a new branch to a merged pull request, in a worktree with its own development stack. Use when starting a feature, a fix or any piece of work, planning it, writing its code, pushing its branch, dealing with review findings, or rebasing a branch whose base changed or was merged. A release is prepared by the release skill instead.
---

# Develop

`CLAUDE.md` > Workflow holds the rules of every session, and this skill those of planning, beside the steps that apply
them. Below, `<base>` is `origin/main`, or the unmerged branch the work is stacked on, and `<worktree>` the branch's
worktree, `~/Dev/scanmylib/.claude/worktrees/<topic>`. Every command of the branch below starts with `cd <worktree> &&`,
as `.claude/rules/configuration.md` > Claude Code automation, "An agent given a worktree works only there" says, which a
session that did not start in the branch's worktree reads before its first command. Write each file whose text you
write, such as a plan, the findings of a round or a commit message, with the Write tool, never through a shell: in a
heredoc, or in `git commit -m "…"`, the backquoted text that findings, plans and messages quote runs as commands. A
command's output goes to its file by redirection. Give git a message from a file in a directory that `mktemp -d` creates
outside the worktree, with `git commit -F <file>`.

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

- **Size the work before planning it:** mechanical work is a known transformation with a recipe, such as a sync with a
  template the project follows, a rename across files or a migration with a recipe; normal work adds no module, no
  public interface and no decision that changes the project; large work is the rest. State the size and its reason when
  the work starts, and at the top of its plan, so that the user and the critic can question it, and take the size the
  user gives instead. Once the decisions are settled, size the work again: a decision that changes the project, or a
  new module or public interface, makes normal work large.
- **Settle the decisions with the user before planning:** when the user follows normal or large work, interview them on
  the decisions it leaves open before any plan is written, as [Interview the user](#interview-the-user) says. Agents
  find the facts, and only the decisions go to the user. When the user does not follow the work, there is no interview:
  take the recommended answer to each open decision, record it in the plan as decided alone, and list it in the pull
  request, for the user to check.
- **Plan before writing code:** each piece of work has a plan, kept outside this repository (`CLAUDE.md` > Project
  management), written and checked as its size calls for, at the effort that `.claude/rules/configuration.md` > Claude
  Code automation gives. Mechanical work has a brief of about 20 lines, written by the session, and no check. The
  session writes the plan of normal work, since it holds the decisions first-hand, and a `plan-critic` agent checks it
  in one round, and in a second only for a blocking point. A `planner` agent writes the plan of large work, and a
  `plan-critic` agent checks it. The critic did not write the plan: it checks it against the code and the rules before
  any code is written. Only these changes go without a plan: a typo, a rename inside one file, a dependency bump, a bug
  fix inside one function. A review fix stays within the plan: only a change of design, or the change of method that
  `CLAUDE.md` > Workflow, "Rounds of review converge, or the user decides" calls for, goes back to it. The code follows
  the plan: an implementation that finds it wrong stops and says why, and the plan is revised and checked again as its
  size calls for before the work goes on.
- **A mock comes before the plan of an output a person reads:** when planned work adds or changes something whose layout
  or content a reader judges, such as a document that the code generates, a report, the output of a command or a
  screen, rather than a single message, its plan starts from a mock of that output, written by hand with realistic
  values. The user approves it, or, when the user does not follow the work, the pull request shows it as not approved.
  The mock is part of the goal: the plan, the code and its tests aim for it, and a change of that output goes back to
  the user, as a change of the goal does, or, when the user does not follow the work, is marked as not approved.

Plan the work as "Size the work before planning it", "Settle the decisions with the user before planning" and "Plan
before writing code" say, and revise the plan the same way when the code or a review shows it wrong. State the size and
its reason in your reply, or, when the user does not follow the work, in your final report. The plan goes where your
instructions keep the plan of a branch; without such instructions, to a file outside the repository, whose path you
give the user. Never in the repository: `CLAUDE.md` > Project management.

When the work calls for a mock, as "A mock comes before the plan of an output a person reads" says, write it before the
interview asks about it, or, without an interview, before the plan, with the Write tool, beside the plan, with
`.mock.md` in place of `.md`: Markdown or text, a screen sketched in text, with realistic, invented values, and one
sample for each case that changes what the reader sees. Show it to the user in your reply, and change it as they ask
until they approve it, or, when the user does not follow the work, go on from it. Wherever a step gives the goal, give
the mock's path too, and say whether the user approved it, and commit the mock wherever the plan is committed. When the
user did not approve the mock, or a change of that output, say so in your final report, and show the mock in the
Proposal of the pull request, marked as not approved.

### Interview the user

Before any plan of normal or large work is written, settle its open decisions as [Plan the work](#plan-the-work),
"Settle the decisions with the user before planning" says:

1. Find the facts without the user, such as what the code does, what a library offers or what a rule says, through
   explorers on Haiku or Sonnet, as `CLAUDE.md` > Workflow, "Give searches and explorations to cheaper agents" says.
2. List the open decisions, and which ones depend on another: the goal and what it leaves out, the design choices, the
   mock when there is one, and where the tests go, through which public interfaces, as few as the goal allows, each
   with what it catches and what it misses.
3. When the user does not follow the work, take the answer you recommend to each open decision, give it as decided
   alone to whoever writes the plan, and go on to the last step. Otherwise, ask them in rounds, in plain text in your
   reply, never with the multiple-choice question tool, which caps a round at four questions of four options. A round
   asks every question whose prerequisites are settled, the goal aside: one that depends on a question still open, or
   on a fact still being searched for, waits for a later round. The first round opens with the goal and what it leaves
   out, as you restate them, for the user to confirm, whether open or not, since the plan, the code and their checks
   all aim at the goal, and asks the questions that depend on the goal in the same round, on your reading: an answer
   that changes the goal reopens them. Number each question, give it the context it needs to be understood on its own,
   and give your recommended answer, worded so that "yes" accepts it. Then wait for the answers.
4. Each round of answers settles decisions and opens the questions that depended on them: ask the next round, until no
   decision is left open.
5. Record each decision that changes the project as your instructions say. Size the work again, as [Plan the
   work](#plan-the-work), "Size the work before planning it" says, and state a new size and its reason where you stated
   the first.

### Mechanical work

Write the brief to the plan's path, with the Write tool: the size and its reason, the goal and what it leaves out, the
recipe and where it comes from, and the commits, each with its reason to change. Then, without waiting, commit it as
your instructions say, and write the code as [Write the code](#write-the-code) says.

### Normal work

1. Write the plan yourself, with the Write tool, or the Edit tool for a revision, as `.claude/agents/planner.md` > Plan
   and > The plan say. For a revision, start from what showed the plan wrong, such as the findings of a review, and the
   commits of the branch with their files, from `cd <worktree> && git log --format='%h %s' --name-only <base>..HEAD`.
2. Spawn the `plan-critic` agent at `high`, through the Agent tool's `effort`, with the worktree, its base, the goal,
   the constraints, the decisions and the user's answers you know, and the path of the plan, and, for a revision, what
   showed the plan wrong and the commits of the branch. Answer each blocking and should-fix point in the plan yourself.
   When you agree with the critic that the work is large, or the user makes it large, go on as [Large
   work](#large-work) says instead, for a revision of your plan that starts from the critic's points.
3. Run a second round only when a point was blocking: resume the critic with your answers. When a blocking or
   should-fix point remains after it, ask the user about it, or, when the user does not follow the work, stop and give
   the path of the plan and its open points in your final report.
4. Commit the plan as your instructions say, and go on as [After the plan](#after-the-plan) says.

### Large work

1. Spawn the `planner` agent with its brief: the worktree and its base, the size and its reason, the goal and where it
   comes from, the constraints, the decisions you settled with the user and those you took alone, and, when your
   instructions keep the project-management material somewhere, its path and that of its decision log. For a revision,
   add the path of the plan, what showed it wrong, such as the findings of a review, and the commits of the branch with
   their files, from `cd <worktree> && git log --format='%h %s' --name-only <base>..HEAD`. Write each plan it returns,
   without its `Answers` section, to the plan's path, with the Write tool.
2. Spawn the `plan-critic` agent with the worktree, its base, the goal, the constraints, the decisions and the user's
   answers you know, and the path of the plan, and, for a revision, what showed the plan wrong and the commits of the
   branch, as the planner got them. Resume the planner with the critic's blocking and should-fix points, rather than
   spawning a new one that would read the code again, then resume the critic with the planner's answers. Go on until
   the critic says `ready`. After three rounds, ask the user about what remains, or, when the user does not follow the
   work, stop and give the path of the plan and its open points in your final report.
3. Once the critic says `ready`, commit the plan as your instructions say, and go on as [After the
   plan](#after-the-plan) says.

### After the plan

When the user follows the work, give them the path of the plan, its summary and its open questions, and wait for their
answers only while open questions remain: the interview settled the rest. Revise the plan with a change they ask for:
yourself for normal work, or, for large work, by resuming the planner with the change as the user's answer. Then have
the critic check it, as [Normal work](#normal-work) or [Large work](#large-work) says, and commit the plan again. When
the user does not follow the work, move each open question, with the answer that the plan recommends, to its "Decided
alone" section, and commit the plan again.

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
