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
`roadmap.md`, the latest note in its `handoffs/`, and the plan of the branch you work on, in its `plans/`.

When a decision changes the project, log it in the `decisions.md` of `.pm/`, then commit and push it in that repository.
When sessions run in parallel, hand it to the coordinating session instead ([Workflow](#workflow)).

The plan of a branch is `plans/<branch>.md` in `.pm/`, at the path above even from a worktree. Commit and push it there
each time the `plan-critic` agent finds a version of it ready. When sessions run in parallel, each writes the plan of
its own branch and names it in its final report, and the coordinating session commits it.

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
- **Plan before writing code:** a `planner` agent writes the plan of each piece of work, kept in `.pm/` ([Project
  management](#project-management)), and a `plan-critic` agent, which did not write it, checks it against the code and
  the rules before any code is written. Only a change that leaves the design as it is goes without a plan: a typo, a
  mechanical rename, a dependency bump, a bug fix inside one function. A review fix stays within the plan: only a
  change of design goes back to it. The code follows the plan: an implementation that finds it wrong stops and says
  why, and the plan is revised and checked again before the work goes on.
- **Parallel sessions:** when several Claude sessions work at the same time, each owns one worktree and its pull
  request, from its plan to its review fixes, and never works in another session's worktree. Only the coordinating
  session, the one that started the others or the one the user names, writes to `.pm/`, apart from the plan of each
  session's own branch: the others put their decisions and handoff notes in their final report.
- **Give searches and explorations to cheaper agents,** on the model and at the effort that
  `.claude/rules/configuration.md` > Claude Code automation gives for the task, through the Agent tool's `model` and
  `effort`. An agent defined in `.claude/agents/` runs as its definition says, unless a procedure raises or lowers its
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
- **Commits:** commit as you like while the work is in progress. Before pushing, rewrite the branch into atomic commits
  that each hold one reason to change, with its tests and documents, and pass `scripts/check.sh --last-commit`, the
  areas it touches; the last one passes `scripts/check.sh`. The header of a message follows Conventional Commits,
  `<type>(<scope>): <subject>`, with a type among `feat`, `fix`, `refactor`, `perf`, `style`, `test`, `docs`, `build`,
  `ci` and `chore` (`style` for layout only, such as a formatter's): `fix(android): resume uploads once back online`.
  A scope that would only repeat the type is left out, as in `ci: pin the checkout action`, and a breaking change adds
  `!` before the colon: `feat(scripts)!: deploy only published releases`.
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
- **Review before pushing:** run `/expert-review` on the branch, and fix each finding in the commit it belongs to, or
  answer it in the pull request; then review the fixes once more, alone, with the experts of their domains: a round
  that leaves only nits ends the review, and the pull request names the fixes no expert reviewed. The review changes no
  code.
- **Releases** are pull requests of their own, which the `release` skill prepares (`.claude/rules/releases.md`).
- **A branch reaches `main` only through a pull request whose CI passes.** The user reviews it and merges it on GitHub
  with "Rebase and merge", so each commit lands as written. Never merge into `main` yourself.
- **The `pull-request` skill holds the procedure:** starting a branch, planning its work and writing its code, stacking
  it on another, shaping its history, reviewing it, opening and updating its pull request, showing a visible change in
  it, and reviewing someone else's.

## Commands

- `scripts/check.sh [AREA...]`: the gate, in this order: `lint` (Ruff, mypy, zizmor, ShellCheck, shfmt and Biome),
  `scripts` (unit tests of the scripts), `web` (the web UI's unit tests), `server` (the api's tests), `ocr` (the
  sandbox's unit tests, no models), `android` (the app's tests, lint and ktlint), `integration` (integration tests
  of the scripts). Given areas, it checks only those; `--last-commit`, those that read what the last commit changes.
- `scripts/check.sh --fix`: formats every language and applies the linters' safe fixes: ktlint formats the app in
  place, the other formatters only the files git tracks (`git add` a new file first); read `git diff` before running
  what it changed.
- `scripts/dev-env.sh`, then `scripts/dev.sh up [--real-ocr]`, `status`, `logs`, `down`, `build [api|ocr]` and
  `compose COMMAND...`: the development stack of a worktree.
- `scripts/build-apk.sh [TASK...]`: the dev app (tests, build, lint and signing), or the Gradle tasks given.
- `scripts/e2e_test.py IMAGE...`: the end-to-end test, which acts like the phone against the stack of the checkout's
  `.env`, and refuses production without `--production`.
- `scripts/verify-sandbox.sh`: the isolation of the running `ocr` service.
- `scripts/release.py`: the next release, why, and the draft of its notes; the `release` skill runs it.
- For the user, in the main checkout: `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh [--apk]`;
  `scripts/prod.sh compose COMMAND...`; `scripts/setup.sh` for a first installation.

## Rules

Each file of `.claude/rules/` holds the rules of one concern, in full. Claude Code loads a file with `paths` when you
read or edit a file that matches them, but a subagent in its own worktree or a compacted session can miss that load:
read the file before you do what its line says.

- `repository.md`, loaded in every session: what belongs in the repository, no real document names, no personal
  information, and how external work is credited.
- `conventions.md`, loaded in every session: naming and the allowed acronyms, units, comments, characters a reader
  cannot see, and input from outside the program.
- `python.md`, for any Python file: layout, casing, typing, plain data, errors, internal names, async code, idioms and
  directives.
- `kotlin.md`, for the app's Kotlin, Gradle scripts and resources: layout, casing, null safety, immutability, closed
  sets, coroutines, Compose, idioms and directives.
- `web.md`, for the web UI: TypeScript and React, which it moves to, and JavaScript until then.
- `bash.md`, for any shell script: strict mode, logic in Python, quoting, `.env` files, errors and temporary files.
- `architecture.md`, for any source code, test or build file, and before adding a dependency: layers, ports and wiring,
  responsibilities, stored and shared data, SOLID and organization.
- `configuration.md`, for a build file, a lock, a Dockerfile, `compose.yaml`, CI, the configuration of a formatter,
  linter or type checker, Claude Code settings, skills or agents, before adding or upgrading a dependency, even with a
  command that edits no file you read, and before giving a task to an agent: the units, dependencies and what pins them,
  continuous integration, checks and Claude Code automation, the model and the effort of each agent included.
- `sandbox.md`, for the OCR sandbox, `compose.yaml`, a Dockerfile, `.env.example`, the scripts, the app's manifest, and
  the api's code that reads the sandbox's results: the sandbox's isolation, containers and the host, and what keeps
  development stacks from production.
- `releases.md`, for `VERSION`, `CHANGELOG.md`, and the release and deployment scripts and workflow: what a release is,
  who changes `VERSION`, and what production runs.
- `tests.md`, for any test, test support or test framework configuration, and before fixing a bug, since the fix starts
  with a test: the structure of a test file, writing a test, levels, test support and each test framework.
- `documents.md`, for any document or agent guidance, and any reference to a document, tool messages included: present
  tense, where each statement lives, references by heading, rules files, expert reviewers, skills and the pull request
  template.

## Skills

- `pull-request`: from a new branch to a merged pull request, and reviewing someone else's.
- `expert-review`: `/expert-review [<pr#>|<branch>|<range>] [--fixes <file>] [--post] [focus]`, the review of a diff
  before `main`.
- `release`: `/release [major|minor|patch]`, the pull request of a new release, which a workflow publishes once merged.
- `writing-commits`: the message of a commit, from its type and its scope to its body and its footer.
- `running-tests`: the tests a change needs, the gate's and those it skips, and how to run them.
- `clean-pr-screenshots`: `/clean-pr-screenshots`, the maintainer's deletion of the published screenshots.
