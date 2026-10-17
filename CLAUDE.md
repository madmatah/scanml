# CLAUDE.md

The session manual for AI agents working in this repository: what every session must know and do. Apart from the
language of the repository, the rules about what it holds live in `.claude/rules/`, each once and in full, and
[Rules](#rules) says when to read each file. `docs/foundations.md` explains the design and its reasons, and skills hold
the procedures.

## Language

English is the reference language of this repository. Everything committed is written in English: code, identifiers,
comments, documentation, commit messages, file names, and the text users see. Use American spelling (`color`,
`behavior`, `organize`).

The one exception is the French translation of the text users see. The English text is the reference, and its French
translation lives only in the translation catalogs: `android/app/src/main/res/values-fr/` for the app and
`server/scanmylib/web/static/js/locales/fr.js` for the web UI, whose unit tests fail on an untranslated text and on
French outside the catalog. Never write French anywhere else in the repository.

## Project

ScanMyLib scans books and documents with an Android phone, reads them with an OCR engine on the PC's GPU inside a
sandbox without network, and organizes the results on disk as Markdown and illustrations for AI agents. The app, the api
with its web UI, the OCR sandbox and the scripts that install, develop and deploy them are built; accounts, a connector
for agents, exports and search are planned. `docs/foundations.md` explains the stack, the architecture, the repository
layout and the testing approach, with their reasons: read it before changing the architecture, the dependencies or the
tooling. `docs/ARCHITECTURE.md` describes the components, the data flow and the library's layout, `docs/API.md` the HTTP
API, `docs/OCR_SANDBOX.md` the sandbox protocol, and `docs/SECURITY.md` the threat model and the guarantees.

## Project management

Project-management material lives in `.pm/`, a separate, private Git repository nested at the root of the main checkout
and ignored by this one, never in this repository (`.claude/rules/repository.md`). `.pm/README.md` describes its layout.
Linked worktrees do not have it: from a worktree, it is at
`$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.pm`. At the start of a session, read its
`roadmap.md` and the latest note in its `handoffs/`.

When a decision changes the project, log it in the `decisions.md` of `.pm/`, then commit and push it in that repository.
When sessions run in parallel, hand it to the coordinating session instead ([Workflow](#workflow)).

Never run `git clean` with `-ff` at the repository root: a double `-f` deletes nested repositories, including `.pm/`.

## Production

Production runs on this machine, from the main checkout, `~/Dev/scanmylib`, and is in real use.

- **Never touch it while developing:** not its running containers, not the library (`LIBRARY_DIR`, the user's private
  documents: never read their content), not its state directory. Work on the development stack ([Workflow](#workflow)),
  or with containers, ports and data directories of your own, and remove these afterwards.
- **The main checkout holds production's release** (`git checkout vX.Y.Z`) and production's `.env`. Never develop there
  and never move its HEAD: only fetch there. The scripts recognize it as the directory production's containers were
  started from, or `~/Dev/scanmylib` when none exists; another clone with a copy of its `.env` is not production.
- **Production changes only through `scripts/deploy.sh`,** which the user runs in the main checkout, on a published
  release, and is operated with `scripts/prod.sh compose …`. Never deploy from a worktree, never build the release app
  anywhere else, and never run plain `docker compose`: in a worktree, `scripts/dev.sh build` and
  `scripts/dev.sh compose COMMAND…` check what docker compose resolves before running it.
- **Install nothing on the host,** and download nothing new without the user's approval
  (`.claude/rules/configuration.md` > Dependencies). The containers you start never mount `$HOME` or a secret, and an
  untrusted tool runs in one without network.
- **Review what a branch changes in `scripts/`, `compose.yaml` and the Dockerfiles before running it.** The guards of
  the scripts protect production from misconfiguration, mistakes in a branch and compromised build dependencies, not
  from a deliberately malicious branch, whose scripts run as the user.
- **A `.env` is written by `scripts/setup.sh` or `scripts/dev-env.sh` only:** never copy `.env.example` or production's
  `.env` into a worktree.
- **Never run `docker system prune`, `docker image prune`, `docker volume prune` or `docker builder prune`:** the host
  runs other projects. Remove only the containers and images you created.

## Workflow

- **Each piece of work has its own short-lived branch, `<type>/<topic>`, in its own worktree** under
  `.claude/worktrees/`, started from `origin/main`, or from an unmerged branch whose work it needs; a release's branch
  is `release/vX.Y.Z`. After the merge, remove both: `git worktree remove`, then `git branch -D`, since git does not see
  a rebased branch as merged.
- **In a worktree, its own guidance prevails.** Claude Code also loads the `CLAUDE.md` and the rules of the main
  checkout, which encloses the worktree: those of production's release, which may be older. Where they differ, follow
  the worktree's, which describe the code you change.
- **Parallel sessions:** when several Claude sessions work at the same time, each owns one worktree and its pull
  request, from implementation to review fixes, and never works in another session's worktree. Only the coordinating
  session, the one that started the others or the one the user names, writes to `.pm/`: the others put their decisions
  and handoff notes in their final report.
- **The development stack:** in a new worktree, run `scripts/dev-env.sh` once. It writes the `.env` of the single
  development slot: project and images `scanmylib-dev`, port 8770, its own data next to production's, a test library,
  and production's OCR models, read-only. `scripts/dev.sh up` then starts the api with the fake OCR, and
  `scripts/dev.sh up --real-ocr` with a second real engine, which takes about 4.4 GB of VRAM while it works: only when
  the change needs it. Stop it with `scripts/dev.sh down` when you are done. One development stack runs at a time, and
  `up` in another worktree takes the slot over. Production owns port 8765.
- **The dev app:** `scripts/build-apk.sh` builds "ScanMyLib (dev)" (`fr.scanmylib.dev`), which installs next to the
  production app, from the Pairing tab of the development stack. The production app is built only by
  `scripts/deploy.sh --apk`.
- **Check a visible change in a browser** before calling it done: load the web UI on the development stack, exercise the
  change, and read the console. The gate cannot see what is drawn.
- **Commits:** commit as you like while the work is in progress. Before pushing, rewrite the branch into atomic commits
  that each pass `scripts/check.sh`: one logical change each, with its tests and documents. Messages follow Conventional
  Commits, `type(scope): summary` in the imperative and lowercase, with a type among `feat`, `fix`, `refactor`, `perf`,
  `test`, `docs`, `build`, `ci` and `chore`, and a scope when the change stays in one area: `ocr`, `server`, `web`,
  `android` or `scripts`.
- **A commit message says why.** The subject names the change. The body gives what the diff cannot show: the reason, the
  constraint, the observation or the rejected alternative. A body that restates the diff is noise.
- **Releases** are pull requests of their own, which the `release` skill prepares (`.claude/rules/releases.md`).
- **A branch reaches `main` only through a pull request whose CI passes.** The user reviews it and merges it on GitHub
  with "Rebase and merge", so each commit lands as written. Never merge into `main` yourself.

## Commands

- `scripts/check.sh [AREA...]`: the gate, in this order: `scripts` (the tests of the scripts), `web` (the web UI's unit
  tests), `server` (the api's tests), `ocr` (the sandbox's unit tests, without the models) and `android` (the app's unit
  tests and lint). Given areas, it checks only those. It must pass on every commit you push.
- `scripts/dev-env.sh`, then `scripts/dev.sh up [--real-ocr]`, `status`, `logs`, `down`, `build [api|ocr]` and
  `compose COMMAND...`: the development stack of a worktree.
- `scripts/build-apk.sh [TASK...]`: the dev app (tests, build, lint and signing), or the Gradle tasks given.
- `scripts/e2e_test.py IMAGE...`: the end-to-end test, which acts like the phone against the stack of the checkout's
  `.env`, and refuses production without `--production`.
- `scripts/verify-sandbox.sh`: the isolation of the running `ocr` service.
- The sandbox's unit tests with the engine's environment, which the gate skips, for a change under `ocr/`:

  ```sh
  scripts/dev.sh build ocr
  SANDBOX_DIR=$(sed -n 's/^SANDBOX_DIR=//p' .env)
  docker run --rm --init --network none --read-only --tmpfs /tmp --cap-drop ALL \
      --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" \
      -v "$PWD/ocr:/app:ro" -v "$SANDBOX_DIR:/opt/sandbox:ro" scanmylib-dev-ocr:latest \
      /opt/sandbox/venv-paddle/bin/python -m unittest discover -s /app/tests
  ```
- `scripts/release.py`: the next release, why, and the draft of its notes; the `release` skill runs it.
- For the user, in the main checkout: `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh [--apk]`;
  `scripts/prod.sh compose COMMAND...`; `scripts/setup.sh` for a first installation.

## Rules

Each file of `.claude/rules/` holds the rules of one concern, in full. Claude Code loads a file with `paths` when you
read or edit a file that matches them, but a subagent in its own worktree or a compacted session can miss that load:
read the file before you do what its line says.

- `repository.md`, loaded in every session: what belongs in the repository, no real document names, no personal
  information, and how external work is credited.
- `conventions.md`, loaded in every session: naming and the allowed acronyms, units, comments, and input from outside
  the program.
- `python.md`, for any Python file: layout, casing, typing, plain data, errors, internal names, async code, idioms and
  directives.
- `kotlin.md`, for the app's Kotlin, Gradle scripts and resources: layout, casing, null safety, immutability, closed
  sets, coroutines, Compose, idioms and directives.
- `web.md`, for the web UI: TypeScript and React, which it moves to, and JavaScript until then.
- `bash.md`, for any shell script: strict mode, logic in Python, quoting, `.env` files, errors and temporary files.
- `architecture.md`, for any source code, test or build file, and before adding a dependency: layers, ports and wiring,
  responsibilities, stored and shared data, SOLID and organization.
- `configuration.md`, for a build file, a lock, a Dockerfile, `compose.yaml`, CI, Claude Code settings, skills or
  agents, and before adding or upgrading a dependency, even with a command that edits no file you read: the units,
  dependencies and what pins them, continuous integration, checks and Claude Code automation.
- `sandbox.md`, for the OCR sandbox, `compose.yaml`, a Dockerfile, `.env.example`, the scripts, the app's manifest, and
  the api's code that reads the sandbox's results: the sandbox's isolation, containers and the host, and what keeps
  development stacks from production.
- `releases.md`, for `VERSION`, `CHANGELOG.md`, and the release and deployment scripts and workflow: what a release is,
  who changes `VERSION`, and what production runs.
- `tests.md`, for any test or test support, and before fixing a bug, since the fix starts with a test: writing a test,
  test levels and test support.
- `documents.md`, for any document or agent guidance, and any reference to a document, tool messages included: present
  tense, where each statement lives, references by heading, rules files and skills.

## Skills

- `release`: `/release [major|minor|patch]`, the pull request of a new release, which a workflow publishes once the user
  merges it.
