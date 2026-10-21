---
name: running-tests
description: Picks and runs the tests that a change to ScanMyLib needs, the gate's areas and the tests the gate skips, such as the OCR sandbox's unit tests with the engine's environment, the sandbox's isolation and the end-to-end test. Use when running or checking the tests of a change, before calling a change done, after changing the OCR sandbox, its service or the flow from the phone to the library, or when the user asks to test a change.
---

# Running tests

`CLAUDE.md` > Workflow, "Commits" says which checks each commit passes, and `.claude/rules/tests.md` > Levels where each
level of tests lives. This skill picks the tests a change needs and runs them, from the branch's worktree, `<worktree>`
below: every command starts with `cd <worktree> &&`, since the shell may be back in the main checkout, production's
(`CLAUDE.md` > Production).

## The gate

- **While you work,** run the areas that the change touches: `cd <worktree> && scripts/check.sh AREA...`, the areas of
  `CLAUDE.md` > Commands.
- **Once committed,** `cd <worktree> && scripts/check.sh --last-commit` runs the areas that read what the last commit
  changes. Before
  pushing, check every commit as `.claude/skills/pull-request/SKILL.md` > Shape the history shows.

## What the gate skips

The gate runs without network, models, GPU or a running stack, so the tests that need one run apart. Run each one that
the change calls for, on the development stack of the worktree, which `scripts/dev-env.sh` set up (`CLAUDE.md` >
Workflow, "The development stack").

### A change under `ocr/`

The sandbox's unit tests that need an engine's environment skip in the gate. Run them in the sandbox's image, with the
environment that the development stack's `SANDBOX_DIR` holds, read-only and without network:

```sh
cd <worktree> && scripts/dev.sh build ocr && SANDBOX_DIR=$(sed -n 's/^SANDBOX_DIR=//p' .env) &&
    docker run --rm --init --network none --read-only --tmpfs /tmp --cap-drop ALL \
    --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" \
    -v "$PWD/ocr:/app:ro" -v "$SANDBOX_DIR:/opt/sandbox:ro" scanmylib-dev-ocr:latest \
    /opt/sandbox/venv-paddle/bin/python -m unittest discover -s /app/tests
```

### A change to the `ocr` service

A change to its isolation, its container in `compose.yaml` or its `Dockerfile` passes
`cd <worktree> && scripts/verify-sandbox.sh` against the running service. Start the real sandbox first, with
`cd <worktree> && scripts/dev.sh up --real-ocr`: the fake that `scripts/dev.sh up` runs skips the checks of the
sandbox's own directories. Stop it when you are done, as `CLAUDE.md` > Workflow, "The development stack" says.

### A change to the flow from the phone to the library

A change to the upload, the reading of the pages or what the api writes in the library passes
`cd <worktree> && scripts/e2e_test.py IMAGE...` against the development stack, which it targets by default: start it
first with `cd <worktree> && scripts/dev.sh up`, and stop it when you are done. Give it photos of invented pages, never
a page of the user's library (`CLAUDE.md` > Production).
