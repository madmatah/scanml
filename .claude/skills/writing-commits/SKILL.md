---
name: writing-commits
description: Holds the rules of ScanMyLib's commit messages and writes them, so that each one says what its change achieves and why it was made, with the type and the scope the rules give it. Use when committing, amending or rewording a commit, splitting work into commits, shaping a branch's history before pushing it, or checking the commit messages of a branch before it is pushed.
---

# Writing commits

`CLAUDE.md` > Workflow, "Commits" says what a commit holds, and [The rules of a commit
message](#the-rules-of-a-commit-message) below states the rules of its message. This skill applies them to each commit
that will be pushed, whether you write it at once or while you rewrite the branch before pushing. A work-in-progress
commit or a `fixup!` commit needs none of it, since the rewrite replaces it, but the message that an `amend!` commit
carries below its first line follows it all, since it replaces the message of its commit. A release's own commit,
`chore(release): X.Y.Z`, needs none of it either, since `scripts/release.py --commit` writes it whole. Where a rule
leaves a choice, the sections below say how to make it. Write from the rules, not from `git log`, whose older messages
may predate them.

The examples below use this repository's own scopes, those of "A commit scope names where the change belongs", so that
none shows a scope the rule refuses. The changes they tell are invented: none of them is a fact about this repository.

## The rules of a commit message

- **A commit header follows the commit style:** Conventional Commits, `<type>(<scope>): <subject>`, with a type among
  those of `CLAUDE.md` > Workflow, "Each piece of work has its own short-lived branch, `<type>/<topic>`, in its own
  worktree" (`style` for layout only, such as a formatter's): `fix(android): resume uploads once back online`. A scope
  that would only repeat the type is left out, as in `ci: pin the checkout action`, and a breaking change adds `!`
  before the colon: `feat(scripts)!: deploy only published releases`.
- **A commit scope names where the change belongs:** the unit, as `docs/foundations.md` > Layers and modules names it,
  `server` for the api, `web` for the web UI, `android` for the app, `ocr` for the OCR sandbox, and `scripts`; or else
  the area: `build` for the build, the packaging and the tools' configuration, `ci` for the workflows, `docs` for
  `README.md`, `CREDITS.md` and a document of `docs/` that belongs to no single unit, `rules` for `CLAUDE.md` and
  `.claude/rules/`, a skill's name for that skill and the agents it runs, and `project` for the repository's own files,
  such as the license, `.gitignore`, `.claude/settings.json` or the pull request template. A scope is in lowercase, and
  never a file name, a path or two scopes. The documents that a change must update go in its commit, under its scope. A
  change that spans two units is usually two commits, and one that cannot be split takes the scope of the unit or the
  area that owns the decision.
- **A commit message says why.** The subject says what the change achieves, in the reader's terms, and not the files it
  touches, which the diff lists: in the imperative, in lowercase, acronyms and product names included, with a symbol
  keeping its own casing, without a final period, in a header of around 70 characters, so that it reads whole in a log.
  The body, after a blank line and wrapped at 72 columns, gives what the diff cannot show: the motivation and the
  behavior it replaces, the constraint, the observation or the rejected alternative. It never lists the changes: a body
  that restates the diff is noise. Only a change that speaks for itself goes without a body: a typo, a mechanical
  rename, a dependency bump.
- **A commit footer holds only what tools read:** a breaking change, as `BREAKING CHANGE:` followed by what breaks and
  what its users must do, which `scripts/release.py` reads, the issues the commit closes, as `Closes #42`, which GitHub
  reads, never one that is not true, and the `Release-Base:` trailer that `scripts/release.py` writes on a release's own
  commit. No other trailer, such as `Co-Authored-By`, `Generated with` or `Signed-off-by`: who typed a change says
  nothing of its reason.

## Draw the commits

Each commit holds one reason to change (`CLAUDE.md` > Workflow, "Commits"), so that a reader can review it, revert it or
find it with `git bisect` on its own.

- **A subject that needs an "and"** usually holds two commits. Two unrelated fixes made the same afternoon are two
  commits.
- **The test that pins a fix** goes in the commit of the fix, since every commit passes the checks of the areas it
  touches on its own (`CLAUDE.md` > Workflow, "Commits").
- **A correction to an earlier commit of the branch** is folded into it, as `.claude/skills/develop/SKILL.md` > Shape
  the history shows. The history describes the change that ships, not the path that found it.

## Choose the type

Take the type of the commit's dominant intention. When two seem to fit:

| The change | Type | Not |
|---|---|---|
| Restores the behavior that was intended | `fix` | `feat`, even when the fix adds code |
| Adds behavior that a user or a caller can observe | `feat` | `fix` |
| Restructures, renames or moves code without changing its behavior | `refactor` | `perf`, unless a measurement motivates it |
| Changes only the layout of the code, such as a formatter's output | `style` | `refactor` |
| Makes the code faster or leaner, as a measurement shows | `perf` | `refactor` |
| Draws a layer or a directory boundary, or adds a unit | `refactor`, or `feat` when it brings new behavior | `chore` |
| Adds or extends the tests of behavior that already works | `test` | `fix`, whose commit carries the test that pins it |
| Documents, guides and agent guidance | `docs` | `chore` |
| The CI workflows | `ci` | `build`, `chore` |
| The build, the packaging, the dependencies and the tools' configuration, the gate included | `build` | `ci`, `chore` |
| Undoes an earlier commit | the type of what the undoing does, such as `fix` when the undone commit broke something | `chore` |
| The repository's own files that are neither documents nor build, such as the license or `.gitignore` | `chore` | `build`, `docs` |

A breaking change keeps the type of what it does, and "A commit header follows the commit style" says how its header
shows it. The type matters beyond the log: `scripts/release.py` drafts the release notes from the features, the fixes
and the breaking changes, and chooses the next version from them, so a feature typed `refactor` never reaches the notes.

## Choose the scope

Take the scope as "A commit scope names where the change belongs" says. Where it leaves a doubt:

- **A document of one unit,** such as `docs/API.md` for the api, takes the unit's scope, not `docs`.
- **A test** takes the scope of the code it pins.
- **A dependency** takes the scope of the unit whose manifest or lock declares it.
- **A new unit** takes its own name, which the change adds to "A commit scope names where the change belongs", and a new
  file or directory of a unit takes the unit's.
- **A rule changed together with the skills, agents and documents that follow it** takes `rules`: the rule owns the
  decision.
- **A release's own commit,** `chore(release): X.Y.Z`, takes `release`, the name of the skill that prepares it, though
  it changes `VERSION` and `CHANGELOG.md`: `scripts/release.py --commit` writes it whole, as
  `.claude/rules/releases.md`, "Pull requests never change `VERSION`" says.

## Write the subject

Picture a reader scanning `git log --oneline` for the commit that changed a behavior. The subject is what they read, and
it decides whether they open the commit. Tell them what the change achieves, which only you know: the diff already shows
the mechanism and the files. What does not fit goes in the body. A revert gets a header of this form too, not the
`Revert "…"` that `git revert` writes.

💩 The mechanism, or nothing at all:

```
fix(android): fix upload bug
fix(android): add a retry around uploadPage
feat(server): update library.py and pages.py
fix(android): Fixed the timeout error.
```

❤ The intent:

```
fix(android): never upload a page twice when the PC times out
fix(server): say which page broke instead of refusing the whole upload
feat(web): show the pages of a document in their reading order
refactor(ocr): read the engine's results in one place instead of three
```

## Write the body

See the body as a brain dump of your state of mind at the moment you commit. Picture someone asking you, six months from
now: "Why did you do this?" You would not answer with the list of the files you edited. You would give the context that
led you there, the context you will have forgotten by then. Without it, the change gets misread, criticized, or reverted
by someone who could not see what it protected against. That someone is most likely you.

Answer the questions that reader would ask:

- What broke, or what constraint appeared? What did the previous code assume, and when did that stop holding?
- Which alternative was tempting, and why did you turn it down? Nothing else in the repository records a rejected
  approach.
- Which facts from outside the code does the change rest on: the line of a datasheet or a standard, a measured value,
  how an external service behaves? No reader can recover them from the code.

Then reread the body: a sentence that the diff could have told is one to cut. And the message is published with the
repository: an observation about a document or a machine is told with placeholders, as
[Check the message](#check-the-message) checks.

Under `fix(android): never upload a page twice when the PC times out`:

💩 The diff, told again:

```
Add an idempotency key to uploadPage and retry on timeout. Update the
upload tests accordingly.
```

❤ The context that led there:

```
Under load, the PC accepts a page and times out before it replies. The
app took the timeout for a refusal and sent the page again on its next
attempt, so a document could hold the same page twice.

An idempotency key sent with each page lets the api recognize the retry
and return the first result. A longer timeout would only have made the
duplicate rarer, never impossible.
```

## Add the footer

Write it as "A commit footer holds only what tools read" says, and never on a guess: a breaking change only when its
users will meet it, an issue only when this commit closes it.

```
feat(server)!: give the size of a page in bytes, as an integer

Clients rounded the decimal string of `size`, in megabytes, each in
their own way, so the app and the web UI could show different sizes
for the same page. An integer number of bytes leaves no rounding to
the client.

BREAKING CHANGE: `size`, a decimal string of megabytes, is replaced by
`size_bytes`, an integer number of bytes. Divide it by 1,000,000 to
show megabytes.
Closes #42
```

## Check the message

Before committing, read the message against the rules:

1. **The header** follows "A commit header follows the commit style", with the type of [Choose the
   type](#choose-the-type) and the scope of [Choose the scope](#choose-the-scope).
2. **The subject** follows "A commit message says why", in its form as in what it says: what the change achieves, not
   the files it touches.
3. **The body** follows the same rule: it says why, and lists nothing that the diff shows. Without one, the change
   really speaks for itself.
4. **The footer** follows "A commit footer holds only what tools read": what the rule requires, nothing that it
   excludes, and nothing untrue.
5. **Nothing private:** the message is published, and a pushed commit cannot be taken back, so it holds no secret and
   nothing that `.claude/rules/repository.md` > What belongs in the repository, > No real document names or > No
   personal information forbids, from a pasted log or a command's output as much as from your own words.

Nothing to run here: the commit passes what `CLAUDE.md` > Workflow, "Commits" asks of it,
`scripts/check.sh --last-commit`, which `.claude/skills/develop/SKILL.md` > Shape the history runs on every commit at
once, when the branch is shaped; the CI then runs the whole gate on the pull request, as `CLAUDE.md` > Workflow, "Run
each check once, at its level" says.
