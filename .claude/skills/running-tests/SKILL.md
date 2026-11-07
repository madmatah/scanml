---
name: running-tests
description: Picks and runs the tests that a change to ScanMyLib needs, the gate's areas and the tests the gate skips, such as the OCR sandbox's unit tests with the engine's environment, the sandbox's isolation and the end-to-end test. Use when running or checking the tests of a change, before calling a change done, after changing the OCR sandbox, its service or the flow from the phone to the library, or when the user asks to test a change.
---

# Running tests

`CLAUDE.md` > Workflow, "Run each check once, at its level" says which checks run when, and `.claude/rules/tests.md` >
Levels where each level of tests lives. This skill picks the tests a change needs and runs them, from the branch's
worktree, `<worktree>` below: every command starts with `cd <worktree> &&`, as `.claude/rules/configuration.md` > Claude
Code automation, "An agent given a worktree works only there" says, so that no command runs on production's `.env`
(`CLAUDE.md` > Production).

## The gate

- **While you work,** a fix included, run the tests of what you change, and only them: those of the areas that the
  change touches, `cd <worktree> && scripts/check.sh AREA...`, the areas of `CLAUDE.md` > Commands, or, within them,
  only the test files of what you change.
- **When the history is shaped,** `cd <worktree> && scripts/check.sh --last-commit` checks every commit once, on the
  areas that read what it changes, as `.claude/skills/develop/SKILL.md` > Shape the history shows, and skips a commit
  that already passed it.
- **The CI runs the whole gate** on every pull request. Run `cd <worktree> && scripts/check.sh` yourself only when the
  change touches the gate itself, as `CLAUDE.md` > Workflow, "Run each check once, at its level" says.

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

A change to an engine's libraries or to its worker also passes the check of the engine's environment, in the real
sandbox of the development stack, started as [A change to the `ocr` service](#a-change-to-the-ocr-service) says:
`cd <worktree> && scripts/dev.sh compose exec -T ocr python3 -m scanmylib_ocr.engine_environment 2>&1 | cat -v`,
which prints `ok: …` and exits 0. Its output is the sandbox's, untrusted: without a terminal (`-T`) and through
`cat -v`, no control sequence of it reaches the session's terminal.

### A change to the `ocr` service

A change to its isolation, its container in `compose.yaml` or its `Dockerfile` passes
`cd <worktree> && scripts/verify-sandbox.sh` against the running service, then the check of the engine's environment
in its new image, as [A change under `ocr/`](#a-change-under-ocr) runs it. Start the real sandbox first, with
`cd <worktree> && scripts/dev.sh up --real-ocr`, which builds its image: the fake that `scripts/dev.sh up` runs skips
the checks of the sandbox's own directories and runs no engine. Stop it when you are done, as `CLAUDE.md` > Workflow,
"The development stack" says.

### A change to the sandbox's setup

A change to what installs the sandbox, `ocr/setup/` or the packages of `ocr/Dockerfile`, is tested on a sandbox that it
installs, never on production's, which the development stack only reads. Give the development stack a sandbox of its
own, then install the new one there as a deployment would, with a rehearsal of `scripts/deploy.sh --new-sandbox`
(`README.md` > Updating):

1. Ask the user first, as `.claude/rules/configuration.md` > Dependencies says: an installation downloads about 16 GB,
   takes about an hour, and needs 36 GiB free next to the sandbox (`README.md` > Updating).
2. `cd <worktree> && scripts/dev-env.sh --own-sandbox`, which points `SANDBOX_DIR` at `<DATA_DIR>/sandbox`, inside the
   stack's own `DATA_DIR`. To compare with today's sandbox, or to rehearse a rollback, copy production's into it first,
   which only reads it: `cd <worktree> && cp -a --reflink=auto <production's SANDBOX_DIR>/. <DATA_DIR>/sandbox/`.
3. Commit the change, since a rehearsal builds and installs the commit, then run
   `cd <worktree> && SCANMYLIB_DEPLOY_REHEARSAL=scanmylib-dev scripts/deploy.sh --dry-run --new-sandbox`, and the same
   without `--dry-run`. Add `--first-install` to both while the development stack has no database,
   `<DATA_DIR>/state/scanmylib.db`, which its first `scripts/dev.sh up` creates.
4. On the new sandbox, run [A change to the `ocr` service](#a-change-to-the-ocr-service), the unit tests of
   [A change under `ocr/`](#a-change-under-ocr), and the end-to-end test of
   [A change to the flow from the phone to the library](#a-change-to-the-flow-from-the-phone-to-the-library).

If the installation fails, read its log, `<DATA_DIR>/sandbox.new/setup.log`, with
`cd <worktree> && cat -v <that path>`, since what a package prints is untrusted, and only once
`cd <worktree> && test -f <that path> && test ! -L <that path>` passes: the installation writes it, and a link there
would show a file of the host. Before a path under `DATA_DIR` is removed, such as a leftover `sandbox.new` or a
`sandbox.replaced-<time>` no longer needed, build it from `DATA_DIR` as
`cd <worktree> && scripts/lib/stack.py env .env` prints it, never typed by hand, and check it against production's
paths and the mounts of production's containers, as `scripts/deploy.sh` does, with an empty list when production has
no container, since `docker inspect` fails without one:

```bash
cd <worktree> \
  && ids=$(docker ps --all --quiet --filter label=com.docker.compose.project=scanmylib) \
  && { if [[ -n $ids ]]; then docker inspect $ids; else echo '[]'; fi; } \
  | scripts/lib/stack.py check-paths NAME=PATH
```

Keep the new sandbox: the release tests on it (`.claude/skills/release/SKILL.md` > Test the sandbox with its engine).
`scripts/dev-env.sh` without the option goes back to production's sandbox, read-only.

### A change to the flow from the phone to the library

A change to the upload, the reading of the pages or what the api writes in the library passes
`cd <worktree> && scripts/e2e_test.py IMAGE...` against the development stack, which it targets by default: start it
first with `cd <worktree> && scripts/dev.sh up`, and stop it when you are done. Give it photos of invented pages, never
a page of the user's library (`CLAUDE.md` > Production).
