# ScanMyLib

Scan books and documents with an Android phone, OCR them on the PC's GPU inside a network-less sandbox, and organize
the results on disk as Markdown and illustrations for AI agents. Start with `docs/foundations.md`, then
`docs/ARCHITECTURE.md`.

## Language

English is the reference language of this repository. Everything committed is written in English: code, identifiers,
comments, documentation, commit messages, file names and UI text. Use American spelling (`color`, `behavior`,
`organize`).

The only exception is the French translation of user-facing UI text. English strings are the reference; their French
translations live only in the translation catalogs: `android/app/src/main/res/values-fr/` for the Android app and
`server/scanmylib/web/static/js/locales/fr.js` for the web UI (its unit tests fail on any untranslated string or on
French outside the catalog). Never write French anywhere else in the repository.

## What belongs in the repository

The repository holds the current state of the project and nothing else. Never commit project-management material:

- status or tracking files;
- decision records;
- roadmaps;
- handoffs;
- meeting or research notes;
- `TODO` comments.

That material lives in `.pm/`, a separate, private Git repository nested at the root and ignored by this one.
`.pm/README.md` describes its layout. At the start of a session, if `.pm/` exists, read `.pm/roadmap.md` and the latest
note in `.pm/handoffs/`.

When a decision changes the project:

- update `docs/foundations.md` to describe the new state;
- log the decision in `.pm/decisions.md`, then commit it in the `.pm/` repository.

## No real document names

No real document or book may be named anywhere in the repository: not in code, tests, fixtures, examples,
documentation or commit messages. This covers titles, authors, file and folder names, and excerpts, and above all
anything seen in the user's library. Use invented placeholders (`Example Book`, `Jane Doe`). This keeps contributors
from leaking the user's private data.

## Security rules

The user's account holds many secrets, and the OCR stack (PaddlePaddle, PaddleOCR, vLLM, model code) is untrusted.

- Install nothing on the host. Builds, tests and tools run in Docker containers; the host's `python3` (standard
  library only) and `curl` are fine. Ask the user before downloading or installing anything new: models, images,
  toolchains or dependencies.
- The `ocr` service keeps `network_mode: none`, a read-only root filesystem, no capabilities, `no-new-privileges`, a
  non-root user, and no host mount besides the read-only `SANDBOX_DIR`, the socket directory and its cache directory.
  Never weaken this; `scripts/verify-sandbox.sh` must pass.
- Untrusted components are downloaded only by the `ocr-setup` container, pinned by version or commit. No Paddle code
  runs with network access.
- Everything the sandbox returns is untrusted data: sizes, names, HTML, Markdown. See `docs/SECURITY.md`.
- Never mount `$HOME` or any secret into a container.

## Engineering principles

- The pipeline is engine-agnostic: the api only knows the sandbox protocol (`docs/OCR_SANDBOX.md`). Never add
  post-processing that compensates for a specific model's mistakes. Keep OCR output as produced, raw LaTeX included,
  and fix display generically.
- Nothing is hard-deleted from the library: deletions go to `LIBRARY_DIR/.trash/`.
- Production is in real use. While developing, never touch the running containers, the library (`LIBRARY_DIR`, the
  user's private documents: do not read their content) or the state directory. Test with your own containers, ports
  and data directories, and remove them afterwards.

## Layout and commands

| Area | Path | Test or run |
|---|---|---|
| OCR sandbox | `ocr/` | `docker run --rm --init --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000 -v "$PWD/ocr:/app:ro" -v "$SANDBOX_DIR:/opt/sandbox:ro" scanmylib-ocr:latest /opt/sandbox/venv-paddle/bin/python -m unittest discover -s /app/tests`; isolation of the running service: `scripts/verify-sandbox.sh` |
| api and web UI | `server/` | `cd server && docker build --target test -t scanmylib-api:test . && docker run --rm --network none --read-only --tmpfs /tmp scanmylib-api:test` |
| Web UI unit tests | `server/scanmylib/web/tests/` | `docker run --rm --network none --read-only --user 1000:1000 -v "$PWD/server/scanmylib/web:/web:ro" node:22-bookworm-slim node --test '/web/tests/*.test.js'` |
| Android app | `android/` | `scripts/build-apk.sh` (tests, release build, lint, offline signing) |
| Deployment | `compose.yaml`, `.env` | `docker compose build api ocr && docker compose up -d api ocr`; full install: `scripts/setup.sh` |
| End to end | `scripts/e2e_test.py` | `scripts/e2e_test.py IMAGE...` against the running stack |

## Safety

- Never run `git clean` with `-ff` at the repository root: a double `-f` deletes nested repositories, including
  `.pm/`.
- Never run `docker system prune`, `docker image prune`, `docker volume prune` or `docker builder prune`: the host runs
  other projects. Remove only the containers and images you created.
