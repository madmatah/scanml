---
name: writing-commits
description: Writes the commit messages of ScanMyLib, so that each one says what its change achieves and why it was made, with the type and the scope the repository's rules give it. Use when committing, amending or rewording a commit, splitting work into commits, shaping a branch's history before pushing it, or checking the commit messages of a branch before it is pushed.
---

# Writing commits

`CLAUDE.md` > Workflow states the rules of a commit: "Commits", "A commit scope names where the change belongs", "A
commit message says why" and "A commit footer holds only what tools read". This skill applies them to each commit that
will be pushed, whether you write it at once or while you rewrite the branch before pushing. A work-in-progress commit
or a `fixup!` commit needs none of it, since the rewrite replaces it, and neither does a release's own commit,
`chore(release): X.Y.Z`, which `scripts/release.py --commit` writes whole. Where a rule leaves a choice, the sections
below say how to make it. Write from the rules, not from `git log`, whose older messages may predate them.

The examples below come from an imagined shop, whose modules are `billing`, `importer`, `calendar`, `catalog` and
`checkout`, so that none of them reads as a fact about this repository; its own scopes are those of "A commit scope
names where the change belongs".

## Draw the commits

Each commit holds one reason to change ("Commits"), so that a reader can review it, revert it or find it with
`git bisect` on its own.

- **A subject that needs an "and"** usually holds two commits. Two unrelated fixes made the same afternoon are two
  commits.
- **The test that pins a fix** goes in the commit of the fix, since every commit passes the checks of the areas it
  touches on its own (`CLAUDE.md` > Workflow, "Commits").
- **A correction to an earlier commit of the branch** is folded into it, as `.claude/skills/pull-request/SKILL.md` >
  Shape the history shows. The history describes the change that ships, not the path that found it.

## Choose the type

Take the type of the commit's dominant intention. When two seem to fit:

| The change | Type | Not |
|---|---|---|
| Restores the behavior that was intended | `fix` | `feat`, even when the fix adds code |
| Adds behavior that a user or a caller can observe | `feat` | `fix` |
| Restructures, renames or moves code without changing its behavior | `refactor` | `perf`, unless a measurement motivates it |
| Changes only the layout of the code, such as a formatter's output | `style` | `refactor` |
| Makes the code faster or leaner, as a measurement shows | `perf` | `refactor` |
| Draws a module boundary or a layer, or adds a module | `refactor`, or `feat` when it brings new behavior | `chore` |
| Adds or extends the tests of behavior that already works | `test` | `fix`, whose commit carries the test that pins it |
| Documents, guides and agent guidance | `docs` | `chore` |
| The CI workflows | `ci` | `build`, `chore` |
| The build, the packaging, the dependencies and the tools' configuration, the gate included | `build` | `ci`, `chore` |
| Undoes an earlier commit | the type of what the undoing does, such as `fix` when the undone commit broke something | `chore` |
| The repository's own files that are neither documents nor build, such as the license or `.gitignore` | `chore` | `build`, `docs` |

A breaking change keeps the type of what it does, and "Commits" says how its header shows it. The type matters beyond
the log: `scripts/release.py` drafts the release notes from the features, the fixes and the breaking changes, and
chooses the next version from them, so a feature typed `refactor` never reaches the notes.

## Choose the scope

Take the scope as `CLAUDE.md` > Workflow, "A commit scope names where the change belongs" says. Where it leaves a doubt:

- **A document of one unit,** such as `docs/API.md` for the api, takes the unit's scope, not `docs`.
- **A test** takes the scope of the code it pins.
- **A dependency** takes the scope of the unit whose manifest or lock declares it.
- **A new unit** takes its own name, and a new module of a unit the unit's.
- **A rule changed together with the skills, agents and documents that follow it** takes `rules`: the rule owns the
  decision.

## Write the subject

Picture a reader scanning `git log --oneline` for the commit that changed a behavior. The subject is what they read, and
it decides whether they open the commit. Tell them what the change achieves, which only you know: the diff already shows
the mechanism and the files. What does not fit goes in the body. A revert gets a header of this form too, not the
`Revert "…"` that `git revert` writes.

💩 The mechanism, or nothing at all:

```
fix(billing): fix payment bug
fix(billing): add a retry around chargeCard
feat(billing): update invoice.ts and charge.ts
fix(billing): Fixed the timeout error.
```

❤ The intent:

```
fix(billing): never charge a card twice when the provider times out
fix(importer): say which row broke instead of rejecting the whole file
feat(calendar): read recurring events that end on a date
refactor(catalog): compute a price in one place instead of three
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

Under `fix(billing): never charge a card twice when the provider times out`:

💩 The diff, told again:

```
Add an idempotency key to chargeCard and retry on timeout. Update the
billing tests accordingly.
```

❤ The context that led there:

```
Under load, the payment provider accepts a charge and times out before
it replies. The client took the timeout for a refusal and charged again
on its next attempt, so a customer could pay twice for one order.

An idempotency key sent with each charge lets the provider recognize
the retry and return the first result. A longer timeout would only have
made the double charge rarer, never impossible.
```

## Add the footer

Write it as `CLAUDE.md` > Workflow, "A commit footer holds only what tools read" says, and never on a guess: a breaking
change only when its users will meet it, an issue only when this commit closes it.

```
feat(checkout)!: return amounts as integer cents

Clients rounded the decimal strings each in their own way, so two
screens could show different totals for the same order. An integer
number of cents leaves no rounding to the client.

BREAKING CHANGE: `amount` is an integer number of cents, no longer a
decimal string. Divide it by 100 to show it.
Closes #42
```

## Check the message

Before committing, read the message against the rules:

1. **The header** follows "Commits", with the type of [Choose the type](#choose-the-type) and the scope of
   [Choose the scope](#choose-the-scope).
2. **The subject** follows "A commit message says why", in its form as in what it says: what the change achieves, not
   the files it touches.
3. **The body** follows the same rule: it says why, and lists nothing that the diff shows. Without one, the change
   really speaks for itself.
4. **The footer** follows "A commit footer holds only what tools read": what the rule requires, nothing that it
   excludes, and nothing untrue.
5. **Nothing private:** the message is published, and a pushed commit cannot be taken back, so it holds no secret and
   nothing that `.claude/rules/repository.md` > What belongs in the repository, > No real document names or > No
   personal information forbids, from a pasted log or a command's output as much as from your own words.

Once committed, the commit passes what "Commits" asks of it: `scripts/check.sh --last-commit`, which checks what the
last commit changes. When you rewrite a branch, `.claude/skills/pull-request/SKILL.md` > Shape the history checks every
commit at once, and the last one on every area.
