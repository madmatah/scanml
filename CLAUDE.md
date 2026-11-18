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
`server/scanmylib/web/locales/fr.json` for the web UI, whose checks fail on an untranslated text and on French outside
the catalog. Never write French anywhere else in the repository.

## Project

ScanMyLib scans books and documents with an Android phone, reads them with an OCR engine on the PC's GPU inside a
sandbox without network, and organizes the results on disk as Markdown and illustrations for AI agents. The app, the api
with its web UI, the OCR sandbox and the scripts that install, develop and deploy them are built; accounts, a connector
for agents, exports and search are planned. `docs/foundations.md` explains the stack, the architecture, the repository
layout and the testing approach, with their reasons: read it before changing the architecture, the dependencies or the
tooling. `docs/ARCHITECTURE.md` describes the components, the data flow and the library's layout, `docs/API.md` the HTTP
API, `docs/OCR_SANDBOX.md` the sandbox protocol, and `docs/SECURITY.md` the threat model and the guarantees.

## Project management

Project-management material, such as the status, the roadmap, the decisions, the plans, the handoff notes and research
notes, never lives in this repository, and no file of the repository says where it lives
(`.claude/rules/repository.md`). Each contributor keeps it where they choose, and a session follows its own
instructions on where.

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
  `.claude/worktrees/`, with the type that matches the intention of its main change, among `feat`, `fix`, `refactor`,
  `perf`, `style`, `test`, `docs`, `build`, `ci` and `chore`, started from `origin/main`, or from an unmerged branch
  whose work it needs; a release's branch is `release/vX.Y.Z`. After the merge, remove both: `git worktree remove`,
  then `git branch -D`, since git does not see a rebased branch as merged.
- **In a worktree, its own guidance prevails.** Claude Code also loads the `CLAUDE.md` and the rules of the main
  checkout, which encloses the worktree: those of production's release, which may be older. Where they differ, follow
  the worktree's, which describe the code you change.
- **Parallel sessions:** when several Claude sessions work at the same time, each owns one worktree and its pull
  request, from its plan to its review fixes, and never works in another session's worktree. Review fixes go to a new
  `fixer` agent in that worktree, as `.claude/skills/deliver-branch/SKILL.md` > Review says, never back to the agent
  that wrote the branch, whose context only grows. The coordinating session is the one that started the others, or the
  one the user names.
- **Give searches and explorations to cheaper agents,** on the model and at the effort that
  `.claude/rules/configuration.md` > Claude Code automation gives for the task, through the Agent tool's `model` and
  `effort`. An agent defined in `.claude/agents/` runs as its definition says, unless a procedure sets its model or its
  effort.
- **The development stack:** in a new worktree, run `scripts/dev-env.sh` once. It writes the `.env` of the single
  development slot: project and images `scanmylib-dev`, port 8770, its own data next to production's, a test library,
  and production's OCR models, read-only. `scripts/dev.sh up` then starts the api with the fake OCR, and
  `scripts/dev.sh up --real-ocr` with a second real engine, which takes about 4.4 GB of VRAM while it works: only when
  the change needs it. Stop it with `scripts/dev.sh down` when you are done. One development stack runs at a time, and
  `up` in another worktree takes the slot over. Production owns port 8765.
- **The dev app:** `scripts/build-apk.sh` builds "ScanMyLib (dev)" (`fr.scanmylib.dev`), which installs next to the
  production app, from the Pairing tab of the development stack. The production app is built only by
  `scripts/deploy.sh --apk`.
- **Check a visible change** before calling it done: the web UI in a browser on the development stack, reading its
  console; the app in its screenshot tests (`.claude/rules/tests.md` > Levels). The gate cannot see what is drawn.
- **Show a visible change in its pull request:** a change that a screen of the app or the web UI shows puts screenshots
  of the screens it changes in its pull request, after the change and before it when the base can show the screen, so
  that the reviewer sees it without running it, as `.claude/skills/pull-request/SKILL.md` > Show a visible change
  says.
- **Commits:** commit as you like while the work is in progress: before it is pushed, the branch is rewritten into
  atomic commits that each hold one reason to change and pass `scripts/check.sh --last-commit`, as
  `.claude/skills/deliver-branch/SKILL.md` > Shape the history says, and each message is written with the
  `writing-commits` skill.
- **Run each check once, at its level:** the tests of what you change while you write code, the per-commit check when
  the history is shaped, and the whole gate in the CI, with the tests that the CI skips when the change calls for them,
  as `.claude/skills/deliver-branch/SKILL.md` > Shape the history, "Run each check once, at its level" says.
- **Releases** are pull requests of their own, which the `release` skill prepares (`.claude/rules/releases.md`).
- **A branch reaches `main` only through a pull request whose CI passes.** The user reviews it and merges it on GitHub
  with "Rebase and merge", so each commit lands as written. Never merge into `main` yourself, except a release pull
  request, which the `release` skill merges under the conditions of `.claude/rules/releases.md`.
- **Every branch, however small, is delivered** as `.claude/skills/deliver-branch/SKILL.md` says, and reviewed as
  `.claude/skills/deliver-branch/SKILL.md` > Review says.
- **The session writes the code itself,** as `.claude/skills/implement/SKILL.md` says, and gives it to an implementer
  agent only when the user asks, or when the session's own instructions for a planned piece of work say so: an
  implementer would read again the code that the session read to brief it. Such a piece of work comes planned outside
  this repository ([Project management](#project-management)), and its brief gives the implementer the goal, the
  criteria and its slice of the plan.

## Commands

- `scripts/check.sh [AREA...]`: the gate, whose areas `README.md` > Development lists in the order they run. Given
  areas, it checks only those; `--last-commit`, those that read what the last commit changes, unless the commit already
  passed them. The CI runs it on every pull request; run it yourself only as `.claude/skills/deliver-branch/SKILL.md` >
  Shape the history, "Run each check once, at its level" says.
- `scripts/check.sh --fix`: formats every language and applies the linters' safe fixes: ktlint formats the app in
  place, the other formatters only the files git tracks (`git add` a new file first); read `git diff` before running
  what it changed.
- `scripts/dev-env.sh [--own-sandbox]`, then `scripts/dev.sh up [--real-ocr]`, `status`, `logs`, `down`,
  `build [api|ocr]` and `compose COMMAND...`: the development stack of a worktree, on production's sandbox, read-only,
  or on a sandbox of its own, which `dev.sh up` runs.
- `scripts/build-apk.sh [TASK...]`: the dev app (tests, build, lint and signing), or the Gradle tasks given.
- `scripts/e2e_test.py IMAGE...`: the end-to-end test, which acts like the phone against the stack of the checkout's
  `.env`, and refuses production without `--production`.
- `scripts/verify-sandbox.sh`: the isolation of the running `ocr` service.
- `scripts/release.py`: the next release, why, and the draft of its notes; the `release` skill runs it.
- For the user, in the main checkout: `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh [--apk] [--new-sandbox]`;
  `scripts/prod.sh compose COMMAND...`; `scripts/setup.sh` for a first installation.

## Rules

Each file of `.claude/rules/` holds the rules of one concern, in full. Claude Code loads a file with `paths` when you
read or edit a file that matches them, but a subagent in its own worktree or a compacted session can miss that load:
read the file before you do what its line says.

- `repository.md`: loaded in every session.
- `conventions.md`: for any code, test or configuration, scripts and the commands of Claude Code settings included.
- `python.md`: for any Python file.
- `kotlin.md`: for the app's Kotlin, Gradle scripts and resources.
- `web.md`: for the web UI.
- `bash.md`: for any shell script.
- `architecture.md`: for any source code, test or build file, and before adding a dependency.
- `configuration.md`: for a build file, a lock, a Dockerfile, `compose.yaml`, CI, the configuration of a formatter,
  linter or type checker, Claude Code settings, skills or agents, before adding or upgrading a dependency, even with a
  command that edits no file you read, and before giving a task to an agent or making a web request.
- `sandbox.md`: for the OCR sandbox, `compose.yaml`, a Dockerfile, `.env.example`, the scripts, the `running-tests`
  skill, the app's manifest, the vulnerability scan's workflow, and the api's code that reads the sandbox's results.
- `releases.md`: for `VERSION`, `CHANGELOG.md`, and the release and deployment scripts, workflow and skill.
- `tests.md`: for any test, test support or test framework configuration, and before fixing a bug, since the fix starts
  with a test.
- `documents.md`: for any document or agent guidance, and any reference to a document, tool messages included.
