# ScanMyLib — Foundations

This document explains the design of ScanMyLib and the reasons behind it: the stack, the architecture, the repository
layout and the testing approach. The rules that follow from it live in `.claude/rules/`, indexed in `CLAUDE.md`, and the
procedures in `.claude/skills/`. The references of `docs/` describe the parts in detail: `ARCHITECTURE.md` the
components, the data flow and the library's layout, `API.md` the HTTP API, `OCR_SANDBOX.md` the sandbox protocol, and
`SECURITY.md` the threat model and the guarantees.

## The project

ScanMyLib scans documents and books with an Android phone, a few pages at a time, in any order and over many sessions;
reads them with an OCR engine on a Linux PC with an NVIDIA GPU; and keeps a library of Markdown files with their
illustrations, which AI agents read as reference material. The app, the api with its web UI, the OCR sandbox and the
scripts that install, develop and deploy them are built. Accounts with tokens per user, a connector through which agents
read and write the library, exports in defined formats and a search of the library are planned.

These constraints drive the choices in this document:

| Constraint | Consequence |
|---|---|
| The OCR stack (PaddlePaddle, PaddleOCR, vLLM and model code) is untrusted, and the user's account holds many secrets | The engine runs in a container without network, privileges or access to the user's files, and its output is untrusted data ([The OCR sandbox](#the-ocr-sandbox)) |
| Nothing is installed on the host | Every build, test and service runs in Docker containers; heavy data (environments, models, the Android toolchain) lives under `DATA_DIR`, outside the repository |
| The library holds the user's private documents, and the repository is public | No real document name and no personal information in the repository; nothing is hard-deleted from the library |
| Pages arrive in any order, over many sessions, from a phone that is often away from the PC | The phone keeps every page until the PC has it, every create is idempotent (ids made by the client), and the reading order comes from the printed page numbers |
| The output is read by agents | Markdown with page markers, illustrations as files, indexes of the library, and OCR output kept as the engine produced it |
| Production runs on the developer's machine, in real use | A development stack and app run beside it, kept from it by the guards of the scripts, and production changes only by deploying a published release |
| One GPU, shared with other work | The engine loads with the first page and unloads after a delay without pages |

## Technology stack

| Tool | Version | Role |
|---|---|---|
| Docker Engine, Docker Compose v2 | — | Every service, build and test; the stacks are compose projects |
| NVIDIA Container Toolkit (CDI) | — | The GPU in the sandbox, as a CDI device |
| Python | 3.12 | The api, the OCR sandbox and the scripts (the host's `python3`, standard library only, for the scripts) |
| FastAPI, Uvicorn | 0.143.0, 0.54.0 | The api's HTTP server and routes |
| SQLite | the Python build's | The api's state: documents, pages, web sessions |
| Pillow | 12.3.0 | Decoding, re-encoding and thumbnails of scans and illustrations |
| markdown-it-py, nh3 | 4.2.0, 0.3.7 | HTML previews of the Markdown, and their allowlist sanitizer |
| HTTPX | 0.28.1 | The api's client of the sandbox, over its Unix socket |
| qrcode | 8.2 | The QR codes of pairing |
| pytest | 9.1.1 | The api's tests |
| Ruff, mypy | 0.16.10, 2.4.0 | Formatting and lint of the Python, and its types, strict |
| JavaScript (ES modules) | the browser's | The web UI, loaded as it is, without a build step |
| KaTeX | 0.19.0 | Typesetting of the LaTeX formulas in the web UI, vendored |
| Node.js | 22 | The web UI's unit tests (`node --test`) |
| PaddleOCR, PaddlePaddle | 3.7.0, 3.2.1 | The OCR pipeline: PP-DocLayoutV3 layout analysis, UVDoc unwarping, orientation |
| PaddleOCR-VL-1.6, vLLM | 0.9B, 0.31.0 | The recognition model, served by vLLM inside the sandbox |
| Kotlin, Android Gradle Plugin, Gradle | 2.4.21, 9.4.1, 9.8.1 | The app and its build; `minSdk` 26, `targetSdk` 36 |
| Jetpack Compose | BOM 2026.09.00 | The app's UI |
| Kotlin coroutines, kotlinx.serialization | 1.11.0 | The app's concurrency, and its JSON |
| Room, WorkManager, DataStore | 2.8.5, 2.12.0, 1.2.1 | The app's database, upload queue and settings |
| CameraX, ML Kit document scanner and code scanner | 1.6.2, 16.0.0, 16.1.0 | The app's camera, Google's document scanner and the QR code reader |
| OkHttp, Coil | 5.5.0, 3.6.3 | The app's client of the PC, and its images |
| JUnit | 4.13.2 | The app's unit tests |
| Bash | — | The scripts that install, develop, check and deploy |
| ShellCheck, shfmt | 0.11.0, 3.14.1 | Lint and formatting of the shell scripts |
| ktlint | 1.8.0 | Formatting and lint of the app's Kotlin, in Android Studio's style with trailing commas |
| Biome | 2.5.15 | Formatting and lint of the web UI |
| zizmor | 1.30.1 | Audit of the GitHub workflows |

Notes:

- **CI runs on GitHub Actions** (`.github/workflows/ci.yml`):
  - `scripts/check.sh` runs on every pull request and every push to `main`, one job per area;
  - actions are pinned to full commit SHAs, and the jobs may only read the repository;
  - `.github/workflows/release.yml` publishes a release once its pull request is merged, and is the only workflow that
    writes to the repository: its tag and its GitHub release.
- **The web UI has no build step:** the browser loads its modules as they are, and the api serves them. Its move to
  TypeScript and React, built by a bundler whose output names carry a hash of their content, is planned: those files can
  then be cached for good, and only the page that names them is revalidated, so a browser never mixes the modules of two
  versions.
- **The app is built in throwaway containers** (`eclipse-temurin` with the JDK 21), signed offline with a key kept
  outside the repository, without R8 shrinking.
- **Every language has its formatter and its linter in the gate,** so that a review never discusses layout and the
  tools catch what they can; review checks the rest of the conventions. The tools of the `lint` area run in containers
  without network or privileges, on read-only sources: the Python tools and the api's dependencies, which mypy needs,
  from hashed locks; Biome from the web UI's lockfile; ShellCheck and shfmt from their authors' images, by digest.
  ktlint runs through Gradle in the app's build container, with its network and its writable `android/`, and Gradle's
  verification metadata checks it as it checks the app's dependencies. `scripts/check.sh --fix` runs the other
  formatters on a copy of the tracked files they format in `server/`, `ocr/` and `scripts/` (never a vendored file or a
  lock), and brings back only their changes to those files, so that nothing they create reaches the checkout, where the
  host would run it, and no change reaches a file whose diff a reader could not judge. Biome's
  `noDescendingSpecificity` is off: the stylesheet orders its rules by component, and reordering them to satisfy it
  would change which rule wins.
- **`CLAUDE.md` and `.claude/` are the agent guidance** ([Agent guidance](#agent-guidance)).

## Architecture

### Principles

The project follows Clean Architecture: the rules live in a pure domain at the center, and each technology stays at the
edge, behind an interface that an inner layer owns. `.claude/rules/architecture.md` states the rules. The code written
before them keeps its layout until it is restructured: the api's restructuring is planned first, then the app's, and the
web UI's comes with its move to TypeScript and React; none is planned yet for the OCR sandbox.

- **The domain is pure,** so it runs anywhere the language runs, and its tests need no I/O, no network and no framework.
  The rules of page numbering and of the reading order are its heart.
- **The application reaches the outside world only through its ports,** declared in its own vocabulary, so its tests run
  it on fakes, and each technology stays one implementation among possible others.
- **Composition roots wire by hand,** so the whole graph sits in one place and the types check it. A DI container would
  resolve it at run time, by tokens.
- **What is stored or shared is plain data,** so it saves, travels and replays as it is.
- **SOLID applies to modules, functions and types,** so a new case is added beside the others, without rewriting them.
- **The pipeline is engine-agnostic.** The api knows the engine only through the sandbox protocol, its OCR port, so a
  better engine replaces the current one by implementing a new worker, and no code compensates for one model's mistakes:
  what one model needs, another would break.
- **The library is the product.** Each document is a folder with `document.md` (its pages in reading order), a Markdown
  file per page, the cropped illustrations, the raw OCR results and the original scans; `INDEX.md` and `library.json`
  list the documents. Nothing is hard-deleted, so that a mistake never loses a scan that may exist nowhere else:
  deletions move to `.trash/`.
- **The phone works offline first.** It keeps every page until the PC has it, retries on its own, and makes the ids of
  what it creates, so that a retry never duplicates a page.

### The OCR sandbox

The OCR engine runs in the `ocr` container: no network interface besides loopback, a read-only root filesystem, no
capabilities, a non-root user, and no host file but its models (read-only), its socket and its cache. The api talks to
it through a Unix socket, with the protocol of `docs/OCR_SANDBOX.md`. Its packages and models are downloaded once, by
the `ocr-setup` container, pinned by version or commit, so that no Paddle code ever runs with network access. Whatever
it returns is checked, re-encoded and sanitized before it reaches the library or a browser. `.claude/rules/sandbox.md`
states the rules, and `docs/SECURITY.md` the threat model, the guarantees and the residual risks.

### Design choices

| Topic | Choice |
|---|---|
| OCR engine | PaddleOCR-VL-1.6 (PP-DocLayoutV3 layout and the 0.9B vision-language model), served by vLLM inside the sandbox |
| GPU use | the engine starts on the first page and unloads after 300 s without pages; ~4.4 GB of VRAM while loaded |
| OCR options | page orientation detection always on; unwarping of curved pages on by default for books; footnotes and sidebars kept in the Markdown |
| Formulas | kept as LaTeX in the Markdown, and typeset by KaTeX in the web UI |
| Page order | a page is placed by its manual position, else its effective page number (roman front matter before arabic pages), else next to its neighbors in the same capture session, else at the end; a manual reordering stores positions only for the pages moved |
| Phone capture | Google's ML Kit document scanner (retouching off by default), the app's own camera (one original photo per tap), or photos imported from the gallery, from the app or shared to it by another app (only what that app's provider grants) |
| App updates | offered by the paired PC (`/api/health` describes the APK it publishes), checked when the library shows or is refreshed, at most once an hour, again once the library reaches the PC after a failed check, and from the settings; the app downloads the APK from that PC, checks its digest, package, version and signing certificate (where Android reports it), and hands it to Android's installer, which asks the user each time |
| Pairing and access | a random bearer token, shared by QR code; plain HTTP on the local network; remote use through a VPN |
| Deployment | Docker Compose (`api`, `ocr`), restarted automatically with Docker; no official instance: each installation deploys the releases it chooses, with `scripts/deploy.sh` |
| Releases | one version for the api and the app (`VERSION`), so that the app a PC offers always matches its api; a release is a pull request of its own, whose notes are drafted from the Conventional Commits since the last release (`scripts/release.py`) in the Keep a Changelog format, and a workflow publishes it once it is merged, so that a release is reviewed like any change and published by nothing but its merge |
| Development | changes are made in worktrees and tried on a development stack and app (`fr.scanmylib.dev`) beside production; the scripts' guards protect production from misconfiguration, mistakes in a branch and compromised build dependencies, not from a deliberately malicious branch (`docs/SECURITY.md`) |

### Layers and modules

The modules as they are, and the layer each one belongs to, whose directory the restructuring of
[Principles](#principles) moves it into where one is planned. A module that mixes two layers splits along them.

| Unit | Module | Responsibility | Layer |
|---|---|---|---|
| api | `__main__`, `app`, `config` | Entry point, wiring of the services and routes, settings from the environment | Composition root |
| api | `ordering` | Page numbering, reading order, duplicates and coverage of a document | Domain |
| api | `records`, `text` | Typed records and the inputs of library operations; slugs and collation | Domain |
| api | `library`, `ocr_loop`, `publisher`, `debounce` | Documents and pages kept in sync with the library; the single OCR loop; publication of the library files | Application |
| api | `assemble`, `preview` | Rendering of the library files and of the HTML previews | Domain (the rendering) and adapters (the files) |
| api | `db`, `storage`, `export` | SQLite state; the library's files, atomic writes and trash; zip archives | Adapters |
| api | `ocr_client`, `ocr_result` | Client of the sandbox protocol, and validation of its untrusted results | Adapters |
| api | `images`, `sanitize`, `qr`, `clock`, `published_apk` | Pillow, the Markdown sanitizer, QR codes, timestamps, the published APK's metadata | Adapters |
| api | `api/`, `auth`, `middleware` | HTTP routes, authentication, security headers and body limits | Adapters |
| api | `devtools/fake_ocr` | The fake OCR sandbox of the development stack and the tests | Test support |
| web UI | `main.js` | Entry point | Composition root |
| web UI | `lib/order.js`, `lib/reading.js`, `lib/math.js`, `lib/format.js`, `lib/labels.js` | Ordering, reading view, formulas, formatting and labels | Domain |
| web UI | `router.js`, `session.js`, `status.js`, `uploads.js` | Navigation, session, engine status, uploads | Application |
| web UI | `api.js`, `lib/i18n.js`, `lib/dom.js`, `lib/clipboard.js`, `lib/errors.js`, `lib/uuid.js`, `views/`, `components/` | Client of the api, translations, the DOM and its views | Adapters |
| app | `ScanMyLibApplication`, `AppContainer`, `MainActivity` | Entry points and wiring | Composition roots |
| app | `model/`, `library/PageNumbering` | Document kinds, scan sources, scanner modes, the PC's address; page numbering | Domain |
| app | `library/`, `pairing/`, `sync/`, `update/`, `settings/` | The library and its staging area, pairing, the upload queue, app updates, settings | Application, with their technology parts as adapters |
| app | `api/`, `db/`, `diagnostics/`, `ui/` | Client of the PC, Room database, crash reports, Compose screens and view models | Adapters |
| OCR sandbox | `supervisor`, `worker` | The HTTP API on the Unix socket, and the process that runs an engine | Composition roots |
| OCR sandbox | `protocol`, `engines/base` | Messages between supervisor and worker, the interface of an engine | Application |
| OCR sandbox | `manager`, `runtime`, `config`, `gpu`, `client` | Engine lifecycle and page queue, engine processes, settings, GPU readings, a client of the socket | Application and adapters |
| OCR sandbox | `engines/paddleocr_vl`, `engines/images` | PaddleOCR-VL-1.6, and its image handling | Adapters |
| scripts | `lib/stack.py`, `lib/version.py`, `lib/formatting.py`, `lib/common.sh` | The `.env` format, production's checkout and the isolation of a stack; the version of a build; what the gate hands to its formatters and linters, and what comes back; shared shell functions | Tools |
| scripts | `setup.sh`, `dev-env.sh`, `dev.sh`, `build-apk.sh`, `check.sh`, `deploy.sh`, `prod.sh`, `release.py`, `e2e_test.py`, `verify-sandbox.sh`, `vendor-katex.sh` | Install, develop, build the app, check, deploy, operate, release, test end to end, verify the sandbox, vendor KaTeX | Tools |

## Repository layout

### Repository tree

```
scanmylib/
├── .claude/                     # Claude Code: rules, skills and the expert reviewers
├── .github/
│   ├── pull_request_template.md # The body of every pull request, with its checklist
│   └── workflows/               # CI (the gate on every pull request and every push to main), and the release
├── android/                     # The app: Kotlin, Compose, Gradle
├── docs/
│   ├── foundations.md           # This document
│   ├── ARCHITECTURE.md          # Components, data flow, the library's layout, the ordering algorithm
│   ├── API.md                   # The HTTP API of the app and the web UI
│   ├── OCR_SANDBOX.md           # The protocol between the api and the sandbox
│   └── SECURITY.md              # Threat model, guarantees, residual risks
├── ocr/                         # The OCR sandbox: its image, its setup, its supervisor and engines, benchmarks
├── scripts/                     # Install, develop, check, release and deploy; their tests
├── server/                      # The api, and the web UI it serves (scanmylib/web/)
├── .env.example                 # The settings of a stack, with their defaults
├── CHANGELOG.md                 # The notes of each release
├── CLAUDE.md                    # The session manual for AI agents
├── CREDITS.md                   # External work reused, with its terms
├── compose.yaml                 # The services of a stack
├── LICENSE
├── README.md
└── VERSION                      # The last release
```

### Module anatomy

```
server/                          # The api's unit
├── Dockerfile                   # Its images: runtime, and the test target
├── pyproject.toml               # Its direct dependencies, pinned
├── requirements*.lock           # The full set, with hashes
├── scanmylib/                   # Its package; scanmylib/web/ is the web UI it serves
└── tests/                       # Its tests, with pytest
```

Each unit builds in its own container, from its own pinned inputs, so that a unit's dependencies never reach another
one: the api never sees the sandbox's packages, and the sandbox never sees the api's code.

### Enforcement

Each row names a rule, the rules file that states it, and what enforces it.

| Rule | Enforced by |
|---|---|
| The `ocr` service stays isolated (`.claude/rules/sandbox.md` > The OCR sandbox) | `scripts/verify-sandbox.sh`, after every deployment |
| Every stack but production's is checked before docker compose runs it (`.claude/rules/sandbox.md` > Development stacks and production) | `scripts/lib/stack.py`, through `scripts/dev.sh`, `scripts/dev-env.sh`, `scripts/deploy.sh`'s rehearsal and `scripts/build-apk.sh`, and its tests in `scripts/tests/` |
| Production is operated by hand only through `scripts/prod.sh compose` (`.claude/rules/sandbox.md` > Development stacks and production) | `scripts/lib/stack.py check-compose-command --production`, through `scripts/prod.sh` |
| The dev app keeps its own application id (`.claude/rules/sandbox.md` > Development stacks and production) | The signing container of `scripts/build-apk.sh` |
| Production runs published releases only (`.claude/rules/releases.md`) | `scripts/deploy.sh`, `scripts/setup.sh`, `scripts/prod.sh` and `scripts/build-apk.sh` |
| Never weaken what the lockfile or the registry settings guarantee (`.claude/rules/configuration.md` > Dependencies) | `pip --require-hashes`, `npm ci`'s integrity check, Gradle's dependency verification, the image digests of `scripts/check.sh`, the checksums of `scripts/build-apk.sh` and `scripts/vendor-katex.sh` |
| The French translation lives only in the catalogs (`CLAUDE.md` > Language) | The web UI's unit tests; Android lint for missing translations |
| Part of the rules of the Python: PEP 8 at 120 columns, imports, typed signatures with no bare `Any`, no blind `except`, no mutable defaults (`.claude/rules/python.md`), no shell or SQL string built from input (`.claude/rules/conventions.md` > Input from outside the program), and, in part, no character a reader cannot see written as such (`.claude/rules/conventions.md` > Characters a reader cannot see) | Ruff and mypy `--strict`, in `scripts/check.sh lint` |
| Part of the rules of the shell scripts: quoting and `[[ … ]]` (ShellCheck), indentation (shfmt) (`.claude/rules/bash.md`) | ShellCheck and shfmt, in `scripts/check.sh lint` |
| The Kotlin conventions at 120 columns, file names (`.claude/rules/kotlin.md`) | ktlint, in `scripts/check.sh android` |
| The rules of the web UI: layout, `const`, strict equality, named exports (`.claude/rules/web.md`) | Biome, in `scripts/check.sh lint` |
| Part of the rules of continuous integration: actions pinned to commits, the jobs' permissions and credentials, no template injection (`.claude/rules/configuration.md` > Continuous integration) | zizmor, in `scripts/check.sh lint` |
| Every rule no tool can check: architecture, conventions, tests as specification… | `/expert-review` ([Code review](#code-review)), before every pull request |

## Conventions

### Code conventions

The conventions serve one aim: the code explains itself, so that it needs no comments, and a reviewer can check it
against the domain. `.claude/rules/conventions.md` states them, and a rules file per language adds its own.

- **Names carry the meaning** that comments may not carry, in the vocabulary of the domain. A unit spelled out in a name
  makes a unit error visible where it is written.
- **Comments only say why.** The names say what the code does, and the tests state the business rules ([Tests document
  the rules](#tests-document-the-rules)).
- **Acronyms are written as words in the four languages,** even where Python's or Kotlin's own conventions would
  capitalize them, so that a concept is spelled the same in the api, the web UI and the app.
- **A name outside the program keeps its spelling,** such as a variable of `.env` or a field of the API, because
  installations, phones and agents depend on it.

### Git

`CLAUDE.md` > Workflow says how a session works. The reasons behind it:

- **A worktree per piece of work** keeps parallel sessions from changing each other's files, and keeps work in progress
  out of the main checkout, which holds production's release. The worktrees live under `.claude/worktrees/` of the
  main checkout, where `claude --worktree` puts them, at a cost: Claude Code loads the guidance of every directory
  above a session's, so a worktree session also reads the main checkout's, that of production's release, which may be
  older.
- **The main checkout holds production's release, not `main`,** because production runs from it: its containers were
  started there, its `.env` is there, and a deployment builds from its HEAD. Only releases are deployed, since the
  release app's versionCode comes from `VERSION`.
- **A stacked branch** costs only a rebase of its own commits when its base is rewritten, so no work waits for a
  merge.
- **A history rewritten before it is pushed,** into atomic commits whose messages say why, keeps the reasons that a diff
  cannot show. Each commit passing the gate keeps `main` a safe start for any work.
- **A header that says what the change achieves, under the scope it belongs to,** lets a reader find a change in
  `git log --oneline` without opening it, since the diff already lists the files. The release notes that
  `scripts/release.py` drafts are the subjects of the features and fixes, each prefixed with its scope.
- **A footer that holds only what tools read** lets the release tooling and the issue tracker trust it. A trailer naming
  the tool that typed a change would add a line to every message and say nothing of its reason.
- **"Rebase and merge"** lands each commit as written, after the review ([Code review](#code-review)) and CI
  ([Technology stack](#technology-stack)).
- **One writer for `.pm/`,** the coordinating session, keeps its commits from racing.

### Agent guidance

Agents work from four kinds of documents, each with one job, so that a statement has one home and never drifts from a
copy. `.claude/rules/documents.md` > Where a statement lives says what goes where. The reasons:

- **`CLAUDE.md` is the session manual** because Claude Code loads it whole into every session: each line costs every
  session, so it holds only what every session needs.
- **The rules live in `.claude/rules/`** because a file with `paths` loads only with the files it governs, and a rule
  stated there in full, with its reason, needs no second document. A load by `paths` can be missed, by a subagent in its
  own worktree or after a compaction, which is why each file has its line in `CLAUDE.md`.
- **The rules files follow concerns, not directories,** because a concern often spans several directories, where a
  `CLAUDE.md` per directory would scatter its rules. The rules of each language have a file of their own, so that a
  session loads only those of the code it touches.
- **Skills hold procedures** because a procedure matters only while its task runs, and a skill loads only then.
- **This document holds the design and its reasons,** and states no rule, so that a rule changes in one place.
- **The history of a decision lives in `.pm/`**, a private repository nested in the main checkout, so the documents here
  describe only the present, with its reasons.

## Testing

### Tests document the rules

The tests are the specification of the business rules. To learn how a part of the system behaves, read its tests: each
one states one rule, in a sentence, in the vocabulary of the domain. That is why the code carries no comment that states
a rule. `.claude/rules/tests.md` says how tests are written.

### Test levels

- **The unit tests run in the gate,** in containers without network, so that they are fast, need no GPU and can never
  reach production. The api's tests use a fake sandbox that speaks the real protocol on a real Unix socket, so that the
  client and its limits are tested as they run.
- **The tests of the scripts use a stand-in for docker,** because the guards they test must refuse what production owns
  without any container being built or started.
- **The end-to-end test and the isolation check need a running stack,** so they run against the development stack, or
  production after a deployment, outside the gate.
- **The benchmarks need the real engine and the GPU,** so they run by hand, outside the gate.

### Budgets

No budget is set yet. The first one comes with the benchmark that measures it. The measures of `README.md` > OCR engine
and the benchmarks of `ocr/bench/` are the references.

### Code review

Every branch goes through `/expert-review` before its pull request. It is a project skill in
`.claude/skills/expert-review/`, named so that it never shadows the built-in `/code-review`.

- **It runs in its own subagent**, which never saw the code being written, so the review stays independent of the
  session that wrote the code, and that session keeps its context.
- **One expert per domain, in parallel.** Correctness reviews every diff, and conventions every diff that holds code or
  configuration. Architecture, tests, performance, security and documentation join when the diff touches their domain,
  and so do the project's own experts: isolation (the sandbox, the guards of the scripts, the Dockerfiles and
  `compose.yaml`) and Android. Each expert is an agent of `.claude/agents/` on the strongest model, and cannot run a
  command, so that no reviewed text can make it act.
- **The orchestrator confirms every blocking and should-fix finding** before reporting it, and lists the findings it
  dropped with their counter-evidence, so the report makes no claim it has not checked.
- **A target other than the current branch is checked out outside the repository**, so a reviewed `CLAUDE.md` never
  loads as an instruction.
- **Reviews can run at the same time, from the same checkout:** each one keeps its scope in a temporary directory of
  its own.
- **The report ends the review.** It suggests a fix for each finding but applies none: the session that wrote the code
  fixes or answers each one, and the user decides at the merge.

## References

- Clean Architecture, Robert C. Martin: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- PaddleOCR (PaddleOCR-VL, PP-DocLayoutV3): https://github.com/PaddlePaddle/PaddleOCR
- vLLM: https://docs.vllm.ai
- FastAPI: https://fastapi.tiangolo.com
- Android app architecture: https://developer.android.com/topic/architecture
- Jetpack Compose: https://developer.android.com/compose
- ML Kit document scanner: https://developers.google.com/ml-kit/vision/doc-scanner
- KaTeX: https://katex.org
- Conventional Commits 1.0.0: https://www.conventionalcommits.org/en/v1.0.0/
- Keep a Changelog 1.1.0: https://keepachangelog.com/en/1.1.0/
- Semantic Versioning 2.0.0: https://semver.org
