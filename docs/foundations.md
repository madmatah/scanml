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
| Debian | 13 "trixie" | The base of every Python and Node.js image of the project: the stable release, whose packages Debian's security team fixes |
| Python | 3.12 | The api, the OCR sandbox and the scripts (the host's `python3`, standard library only, for the scripts) |
| FastAPI, Uvicorn | 0.143.0, 0.54.0 | The api's HTTP server and routes |
| SQLite | the Python build's | The api's state: documents, pages, web sessions |
| Pillow | 13.0.0 | Decoding, re-encoding and thumbnails of scans and illustrations |
| markdown-it-py, nh3 | 4.2.0, 0.3.7 | HTML previews of the Markdown, and their allowlist sanitizer |
| HTTPX | 0.28.1 | The api's client of the sandbox, over its Unix socket |
| qrcode | 8.2 | The QR codes of pairing |
| pytest | 9.1.1 | The api's tests |
| Ruff, mypy | 0.16.10, 2.4.0 | Formatting and lint of the Python, and its types, strict |
| TypeScript | 7.0.2 | The web UI's modules, under `src/`, and their tests; `tsc --noEmit` checks their types, strict, and Node runs the tests with its type stripping |
| React, React DOM | 19.3.1 | The web UI's screens, as function components |
| React Router | 8.5.1 | The web UI's navigation, in the URL's fragment (`#/login`), on the browser alone |
| esbuild | 0.28.2 | The build of the web UI, in the api's image and in the gate: one module script and one stylesheet, each named by a hash of its content |
| KaTeX | 0.19.1 | Typesetting of the LaTeX formulas in the web UI, installed from its lockfile and bundled into its script, with its stylesheet and fonts |
| i18next, i18next-browser-languagedetector, react-i18next | 26.7.1, 8.3.0, 17.1.12 | The web UI's translations, with the English text as key and the language the browser prefers, given to its React components |
| Node.js | 26 | The web UI's tools, unit tests (`node --test`) and build, in `node:26-trixie-slim` pinned by digest; never in the api's runtime image |
| pnpm | 12.17.0 | The web UI's package manager: installs its dependencies and tools from its lockfile, under the guards of `pnpm-workspace.yaml` |
| PaddleOCR, PaddlePaddle | 3.7.0, 3.2.1 | The OCR pipeline: PP-DocLayoutV3 layout analysis, UVDoc unwarping, orientation |
| OpenCV (headless build) | 4.10.0.84 | The pipeline's image processing, without the GUI and so without libGL, Mesa and the X libraries; installed under the name of the GUI build that PaddleX requires, through an alias distribution |
| PaddleOCR-VL-1.6, vLLM | 0.9B, 0.31.0 | The recognition model, served by vLLM inside the sandbox |
| Kotlin, Android Gradle Plugin, Gradle | 2.4.21, 9.4.1, 9.8.1 | The app and its build; `minSdk` 26, `targetSdk` 36 |
| Jetpack Compose | BOM 2026.09.00 | The app's UI |
| Kotlin coroutines, kotlinx.serialization | 1.11.0 | The app's concurrency, and its JSON |
| Room, WorkManager, DataStore | 2.8.5, 2.12.0, 1.2.1 | The app's database, upload queue and settings |
| CameraX, ML Kit document scanner and code scanner | 1.6.2, 16.0.0, 16.1.0 | The app's camera, Google's document scanner and the QR code reader |
| OkHttp, Coil | 5.5.0, 3.6.3 | The app's client of the PC, and its images |
| JUnit | 4.13.2 | The app's unit tests |
| Robolectric, Roborazzi | 4.17, 1.76.0 | The app's screenshot tests, which draw its screens on the JVM, and its tests that need Android's framework |
| Bash | — | The scripts that install, develop, check and deploy |
| ShellCheck, shfmt | 0.11.0, 3.14.1 | Lint and formatting of the shell scripts |
| ktlint | 1.8.0 | Formatting and lint of the app's Kotlin, in Android Studio's style with trailing commas |
| Biome | 2.5.15 | Formatting and lint of the web UI |
| i18next-cli | 1.82.4 | The checks of the web UI's translation catalogs: no key missing or unused, every French entry translated, no text of the TypeScript UI outside `t()`, the values of each call matching its placeholders; it parses with `@swc/core`, whose native addon the image of the web tools writes at its build |
| zizmor | 1.30.1 | Audit of the GitHub workflows |
| OSV-Scanner | 2.7.0 | The weekly report of the known vulnerabilities of what GitHub's dependency graph cannot read |
| GitHub CLI (`gh`) | — | The pull requests, and the listing that comes before their screenshots are cleaned up; the release workflow's tag and release |

Notes:

- **CI runs on GitHub Actions** (`.github/workflows/ci.yml`):
  - `scripts/check.sh` runs on every pull request and every push to `main`, one job per area;
  - actions are pinned to full commit SHAs, and every job but the two below may only read the repository;
  - `.github/workflows/release.yml` publishes a release once its pull request is merged, and is the only workflow that
    writes to the repository's contents: its tag and its GitHub release;
  - `.github/workflows/vulnerability-scan.yml` runs OSV-Scanner every week, by hand, and on a push to `main` that
    changes what it scans, and reports to the repository's code scanning what Dependabot cannot see: GitHub's dependency
    graph reads only the api's direct dependencies in `pyproject.toml`, the web UI's lockfile and the actions. It scans
    the OCR sandbox's two environments, which it resolves from their requirements as a new installation would that day,
    and the uv that installs them, the Debian and Python packages of the api's image and of the image the sandbox runs,
    and the locks of the gate's Python tools and of the app's libraries; it scans the web UI's pnpm lockfile too,
    which the graph reads, so that its packages are also checked against OSV's advisories. Its upload job alone
    writes, the security events of code scanning, and runs no command, so that no code the scan resolves, builds or
    runs holds a token that writes. It reports and never blocks a pull request. Its resolution is the day's, while an
    installation holds what resolved the day it was installed.
- **The web UI is built with the api's image:** stages of `server/Dockerfile` install its packages with pnpm, from
  the frozen lockfile and under its guards, then type-check its sources and run its build,
  `server/scanmylib/web/build.ts`, without network; the gate's `web` area runs the same build. esbuild writes one
  script and one stylesheet whose names carry a hash of their content, and the entry page that names them. Those files
  can then be cached for good, and only the page that names them is revalidated, so a browser never mixes the modules
  of two versions. Only the built files reach the runtime image: Node, the packages and the sources stay in the stages
  that build, so that the image production runs carries no toolchain it never uses, nor its advisories.
- **The app is built in throwaway containers** (`eclipse-temurin` with the JDK 21), signed offline with a key kept
  outside the repository, without R8 shrinking.
- **Every language has its formatter and its linter in the gate,** so that a review never discusses layout and the
  tools catch what they can; review checks the rest of the conventions. The tools of the `lint` area run in containers
  without network or privileges, on read-only sources: the Python tools and the api's dependencies, which mypy needs,
  from hashed locks; Biome from the web UI's pnpm lockfile, without any package's install script; ShellCheck and shfmt
  from their authors' images, by digest.
  ktlint runs through Gradle in the app's build container, with its network and its writable `android/`, and Gradle's
  verification metadata checks it as it checks the app's dependencies. `scripts/check.sh --fix` runs the other
  formatters on a copy of the tracked files they format in `server/`, `ocr/`, `scripts/` and `.claude/skills/` (never a
  lock or the script copied from a template), and brings back only their changes to those files, so that nothing they
  create reaches the checkout, where the host would run it, and no change reaches a file whose diff a reader could not
  judge. Biome's `noDescendingSpecificity` is off: the stylesheet orders its rules by component, and reordering them to
  satisfy it would change which rule wins.
- **`CLAUDE.md` and `.claude/` are the agent guidance** ([Agent guidance](#agent-guidance)).

## Architecture

### Principles

The project follows Clean Architecture: the rules live in a pure domain at the center, and each technology stays at the
edge, behind an interface that an inner layer owns. `.claude/rules/architecture.md` states the rules. The api and the
web UI follow them; the code of the other units keeps its layout until it is restructured: the app's restructuring is
planned, and none is planned yet for the OCR sandbox.

- **The domain is pure,** so it runs anywhere the language runs, and its tests need no I/O, no network and no framework.
  The rules of page numbering and of the reading order are its heart.
- **The application reaches the outside world only through its ports,** declared in its own vocabulary, so its tests run
  it on fakes, and each technology stays one implementation among possible others. Only the runtime it runs on goes
  without one in the api, since nothing that a rule reads enters or leaves the program through it.
- **Composition roots wire by hand,** so the whole graph sits in one place and the types check it. A DI container would
  resolve it at run time, by tokens.
- **What is stored or shared is plain data,** so it saves, travels and replays as it is.
- **SOLID applies to functions, types, files and directories,** so a new case is added beside the others, without rewriting them.
- **The pipeline is engine-agnostic.** The api knows the engine only through the sandbox protocol, behind its OCR ports,
  so a better engine replaces the current one by implementing a new worker, and no code compensates for one model's
  mistakes: what one model needs, another would break.
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
the `ocr-setup` container, pinned by version or commit, so that no Paddle code ever runs with network access; a
deployment installs a new sandbox next to the running one, and switches to it at its restart. Whatever
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
| App's look | its own colors, "Paper & Ink" (warm paper neutrals, a teal accent, ocher for what needs a look), the same on every phone, so that the app matches its icon and its colors mean the same for everyone, where the wallpaper's colors (Material You) change with each phone and are an option, off by default; a light and a dark theme, as the phone is or as chosen in the settings; medium- and high-contrast variants, chosen from the phone's contrast setting (Android 14 and later), since a fixed scheme would otherwise ignore it, and checked by a unit test of their contrast ratios; titles in the phone's own serif, so that no font is bundled; states told in words and icons as well as colors, so that they read without color, with TalkBack and at twice the text size; badges and banners only for the states that differ from the normal one, so that a screen stays quiet while all goes well, and what needs the user in a banner with the one action that moves it on (`.claude/rules/kotlin.md`, "States") |
| Brand mark | the project's own drawing, an open book in scan corners: in teal on paper cream wherever the product's icon shows, and alone, in the theme's primary (app) or accent (web UI), on its screens; each unit holds its own copies, with the same path data, since a unit builds and tests only from its own tree |
| Pairing and access | a random bearer token, shared by QR code; plain HTTP on the local network; remote use through a VPN |
| Deployment | Docker Compose (`api`, `ocr`), restarted automatically with Docker; no official instance: each installation deploys the releases it chooses, with `scripts/deploy.sh` |
| OpenCV in the sandbox | the headless build, at the version PaddleX pins for the GUI build, which PaddleX requires and checks by distribution name: the setup installs a wheel without code under the GUI build's name that requires the headless build at our own pin, so that PaddleX finds its requirement and the resolver refuses an alias that misses PaddleX's pin. The GUI build would keep libGL, Mesa and LLVM in the image for no window; swapping the builds after the installation, or patching PaddleX's metadata or checks, would edit third-party files; uv's overrides and constraints cannot rename a distribution; the vulnerability scan, which cannot build the alias, leaves its name out (`ocr/setup/aliases.txt`) and scans the headless build |
| Sandbox images | two images on one base, built from `ocr/Dockerfile`: the setup image, which `ocr-setup` runs, holds uv and the installer, and the runtime image, which `ocr` runs, holds neither, so that the image that runs the untrusted engine all day carries no tool that only an installation needs, nor its advisories; the vulnerability scan watches uv by its version on PyPI, since it scans the runtime image only. uv's own image would be a new source, and leave the scan no PyPI version to read; uv mounted from the host would be a host install |
| Sandbox's init | the image's command is the sandbox's own init, a few lines of the standard library that stop being dumpable, start the supervisor, pass it the stop signals and reap orphans, since every process that holds the container's output must be out of the sandbox's reach, the sandbox running as one user: Docker's init (`init: true`) holds that output and cannot be made undumpable; the supervisor as process 1 would have to reap orphans that its `subprocess` calls also wait for; a second user for the supervisor would need capabilities that the sandbox drops |
| Sandbox upgrades | a release that needs a new sandbox is deployed with `scripts/deploy.sh --new-sandbox`, which installs it next to the running one while production runs, checks the new image against it, and swaps the two by renaming them at the restart, keeping the replaced one for a rollback: installing in place would leave production without OCR for the hour of downloads and with nothing to go back to; switching through `.env` would make a new writer of production's `.env`; a symbolic link would not recreate the container, and a later restart would switch silently; a separate script would be a second way to change production, while the image and the sandbox must switch at the same restart |
| Releases | one version for the api and the app (`VERSION`), so that the app a PC offers always matches its api; a release is a pull request of its own, whose notes are drafted from the Conventional Commits since the last release (`scripts/release.py`) in the Keep a Changelog format, and a workflow publishes it once it is merged, so that a release is reviewed like any change and published by nothing but its merge |
| Web UI's build | esbuild alone, called by a script of the repository (`server/scanmylib/web/build.ts`) that writes the hashed names of its script and stylesheet into the entry page, and copies the icons and the manifest, whose URLs the phone and the manifest name, as they are; no dev server, since the gate's build and the development stack check each change. Vite would bring a dev server and a plugin system that the UI does not use, and Rollup with them, for the same two files |
| Development | changes are made in worktrees and tried on a development stack and app (`fr.scanmylib.dev`) beside production; the scripts' guards protect production from misconfiguration, mistakes in a branch and compromised build dependencies, not from a deliberately malicious branch (`docs/SECURITY.md`) |

### Layers and modules

Each unit's source files as they are, grouped by responsibility, and the layer of each group. The api's and the web UI's
files live in their layer's directory, but the composition roots at the top of their source trees, the web UI's build
script and the api's test support; the web UI's tests and their support sit beside the module they test, and those of
its build, its catalogs and its icons beside its build script. The restructuring of [Principles](#principles) moves the
other units' files where one is planned; a file that mixes two layers splits along them. The last row lists the scripts
that the skills keep, which belong to no unit.

| Unit | Source files | Responsibility | Layer |
|---|---|---|---|
| api | `__main__`, `app`, `config`, `version` | Entry point, wiring of the services into the HTTP API, settings from the environment, the version of the build | Composition root |
| api | `domain/ordering` | Page numbering, reading order, duplicates and coverage of a document | Domain |
| api | `domain/documents` | A document's rules: what a new one takes, the slug of its folder, the summary of its layout | Domain |
| api | `domain/pages` | A page's rules: its key, its OCR attempts and the summary of its OCR, the orientation the sandbox detects | Domain |
| api | `domain/records`, `domain/text` | Typed records and the inputs of library operations; slugs and collation | Domain |
| api | `domain/timestamps` | Moments written as text, in the API and in the names of keys and folders | Domain |
| api | `domain/web_sessions` | A web session's rules: how long it lasts | Domain |
| api | `application/library`, `application/ocr_loop`, `application/publisher`, `application/debounce`, `application/status` | Documents and pages kept in sync with the library; the single OCR loop; publication of the library files, and the sections of a document's preview; the status of the OCR, its engine's and its queue's | Application |
| api | `application/clock`, `application/scan_images`, `application/ocr_engine`, `application/library_files`, `application/thumbnails`, `application/catalog`, `application/web_sessions` | The ports of the clock, of the images of the scans, of the OCR engine, of the library's files, of the pages' thumbnails, of the catalog of documents and pages and of the web sessions | Application |
| api | `application/access` | Who may use the api: the token, compared in constant time, and the web sessions opened with it | Application |
| api | `domain/assemble` | Rendering of the library files | Domain |
| api | `adapters/http_api/preview` | The HTML previews: their rendering, one at a time in a worker thread, and the URL of a document's files | Adapters |
| api | `adapters/sqlite/database`, `adapters/sqlite/rows`, `adapters/sqlite/catalog`, `adapters/sqlite/web_sessions` | SQLite state, its rows read into records, the summary of a document's layout written as JSON, and the catalog of documents and pages and the web sessions over them | Adapters |
| api | `adapters/system_clock` | The wall clock, in the server's time zone | Adapters |
| api | `adapters/pillow_images` | Pillow: the checks of an upload, thumbnails, the image sent to the OCR, re-encoded illustrations | Adapters |
| api | `adapters/filesystem/library_files`, `adapters/filesystem/thumbnails`, `adapters/filesystem/token_file`, `adapters/filesystem/published_apk` | The library's files, atomic writes and trash; the thumbnails, a cache in the state directory; the API token, in a file of the state directory that only its owner reads; the published APK's metadata | Adapters |
| api | `adapters/ocr_sandbox/client`, `adapters/ocr_sandbox/results`, `adapters/ocr_sandbox/sanitize`, `adapters/ocr_sandbox/engine` | The OCR sandbox: the client of its protocol, the validation of its untrusted results, the sanitizer of their Markdown, and the OCR engine over them, which times the reading of a page and validates the untrusted status of the sandbox | Adapters |
| api | `adapters/zip_archives`, `adapters/qr_codes` | Zip archives, QR codes | Adapters |
| api | `adapters/http_api/documents`, `adapters/http_api/pages`, `adapters/http_api/system`, `adapters/http_api/web`, `adapters/http_api/schemas`, `adapters/http_api/serializers`, `adapters/http_api/dependencies`, `adapters/http_api/authentication`, `adapters/http_api/middleware`, `adapters/http_api/static_files`, `adapters/http_api/error_answers`, `adapters/http_api/fastapi_application` | HTTP routes, the times that clients send, the credential of each request, security headers and body limits, the web UI's static files and their caching, the answers to errors, and the FastAPI application that assembles them | Adapters |
| api | `devtools/fake_ocr` | The fake OCR sandbox of the development stack and the tests | Test support |
| web UI | `src/main.tsx`, `src/index.html`, `src/app.css`, `src/stylesheet-imports.d.ts` | Entry point, the template of the entry page, and the stylesheet | Composition root |
| web UI | `build.ts` | The build: the bundle, the entry page that names its hashed files, and the copy of the files served under stable URLs | Tools |
| web UI | `i18next.config.ts` | The configuration with which i18next-cli extracts the keys of the UI's text from the sources into the catalogs, and checks them | Tools |
| web UI | `biome-plugins/arrow-functions.grit`, `biome-plugins/typed-components.grit` | Biome's plugins, in GritQL: one refuses a `function` declaration, since every function is a `const` arrow function, and the other a component not typed `FC<Props>` | Tools |
| web UI | `locales/en.json`, `locales/fr.json` | The catalogs of the UI's text: English, the reference, and its French translation | Adapters |
| web UI | `src/domain/reading-order` | The moves of the reading order: a block of pages, next to a page, one place, a range and a span of the selection | Domain |
| web UI | `src/domain/selection` | The selection of the pages of the reading order: a page added or removed, a range from the anchor, the span of a scattered selection, and the pages that left the reading order dropped | Domain |
| web UI | `src/domain/formatting` | The locale of numbers, numbers and decimals, sizes in bytes and percentages, dates, the time elapsed since a date, and a time in ISO 8601 with the browser's offset | Domain |
| web UI | `src/domain/photo-upload` | The checks of a photo before its upload: its format, its size, and a photo without a type left to the server | Domain |
| web UI | `src/domain/document-summary`, `src/domain/document-search` | A document as the library lists it, its counts of pages and the pages its scans cover, written as ranges; the kinds of document; the search of the library by title and author, whatever the case and the accents, shown from four documents | Domain |
| web UI | `src/domain/document-details` | A document as its own screen shows it, with its notes, its folder and its pages; the groups of its pages, in the api's order: in the reading order, unplaced, waiting for their text, excluded and duplicates; whether its pages can be organized, whether a page keeps a place chosen by hand, and how many of its pages are still waiting for their text | Domain |
| web UI | `src/domain/formulas`, `src/domain/reading` | KaTeX's options for the formulas of the OCR, and the text written against an inline formula; the outline of a document being read, and the page at the reading line | Domain |
| web UI | `src/domain/page-details` | A page as its own screen shows it, with its scan, its text, its numbers and the reading of its text; whether its text is being read, the pages before and after it in its document, the number its field shows, a page number typed by hand, and its turns by a quarter | Domain |
| web UI | `src/domain/pairing-details` | What a phone needs to pair with the PC: the PC's address, the access token, and the app's download | Domain |
| web UI | `src/domain/server-status` | The status that the api reports: its version, the engine's report with its graphics card, the counts of its queue and the library's folder; the pages still waiting for their text; the key of the queue's counts, and whether the queue moved from one key to the next | Domain |
| web UI | `src/application/session`, `src/application/api-errors` | The session: signing in with the access token or a sign-in link, signing out, checking the session that this browser may hold, its end when the api no longer knows it, and its ports, the api's calls it makes and the record of a sign-in; how a call to the api fails, refused with its status and detail, or unreachable | Application |
| web UI | `src/application/scheduler` | The port that runs a task after a delay, and cancels it | Application |
| web UI | `src/application/document-catalog`, `src/application/uuid-source` | The ports of the library: the api's calls that list the documents and create one, and a source of random UUIDs, the ids that the browser gives the documents it creates | Application |
| web UI | `src/application/document-store` | The port of a document's screens: the api's calls that read a document with its pages and the HTML of its `document.md`, save its changes, move it to the trash, put its pages in a new order and restore their automatic order, and the addresses of its exports | Application |
| web UI | `src/application/page-store` | The port of a page's screen: the api's calls that read a page and the HTML of its text, save its number, its exclusion or its rotation, read its text again and move it to the trash | Application |
| web UI | `src/application/library-loader`, `src/application/document-loader`, `src/application/page-loader`, `src/application/reader-loader`, `src/application/queue-moves` | The loading of the library, its failure shown in place of the list the first time, and a refresh that fails keeping the list and told unless the api is unreachable; the loading of a document, of a page and of the reader, one request at a time, a load asked meanwhile coming once more after it, or dropped by the reader: again while texts are read, and, for a document, shortly after a photo is sent or when the queue moves, with the changes of its order kept apart from its refreshes; a refresh that fails keeps what the screen shows, unless the document or the page is gone; the moves of the engine's queue, which load the library or a document again, counted from the status known when the screen opens | Application |
| web UI | `src/application/organizer-store` | The Organize mode's state: the order shown at once, its moves sent one request at a time with the last order winning, a refused order that reloads the document, the restore of the automatic order, the selection, and what its toolbar allows | Application |
| web UI | `src/application/pairing-source`, `src/application/clipboard` | The ports of the pairing: the api's call that reads it and the addresses of its QR codes and of the app's download, and the clipboard | Application |
| web UI | `src/application/upload-queue` | The upload queue: the photos added to a document, checked for their format and size, numbered in their capture session, sent two at a time with their progress, failed or refused, sent again, cleared, and what settled once nothing is left to send; and its ports, the upload of a page and the clock | Application |
| web UI | `src/application/engine-status` | The engine's status, polled every three seconds while the page is visible, one request at a time, online, offline or unknown, and its ports: the api's status, the page's visibility | Application |
| web UI | `src/adapters/http-api/api-client`, `src/adapters/http-api/error-detail`, `src/adapters/http-api/response-fields`, `src/adapters/http-api/server-status-decoder`, `src/adapters/http-api/document-summary-decoder`, `src/adapters/http-api/document-details-decoder`, `src/adapters/http-api/page-details-decoder`, `src/adapters/http-api/pairing-decoder`, `src/adapters/http-api/page-uploader` | The client of the api: its requests, with the session cookie and the header that guards the changes of state, cancelled when their screen is left, the calls of the session, of the status, of the library's documents, of a document, of a page and of the pairing, the detail of its error answers, the check of each answer's shape, the upload of a photo, which tells how much of it is sent, and the report of a signed-in call whose session the api no longer knows | Adapters |
| web UI | `src/adapters/browser/sign-in-record`, `src/adapters/browser/address-bar`, `src/adapters/browser/timer-scheduler`, `src/adapters/browser/page-visibility`, `src/adapters/browser/random-uuid-source`, `src/adapters/browser/clipboard`, `src/adapters/browser/window-clipboard`, `src/adapters/browser/unload-guard` | The record of a sign-in in the browser's storage, under the key that browsers signed in to earlier releases hold; the token of a sign-in link, taken from the address bar and the history before the router reads them; the browser's timers behind the scheduler; the visibility of the page; the UUIDs built from the browser's random bytes, also over plain HTTP; the clipboard, through the copy command over plain HTTP; the browser's question before the page is left while photos are being sent | Adapters |
| web UI | `src/adapters/i18next/localization`, `src/adapters/i18next/catalogs`, `src/adapters/i18next/type-options`, `src/adapters/i18next/formatted-text`, `src/adapters/i18next/page-labels`, `src/adapters/i18next/document-labels`, `src/adapters/i18next/reading-text` | The translations: the instance of i18next in the browser's language, its catalogs and the types of their keys, and the texts of sizes, durations, percentages, quotations, dates, the time elapsed since a date, a page's short label, status, number source and placement, a document's kind, and the markers and outline of a document being read | Adapters |
| web UI | `src/adapters/react/shell/routes`, `src/adapters/react/shell/shell`, `src/adapters/react/shell/use-shell`, `src/adapters/react/shell/navigation`, `src/adapters/react/shell/header`, `src/adapters/react/shell/use-document-title`, `src/adapters/react/shell/versioned-url` | The routes, the frame of every screen with its skip link and its state, the header with its navigation, the current section and sign-out, confirmed while photos are being sent, the outcome of the uploads, the redirects to and from the login, the focus and the scroll of a new screen, and its title; the address of an image that the api regenerates in place, which changes with its version | Adapters |
| web UI | `src/adapters/react/shell/loading-state`, `src/adapters/react/shell/error-state`, `src/adapters/react/shell/empty-state`, `src/adapters/react/shell/error-message`, `src/adapters/react/shell/toasts`, `src/adapters/react/shell/toast-region`, `src/adapters/react/shell/brand-mark`, `src/adapters/react/shell/icon` | The states of a screen that is loading, that failed or that has nothing to show, the text of a failed call to the api, the toasts and their region, the brand mark and the icons | Adapters |
| web UI | `src/adapters/react/login/login-screen`, `src/adapters/react/login/use-login-screen`, `src/adapters/react/login/login-messages` | The login, its state, and the texts of its errors and of the reasons it shows | Adapters |
| web UI | `src/adapters/react/library/library-screen`, `src/adapters/react/library/use-library-screen`, `src/adapters/react/library/document-card`, `src/adapters/react/library/library-text` | The library and its state: its documents' cards, their search, the creation of a document, the folder of the library, its loading again when the queue moves or the page shows again, and the texts of its counts, chips and coverage | Adapters |
| web UI | `src/adapters/react/pairing/pairing-screen`, `src/adapters/react/pairing/use-pairing-screen`, `src/adapters/react/pairing/qr-code`, `src/adapters/react/pairing/copy-field` | The pairing and its state: the install of the app and the pairing with the PC, their QR codes, and the address and the token to copy by hand | Adapters |
| web UI | `src/adapters/react/document/document-screen`, `src/adapters/react/document/coverage`, `src/adapters/react/document/coverage-layout`, `src/adapters/react/document/page-grid`, `src/adapters/react/document/placement-chip`, `src/adapters/react/document/document-text` | The document: its details, its editing and its move to the trash, its coverage with its bar and its axis, its counts, its exports and its folder, the grid of its pages in their groups with the badge of how a page got its place, its loading again while texts are read or photos sent, shortly after a photo is sent, or when the queue moves, the changes of its order kept apart from its refreshes, and the texts of its groups, counts and coverage | Adapters |
| web UI | `src/adapters/react/uploads/uploader`, `src/adapters/react/uploads/upload-text` | The uploads of a document: its photos chosen or taken with the camera, the list of their uploads with their progress, their failures and the retry, and the texts of the uploads and of their outcome | Adapters |
| web UI | `src/adapters/react/dialogs/document-dialog`, `src/adapters/react/dialogs/use-document-dialog`, `src/adapters/react/dialogs/document-form`, `src/adapters/react/dialogs/confirm-dialog`, `src/adapters/react/dialogs/use-modal` | The form of a document's title, author, kind, flattening and notes, new or edited, its state and its saving, and the confirmation of an action, in modal dialogs that give the focus back to the control that opened them | Adapters |
| web UI | `src/adapters/react/engine-status/engine-status-badge`, `src/adapters/react/engine-status/use-panel-dismissal`, `src/adapters/react/engine-status/engine-banners`, `src/adapters/react/engine-status/engine-status-text` | The engine's status in the header, its details, in a panel that a click outside or Escape closes, and the banners of an unreachable server or OCR, and their texts | Adapters |
| web UI | `src/adapters/react/shell/brand-mark-drawing` | The brand mark that the page draws: the group of `icon.svg` it names, and its frame | Adapters |
| web UI | `src/adapters/react/sanitized-html/page-markers`, `src/adapters/react/sanitized-html/use-sanitized-html` | The page markers of the server's sanitized HTML, written in the UI's language; that HTML parsed in an inert template, prepared there before anything of it loads, placed in an element that React leaves empty, and its formulas typeset before the screen measures what was placed | Adapters |
| web UI | `src/adapters/katex/render-math` | The formulas of the server's sanitized HTML typeset by KaTeX, with the `style` attributes it writes routed through the CSSOM, which the Content Security Policy allows, and an inline formula kept on the line of the text written against it | Adapters |
| web UI | `src/adapters/react/page/page-screen`, `src/adapters/react/page/scan-pane`, `src/adapters/react/page/text-pane`, `src/adapters/react/page/page-text`, `src/adapters/react/page/scan-layout` | The page: its scan, whole on the screen or the pane's width, turned as the page is; its text, as HTML with its illustrations at the address of their reading and its formulas typeset, or as raw Markdown to copy; its number to type or clear, its rotation, exclusion, new reading and move to the trash; its notices, the previous and the next pages, with the arrow keys too; its loading again while its text is read; and the texts of its technical details and of its number | Adapters |
| web UI | `src/adapters/react/reader/reader-screen`, `src/adapters/react/reader/reading-parts`, `src/adapters/react/reader/outline-groups`, `src/adapters/react/reader/reading-position`, `src/adapters/react/reader/reading-tracker`, `src/adapters/react/reader/page-read-memory`, `src/adapters/react/reader/reader-text` | The reader: the whole document in reading order, its markers in the UI's language and linked to their pages, its missing pages, its illustrations at the address of their reading, loaded as they come into view, and its formulas typeset; the "Page" list under its headings, which sticks under the header, follows the reading and jumps to a page, held in place while the illustrations above it load; the page read kept in the history entry, for "Back" and a reload; the download of `document.md`, the refresh, and the texts of the pages still waiting and of a document with nothing to read yet | Adapters |
| web UI | `src/adapters/react/organizer/grid-geometry` | The organizer's grid: its rows, where a dragged page would land, its insertion mark, and the scrolling speed at the edges | Adapters |
| web UI | `src/adapters/react/organizer/page-organizer`, `src/adapters/react/organizer/drag-gesture`, `src/adapters/react/organizer/page-drag`, `src/adapters/react/organizer/move-dialog`, `src/adapters/react/organizer/organizer-text` | The Organize mode: the selection of its pages with a click, Shift or Ctrl, their moves by the buttons of their cards, the "Move selection" dialog or a drag with a mouse, a finger after a long press or a pen, with its scrolling at the edges and Escape, the order shown at once and sent one request at a time, the restore of the automatic order, and their texts | Adapters |
| app | `ScanMyLibApplication`, `AppContainer`, `MainActivity` | Entry points and wiring | Composition roots |
| app | `model/`, `library/PageNumbering`, `library/PageLabel`, `library/PageRanges` | Document kinds, scan sources, scanner modes, theme modes, the PC's address; page numbering, the pages a page's label names, and the page ranges of the PC's coverage label | Domain |
| app | `library/`, `pairing/`, `sync/`, `update/`, `settings/` | The library and its staging area, pairing, the upload queue, app updates, settings | Application, with their technology parts as adapters |
| app | `api/`, `db/`, `diagnostics/`, `ui/` | Client of the PC, Room database, crash reports, Compose screens and view models | Adapters |
| OCR sandbox | `container_init`, `supervisor`, `worker`, `engine_environment` | The container's process 1, the HTTP API on the Unix socket, the process that runs an engine, and the check that an engine's environment imports its libraries | Composition roots |
| OCR sandbox | `printable_text` | The escape of the characters a terminal does not show, and the cut of an escaped text | Domain |
| OCR sandbox | `protocol`, `engines/base` | Messages between supervisor and worker, the interface of an engine | Application |
| OCR sandbox | `manager`, `runtime`, `config`, `gpu`, `client` | Engine lifecycle and page queue, engine processes, settings, GPU readings, a client of the socket | Application and adapters |
| OCR sandbox | `adapters/dumpable` | A process's descriptors kept from the other processes of the sandbox | Adapters |
| OCR sandbox | `engines/paddleocr_vl`, `engines/images` | PaddleOCR-VL-1.6, and its image handling | Adapters |
| OCR sandbox | `setup/install.sh`, `setup/distribution_alias.py` | The installation of the sandbox's environments and models, which only the setup image holds, and the alias distribution it installs in place of OpenCV's GUI build | Tools |
| scripts | `lib/stack.py`, `lib/version.py`, `lib/formatting.py`, `lib/parallel_tests.py`, `lib/commit_areas.py`, `lib/passed_commit_check.py`, `lib/common.sh`, `lib/engine_check.sh` | The `.env` format and its copy with a setting changed, production's checkout and the isolation of a stack, where a deployment installs a new sandbox, and the settings that the check of a sandbox before a restart takes from the `ocr` service; the version of a build; what the gate hands to its formatters and linters, and what comes back; the gate's parallel run of the tests of the scripts; the areas a commit touches; the commits that already passed their per-commit check; shared shell functions; the check of the engine's environment in a new `ocr` container, and of a sandbox with a new image before a restart | Tools |
| scripts | `setup.sh`, `dev-env.sh`, `dev.sh`, `build-apk.sh`, `check.sh`, `deploy.sh`, `prod.sh`, `release.py`, `e2e_test.py`, `verify-sandbox.sh` | Install, develop, build the app, check, deploy, operate, release, test end to end, verify the sandbox | Tools |
| — (the skills) | `pull-request/scripts/pr_screenshots.py` in `.claude/skills/` | Publish the screenshots of a pull request, copy them without their hidden data, and clean the branch that holds them: the copy of a template's script, kept as it ships, whose tests live with the template | Tools |

## Repository layout

### Repository tree

```
scanmylib/
├── .claude/                     # Claude Code: settings, rules, skills and the expert reviewers
├── .github/
│   ├── pull_request_template.md # The body of every pull request, with its checklist
│   └── workflows/               # CI (the gate on every pull request and every push to main), the release, and the weekly vulnerability scan
├── android/                     # The app: Kotlin, Compose, Gradle
├── docs/
│   ├── foundations.md           # This document
│   ├── ARCHITECTURE.md          # Components, data flow, the library's layout, the ordering algorithm
│   ├── API.md                   # The HTTP API of the app and the web UI
│   ├── OCR_SANDBOX.md           # The protocol between the api and the sandbox
│   └── SECURITY.md              # Threat model, guarantees, residual risks
├── ocr/                         # The OCR sandbox: its images, its setup, its supervisor and engines, benchmarks
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
| The `ocr` service stays isolated (`.claude/rules/sandbox.md` > The OCR sandbox) | `scripts/verify-sandbox.sh`, after every deployment and the first installation |
| No text of the sandbox reaches a terminal as it is (`.claude/rules/sandbox.md` > The OCR sandbox) | `scripts/verify-sandbox.sh` for the processes that hold the container's output, the tests of the supervisor's relay and of `scripts/verify-sandbox.sh`, and the sandbox's expert reviewer (`.claude/agents/sandbox-reviewer.md`) for the commands run in the `ocr` service |
| Every stack but production's is checked before docker compose runs it (`.claude/rules/sandbox.md` > Development stacks and production) | `scripts/lib/stack.py`, through `scripts/dev.sh`, `scripts/dev-env.sh`, `scripts/deploy.sh`'s rehearsal and `scripts/build-apk.sh`, its unit tests in `scripts/tests/`, and the integration tests of those scripts in `scripts/integration_tests/` |
| Production is operated by hand only through `scripts/prod.sh compose` (`.claude/rules/sandbox.md` > Development stacks and production) | `scripts/lib/stack.py check-compose-command --production`, through `scripts/prod.sh` |
| The dev app keeps its own application id (`.claude/rules/sandbox.md` > Development stacks and production) | The signing container of `scripts/build-apk.sh` |
| Production runs published releases only (`.claude/rules/releases.md`) | `scripts/deploy.sh`, `scripts/setup.sh`, `scripts/prod.sh` and `scripts/build-apk.sh` |
| Never weaken what the lockfile or the registry settings guarantee (`.claude/rules/configuration.md` > Dependencies) | `pip --require-hashes`, pnpm's frozen install with its integrity check and the guards of `server/scanmylib/web/pnpm-workspace.yaml`, Gradle's dependency verification, the image digests of `scripts/check.sh`, of `scripts/lint/Dockerfile.web`, of `server/Dockerfile`'s Node stage and of the scanner in `.github/workflows/vulnerability-scan.yml`, the checksums of `scripts/build-apk.sh` and of pnpm in `scripts/lint/Dockerfile.web` and `server/Dockerfile`, which `scripts/tests/test_web_toolchain_pins.py` holds together |
| The French translation lives only in the catalogs (`CLAUDE.md` > Language) | The web UI's unit tests, the catalog test `translations.test.ts` among them; i18next-cli in `scripts/check.sh lint`, whose `extract --ci` refuses a key missing from the catalogs or unused, `status fr` an untranslated entry, and `lint` a text of the TypeScript UI outside `t()` and the values of a call that do not match its placeholders; `tsc`, for a key outside the English catalog; Android lint for missing translations |
| Part of the rules of the Python: PEP 8 at 120 columns, imports, typed signatures with no bare `Any`, no blind `except`, no mutable defaults (`.claude/rules/python.md`), no shell or SQL string built from input (`.claude/rules/conventions.md` > Input from outside the program), and, in part, no character a reader cannot see written as such (`.claude/rules/conventions.md` > Characters a reader cannot see) | Ruff and mypy `--strict`, in `scripts/check.sh lint` |
| Part of the rules of the shell scripts: quoting and `[[ … ]]` (ShellCheck), indentation (shfmt) (`.claude/rules/bash.md`) | ShellCheck and shfmt, in `scripts/check.sh lint` |
| The Kotlin conventions at 120 columns, file names (`.claude/rules/kotlin.md`) | ktlint, in `scripts/check.sh android` |
| The rules of the web UI: layout, named exports, no `any`, type-only imports marked, no `@ts-ignore`, no `enum` or `namespace`, no floating promise, the rules of hooks, keys from the data, no `dangerouslySetInnerHTML`, every function a `const` arrow function, every component but a generic one typed `FC<Props>` (`.claude/rules/web.md`) | Biome, with its plugins `server/scanmylib/web/biome-plugins/arrow-functions.grit` for the arrow functions and `server/scanmylib/web/biome-plugins/typed-components.grit` for the components, in `scripts/check.sh lint` |
| The web UI's TypeScript is strict, with `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` and erasable syntax only (`.claude/rules/web.md` > TypeScript and React) | `tsc --noEmit` on the sources and on the tests, each with the types of its runtime, in `scripts/check.sh lint` |
| Part of the rules of the api's tests: a broad exception asserted with its message, its raising call alone in its block, no assertion in an `except` (`.claude/rules/tests.md` > pytest) | Ruff's PT011, PT012 and PT017, in `scripts/check.sh lint` |
| The hook that runs once in the api's tests is a fixture of `scope="class"` written as a `@classmethod` (`.claude/rules/tests.md` > pytest) | `filterwarnings = ["error::pytest.PytestRemovedIn10Warning"]` in `server/pyproject.toml`, in `scripts/check.sh server` |
| Part of the rules of the web UI's tests: assertions in tests only, no test focused or skipped by its name, no hook twice in a group, five levels at most (`.claude/rules/tests.md` > node:test) | Biome, in `scripts/check.sh lint` |
| Part of the rules of continuous integration: actions pinned to commits, the jobs' permissions and credentials, no template injection (`.claude/rules/configuration.md` > Continuous integration) | zizmor, in `scripts/check.sh lint`; the unit tests of the workflows, in `scripts/check.sh scripts`, for the actions they may use, their permissions, their secrets, `pull_request_target`, what the release workflow runs, and the vulnerability scan's split between the job that scans and the one that uploads, its triggers, the exact options of its containers, and the sandbox's image, uv, requirements and Paddle's version that it follows |
| A commit footer holds only what tools read (`.claude/skills/writing-commits/SKILL.md` > The rules of a commit message) | `attribution` in `.claude/settings.json`, which keeps Claude Code's own commit trailers and pull request line out |
| Part of the layers of the api: every file of the api lies in a layer's directory, but the composition roots at its top and the test support; the domain imports only the domain and libraries of plain values, reads no wall clock and calls no input or output function; the application imports only the inner layers, libraries of plain values, Python's runtime and `PurePath`, reads the wall clock only through its port and calls no input or output function itself; the adapters import no composition root and no test support; a file in a layer imports none still outside the layers; no import cycle between the api's files (`.claude/rules/architecture.md` > Layers, > Ports and wiring and > Responsibilities, `.claude/rules/python.md`, "Plain data is a frozen dataclass", `.claude/rules/tests.md` > Test support) | `server/tests/test_layers.py`, in `scripts/check.sh server` |
| Every rule no tool can check: architecture, conventions, tests as specification… | `/combined-review` ([Code review](#code-review)), before every pull request |

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
- **The project's own files are not checked as outside input is,** since such a check costs code and tests and guards
  against nothing but its own bugs, which a loud failure shows sooner.

### Git

`CLAUDE.md` > Workflow says how a session works, and the `implement`, `deliver-branch`, `pull-request` and
`writing-commits` skills hold the procedures, with the rules of commits and of review. The reasons behind them:

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
  cannot show. Each commit passing the areas that read what it changes keeps `main` a safe start for any work, a commit
  of documents costing nothing, and the whole gate, which the CI runs on the pull request, keeps every part working
  with the others: every pull request must pass it there anyway, so it runs once per push rather than on each machine
  at each rewrite of the branch, and `scripts/check.sh --last-commit` skips a commit that already passed it. The
  integration tests of the scripts run for each commit that changes a script they run, since a commit that a
  `git bisect` checks out may then run that script on the machine of production, whose guards it holds. So does the
  build of the api's runtime image, the `api-image` area, for each commit that changes a file only that build reads, its
  Dockerfile, its `.dockerignore` and the web UI's package files, since a broken image would otherwise first show at a
  deployment; the sources it builds are checked on each commit by the `lint` and `web` areas, and the CI runs it on
  every pull request.
- **A header that says what the change achieves, under the scope it belongs to,** lets a reader find a change in
  `git log --oneline` without opening it, since the diff already lists the files. The release notes that
  `scripts/release.py` drafts are the subjects of the features and fixes, each prefixed with its scope.
- **A footer that holds only what tools read** lets the release tooling and the issue tracker trust it. A trailer naming
  the tool that typed a change would add a line to every message and say nothing of its reason.
- **"Rebase and merge"** lands each commit as written, after the review ([Code review](#code-review)) and CI
  ([Technology stack](#technology-stack)).
- **The screenshots of pull requests live on a branch of their own, `pr-screenshots`,** that holds no code: in the
  code's history, every clone would carry them, and CI artifacts would show every screen rather than the case a pull
  request makes. Each picture is linked by the commit that adds it, so a description never changes once written, and
  the branch is deleted whole from time to time rather than pruned, since rewriting the descriptions that link it
  would cost more than publishing an open pull request's pictures again. Its commits are data, outside the rules of the
  code's commits, and a ruleset that protects every branch leaves it out.

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
- **Skills hold procedures** because a procedure matters only while its task runs, and a skill loads only then. A rule
  that serves only one task, such as writing or checking a commit message, lives in the skill of that task for the same
  reason, and so does a rule of a procedure that other tasks only cite, which `CLAUDE.md` points to in one sentence: in
  `CLAUDE.md`, it would cost every session, and no file's `paths` would load a rules file of its own at the
  moment it serves.
- **This document holds the design and its reasons,** and states no rule, so that a rule changes in one place.
- **An expert reviewer reads at least the rules files of its domain,** one hop away, so that it never chases a rule
  across documents. It starts without the session's `CLAUDE.md` files, which would cost it tokens on every turn and
  could steer it: the rules that apply are the checkout's.
- **Each agent runs on the model and at the effort its task needs,** because every turn of every run pays for both, and
  a review multiplies the runs: the stakes of the work where a plan or code is written, Opus where a review judges and a
  miss costs most, Sonnet where written rules or a plan guide the check, Haiku for search, as
  `.claude/rules/configuration.md` > Claude Code automation gives them. The stakes, not the size, choose the models that
  plan and write, since the size says how much there is to check and the stakes what a mistake costs: reading the code
  makes most of what these agents cost, and Opus charges half of what Fable charges for it, so Opus serves by default;
  Fable serves where the stakes are high, at `high` for a plan, since a mistake in a plan costs every step after it,
  and at `medium` for code, where its announcement measures it above Opus one effort level higher and a higher effort
  costs it several times more; Sonnet writes the code of work whose stakes are low, guided by a checked plan and backed
  by the review, which runs the same whatever the stakes. A low effort saves Haiku and Sonnet little and costs them
  much quality, so they never run at it. The reviews that judge stay on Opus, since a review reads far more than it
  writes, and Fable charges twice as much for what an agent reads.
- **The history of a decision lives outside the repository,** with the project-management material, so the documents
  here describe only the present, with its reasons.

## Testing

### Tests document the rules

The tests are the specification of the business rules. To learn how a part of the system behaves, read its tests: each
one states one rule, in a sentence, in the vocabulary of the domain. That is why the code carries no comment that states
a rule. Every test file follows one structure, so that the sentence runs from the component through the operation and
the situations to the test's name, and a reader, and an agent, finds the arrangement, the act and the assertions in the
same place in every file; `.claude/rules/tests.md` says how tests are written. The web UI's tests sit beside the module
they test, so that a module and its specification are read, and moved, together, and the tools tell them apart by their
names; the other units keep theirs in a test tree of their own, where their runners and images look for them.

### Test levels

- **The unit tests run in the gate,** so that they are fast, need no GPU and can never reach production: those of the
  api, the web UI and the sandbox in containers without network, those of the scripts' files and of the workflows on
  the host's `python3`, with the standard library only. The api's tests use a fake sandbox that speaks the real protocol
  on a real Unix socket, so that the client and its limits are tested as they run.
- **The integration tests of the scripts run the scripts themselves against a stand-in for docker,** because the guards
  they test must refuse what production owns without any container being built or started. They run apart from the
  unit tests of the scripts' files and of the workflows, in an area of the gate of their own, since a whole script
  and the processes it starts cost far more than a call to a function.
- **The end-to-end test and the isolation check need a running stack,** so they run against the development stack, or
  production after a deployment, outside the gate.
- **The benchmarks need the real engine and the GPU,** so they run by hand, outside the gate.

### Releases and deployments

`.claude/rules/releases.md` says which tests a release passes before its pull request opens, who merges that pull
request, what a deployment checks, and how production's images are built. The reasons:

- **A test validates a commit,** and a published release is a commit that CI and the release procedure have tested,
  including the sandbox's tests that need the engine's environment, which CI lacks. Testing it again at each deployment
  would test the same commit again, slow each deployment, and build an image of the api's tests on the machine that runs
  production.
- **Claude merges the release pull request, and the user deploys.** The merge publishes a release, which changes no
  installation: what it holds, the version and the notes, the user approved before the pull request opened, and every
  change it releases went through the user's review in its own pull request, so waiting for the user to merge it would
  only delay the publication, as long as the conditions of the rule hold, without which the user merges it. A deployment
  changes production, the user's machine and library, so only the user runs it.
- **A deployment can still get the installation wrong, where no test of the commit looks:** it builds the images that
  day, on the current image of each base tag and, for the sandbox and the api, the Debian packages of the first build
  on that image, runs them with production's `.env`, and starts the engine's environment that the machine's sandbox
  holds. So its checks look at what it installed, not at the code. They stop short of loading a model, which would
  take the shared GPU for a check: a model that fails to load, or a page the engine cannot read, shows at the first
  page, in the engine's state.
- **The new image imports the engine's libraries from the sandbox before the restart,** so that an image that cannot
  run the sandbox, such as one built on a new base that the sandbox's environments do not suit, is refused while
  production still runs, where the check after the restart could only stop `ocr` and leave the pages waiting. It is the
  same import as the check after the restart, not a test suite, and it costs a deployment the seconds of that import.
  It runs in a `docker run` container of its own, isolated as the service is, rather than through `compose run ocr`,
  which would run engine code in a container that no isolation check has looked at.
- **A new sandbox is checked before it is used, and the replaced one is kept.** The installation runs for about an
  hour, while production runs, and resolves the engines' dependencies as they are that day, with no lock: the check
  before the restart, the checks after it and the first page are what tell that the new sandbox works, and the replaced
  sandbox is what a rollback goes back to, so only the user deletes it.
- **A deployment pulls its base images and keeps the build's cache.** Without the pull, the builder may keep building
  on a copy of a tag that the machine pulled long before, or fall back to it when Docker Hub does not answer, while the
  official images are rebuilt regularly, and sooner for a critical fix. A new base invalidates every layer above it, so
  the packages an image adds are fetched again with each new base and are never older than it; rebuilding every layer
  at each deployment would download them, the api's Python packages and uv each time, for packages only a little
  fresher than the base's own. Each deployment therefore needs Docker Hub.

### Budgets

No budget is set yet. The first one comes with the benchmark that measures it. The measures of `README.md` > OCR engine
and the benchmarks of `ocr/bench/` are the references.

### Code review

Every branch goes through `/combined-review` before its pull request, which follows the procedure of `/expert-review`,
described below, with its experts grouped into two agents, as its own line says; `/expert-review`, one agent per
expert, reviews someone else's pull request, whose planted text could steer a panel and silence all its experts at
once, and runs when the user asks for it. Both are project skills in `.claude/skills/`, named so that they never shadow
the built-in `/code-review`.

- **It runs in its own subagent**, which never saw the code being written, so the review stays independent of the
  session that wrote the code, and that session keeps its context: the experts report to the review, which waits for
  all of them.
- **An interactive review runs in the background.** In the foreground, it can hand back when its first turn ends, while
  its triage and its experts still run, and their answers then reach the session instead. In the background, Claude
  Code keeps a fork running until it hands back its report, and delivers its agents' answers to it. Under `claude -p`,
  which waits for each agent, or with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` set, it runs in the foreground.
- **The review keeps its prompt cache warm while its agents run,** with a sleep in the background started again at each
  turn of the wait: a subagent's cache lasts five minutes, the experts often take longer, and a context written again
  whole costs a cache write where a warm one costs a read.
- **One expert per domain, in parallel.** Correctness reviews every diff, and conventions every diff that holds code or
  configuration. Architecture, tests, performance, security and documentation join when the diff touches their domain,
  and so do the project's own experts: isolation (the sandbox, the guards of the scripts, the Dockerfiles and
  `compose.yaml`) and Android. The goal expert joins when the review has the plan of the work. Each expert is an agent
  of `.claude/agents/`, on Opus for bugs, security, isolation, architecture, the app and performance, and on Sonnet
  for conventions, tests, documentation and the goal, which written rules or the plan guide. No expert can run a
  command, so that no reviewed text can make it act.
- **The goal expert checks the code against its plan,** which the review receives when the brief of the work gives one,
  through `.claude/skills/deliver-branch/SKILL.md` > Review, and its findings get a section of their own in the report:
  a change can pass every rule and still miss its goal, and nothing else in the review reads the plan; a section apart
  keeps a passing axis from hiding a failing one. The plan picks it, not the paths or the triage. It never judges the
  plan, which was checked before the code, as its size calls for. Without a plan it does not run, rather than read a
  goal into an issue whose text may not be the user's.
- **A triage on Sonnet weighs the experts that the paths pick,** by what the diff holds, before any of them runs: an
  expert pays a full reading of its rules, the diff and the code even when it has nothing to say, and the triage costs a
  fraction of that. It keeps an expert when unsure, and never drops correctness, nor security and isolation on their
  paths, nor documentation on an added file, whose content only it searches for a real document's name, nor narrows
  what they read, since a missed expert costs more than a needless one, and a triage that reads the
  diff can be steered by it.
- **`/combined-review` runs the same experts in two agents,** a `review-panel` on Sonnet for the experts on Sonnet and
  one on Opus for those on Opus, without the triage: each expert's run pays for reading its rules, the diff and the
  code around it before it checks anything, and a panel pays for that once for all its experts. Each panel gets every
  expert of its model and reads the whole diff, so that each expert's scope gate both drops it and adds it, by what the
  diff holds, as the triage does. A panel holds several checklists, which makes a miss likelier than with one expert per
  agent, so it takes its experts one at a time, those whose miss costs most first; the workflow takes that risk for the
  cost. The combined review reads the procedure, the contract and the experts' definitions of the expert review rather
  than copying them, so that each rule of review changes in one place.
- **The fixes of blocking findings are checked against the findings they answer,** by their experts, by correctness,
  and by the experts whose concerns the fixes newly touch, such as tests for a new test, rather than by every expert
  whose paths they touch: a fix of three files can touch the paths of every domain, and only the experts it concerns
  have something to check. Security and isolation still check every fix of their paths, since a fix can weaken a guard
  as well as add one.
- **The orchestrator confirms every blocking and should-fix finding** before reporting it, and lists the findings it
  dropped with their counter-evidence, so the report makes no claim it has not checked. It also holds every suggested
  fix to the project's rules, since an expert reads only those of its domain.
- **A branch is reviewed once.** A fix brings code of its own to review, and two runs of the same review judge
  differently, so each new review of the fixes finds something new, and reviews repeated until none finds anything
  never end. Only the fixes of blocking findings are checked again, since a defect there costs the most, and that check
  starts no further round. A finding that calls for a change of design goes back to the plan, where the method is
  cheapest to change, once: a second one shows that the plan cannot settle the design alone, and only the user can.
- **A new agent fixes the findings,** from a brief: the agent that wrote the branch, resumed, re-reads its whole, grown
  context on every turn, which costs more than the review it answers.
- **The report says what the review cost,** agent by agent, so that it shows which agents a review spends on, such as
  an expert that finds nothing on a large diff, and the triage and the experts can be tuned.
- **A target other than the current branch is checked out outside the repository**, at the commits its range resolves
  once, so a reviewed `CLAUDE.md` never loads as an instruction, and nothing done to a branch while the review runs
  changes what it reads. The experts and the panels follow the contract beside the session's expert-review skill, the
  triage and the panels read the definitions of the session's `.claude/agents/`, and the commit check reads the commit
  rules beside the skill: those of the checkout the session started in. A review run from another checkout than the
  branch's worktree, such as the main checkout, follows definitions the branch cannot rewrite; one run from the
  branch's worktree follows the branch's own, which its report lists when they differ from main's, so that the pull
  request names them.
- **Reviews can run at the same time, from the same checkout:** each one keeps its scope in a temporary directory of
  its own.
- **The report ends the review.** It suggests a fix for each finding but applies none: the session that owns the branch
  answers each one or has a `fixer` agent fix it, and the user decides at the merge.

## References

- Clean Architecture, Robert C. Martin: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- PaddleOCR (PaddleOCR-VL, PP-DocLayoutV3): https://github.com/PaddlePaddle/PaddleOCR
- vLLM: https://docs.vllm.ai
- FastAPI: https://fastapi.tiangolo.com
- Android app architecture: https://developer.android.com/topic/architecture
- Jetpack Compose: https://developer.android.com/compose
- Material 3 color roles: https://m3.material.io/styles/color/roles
- material-color-utilities (the contrast levels of Material's schemes): https://github.com/material-foundation/material-color-utilities
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- ML Kit document scanner: https://developers.google.com/ml-kit/vision/doc-scanner
- KaTeX: https://katex.org
- Conventional Commits 1.0.0: https://www.conventionalcommits.org/en/v1.0.0/
- Keep a Changelog 1.1.0: https://keepachangelog.com/en/1.1.0/
- Semantic Versioning 2.0.0: https://semver.org
- mattpocock/skills (the interview before a plan, and the plan of decisions): https://github.com/mattpocock/skills
