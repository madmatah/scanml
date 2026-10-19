## Purpose

<!-- Why this pull request exists: the need or the problem, in a few sentences. -->

## Proposal

<!-- The solution in broad strokes: what it is made of, not how each line works. If the branch is stacked on another, name its pull request. -->

## Screenshots

<!-- The screens a visible change or fix changes, before and after; a screenshot can also show that a change works, even one that does not touch the UI. They are public: invented data only, never a real library, a phone's screen capture or production. "None" when nothing shows. -->

## How to test

<!-- Steps for the reviewer: what to run, what to try, what to look for. -->

<details>
<summary>How it was tested</summary>

<!-- What the author ran and observed: the tests added, the manual checks. -->

</details>

## Review

<!-- What was reviewed, by whom and how, and what was not: the experts of /expert-review that ran and the findings fixed or answered, the other tools or agents, the manual checks. -->

## Checklist

<!-- Tick an item only once it holds. -->

### Quality

- [ ] Each commit passes `scripts/check.sh --last-commit`, and the last one `scripts/check.sh`, every area.
- [ ] A visible change of the web UI was checked in a browser, and a change to the `ocr` service passes `scripts/verify-sandbox.sh` on the development stack.
- [ ] `/expert-review` ran on the completed branch, every finding is fixed or answered here, and the review section says what was not reviewed.

### History

- [ ] Each commit is atomic, and its message follows `CLAUDE.md` > Workflow: the header of "Commits" with the scope of "A commit scope names where the change belongs", a body that says why unless the change speaks for itself, and a footer as "A commit footer holds only what tools read" says; no `fixup!` commit is left.

### Documentation

- [ ] The documents describe the new state: `docs/foundations.md`, the references of `docs/`, `README.md`, `CLAUDE.md`, `.claude/`.
- [ ] Every external work brought in, including a library shipped in a build, is credited in `CREDITS.md`.

### Hygiene

- [ ] No secret, credential or `.env` file is committed, and no real document name or personal information is committed or written here.
- [ ] No project-management material is committed: status, roadmap, decisions, handoffs, notes, `TODO`.
- [ ] No file is committed by accident: build output, logs, temporary captures, an APK.
- [ ] `VERSION` is unchanged: only a release pull request changes it.
