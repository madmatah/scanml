# ScanMyLib

ScanMyLib turns an Android phone and a Linux PC with an NVIDIA GPU into a book and document scanner whose output AI
agents can read. Pages are photographed on the phone, a few at a time, in any order and over as many sessions as
needed. The PC runs them through **PaddleOCR-VL-1.6**, locked in a Docker sandbox without network access, and files
each document on disk as Markdown, with its illustrations, in reading order. The phone app and the web UI are in
English, and in French on a phone or browser set to French.

```
Phone (ScanMyLib app)  ──Wi-Fi──▶  PC: api ──socket──▶ OCR sandbox (GPU, no network)
                                        │
                                        ▼
                             LIBRARY_DIR/<document>/document.md + images/
```

## Features

- **Partial, out-of-order scanning.** Pages arrive in any order, in several batches; they are put back in order from
  their printed page numbers, and the coverage ("1–12, 45–60") shows what is missing.
- **Structured output.** One Markdown file per document and per page, tables in HTML, formulas in LaTeX, illustrations
  cropped into image files, plus a machine-readable index of the library.
- **Untrusted OCR stack kept apart.** PaddlePaddle, vLLM and the model run in a container with no network, no access to
  the host's files and no privileges. Their output is treated as untrusted data.
- **Nothing installed on the host.** Every service, build and test runs in Docker containers.
- **Offline-tolerant phone app.** Pages wait on the phone until the PC is reachable.

## Requirements

- **PC**: Linux on x86-64 with Docker Engine and Docker Compose v2, and the NVIDIA Container Toolkit configured for CDI
  (`nvidia.com/gpu=all`). Also `git`, `bash`, `curl` and `python3` (standard library only).
- **GPU**: an NVIDIA GPU of the Turing generation (RTX 20 series) or newer, with an NVIDIA driver 580 or newer (the
  sandbox uses CUDA 13 builds of vLLM), and about 5 GB of free VRAM while pages are processed. The model is unloaded
  when idle. See "OCR engine" for cards with less than 24 GB.
- **Disk**: about 17 GB for the OCR sandbox (environments and models), 3 GB for the Android toolchain, plus the library.
- **Phone**: Android 8.0 or newer. The Google document scanner and the QR code reader of the app need Google Play
  services; without them, the app's own camera, photo import and manual pairing still work.

## Installation

The app is not published on a store: it is built and signed on the PC, with a signing key created there, and offered
for download by the web UI.

```bash
git clone https://github.com/madmatah/scanml.git ~/Dev/scanmylib
cd ~/Dev/scanmylib
git checkout "$(git describe --tags --abbrev=0)"   # the latest release
scripts/setup.sh          # images, OCR sandbox (~17 GB download), app, start, isolation checks
```

The scripts treat `~/Dev/scanmylib` as the checkout production runs from (`DEFAULT_CHECKOUT` in
`scripts/lib/stack.py`). It runs releases only, published on GitHub with their notes (`CHANGELOG.md`).
`scripts/setup.sh` only performs a first installation; later releases are installed with `scripts/deploy.sh` (see
"Updating").

`scripts/setup.sh` writes `.env` from `.env.example`. The scripts accept only a strict format: one `KEY=VALUE` per line,
without spaces, quotes or comments after a value.

| Variable | Role | Example |
|---|---|---|
| `COMPOSE_PROJECT_NAME`, `IMAGE_PREFIX` | names of the containers and images | `scanmylib` |
| `LIBRARY_DIR` | the organized library | `/home/USER/Documents/ScanMyLib` |
| `DATA_DIR` | state, socket, caches, published app, backups, logs | `/data/USER/scanmylib` |
| `SANDBOX_DIR` | OCR sandbox (environments and models), read-only for the services | `/data/USER/scanmylib/sandbox` |
| `SANDBOX_SETUP_DIR` | where `ocr-setup` installs the sandbox (`SANDBOX_DIR`, production only) | `/data/USER/scanmylib/sandbox` |
| `ANDROID_DIR` | Android SDK, Gradle caches, the app's signing key | `/data/USER/scanmylib/android` |
| `PUBLIC_URL` | address of the PC as seen by the phone | `http://192.168.1.XX:8765` |
| `SCANMYLIB_TZ` | time zone of the dates written in the library (the PC's own, set by `scripts/setup.sh`) | `UTC` |

The services restart automatically with Docker (`restart: unless-stopped`); there is no system service to install.

## Pairing the phone

1. On the PC, open the web UI at the address printed by `scripts/setup.sh` (`http://localhost:8765/#token=…`), then
   the **Pairing** tab.
2. Scan the QR code of **Install the Android app** with the phone's camera to download the app, then install it. Android
   asks once to allow installs from the browser.
3. Open the ScanMyLib app. On the **Pair with PC** screen, tap **Scan the QR code** and aim at the QR code of **Pair the
   app with this PC**: the app then knows the PC's address and its access token. Without a QR code reader, type the **PC
   address** and the **Token** shown under the QR code into the app's **PC address** and **Access token** fields, then
   tap **Test and pair**.

**Updates.** Once paired, the app asks the PC which app it publishes, when the library shows or is refreshed, at most
once an hour, and again once the library reaches the PC if it could not before. When it is newer, the library shows
"ScanMyLib X.Y.Z is available · Install": the app downloads it, checks it (the file the PC announced, the same app,
newer, signed with the same key), then hands it to Android, which asks to confirm. The first time, Android asks to allow
ScanMyLib to install apps, on a page of its settings; the install goes on when you come back.
**Settings › Check for updates** asks the PC at once.

**Appearance.** The app follows the phone's light or dark mode; **Settings › Theme** keeps it **Light** or **Dark**
instead. On Android 12 and later, **Settings › Wallpaper colors** replaces ScanMyLib's colors with the wallpaper's. On
Android 14 and later, the app follows the contrast chosen in the phone's accessibility settings.

The phone and the PC must be on the same network. Away from it, the app keeps the pages and sends them once the PC is
reachable again; the library says when the PC does not answer, with **Retry**, and when it no longer recognizes the
phone, with **Settings**, where **Change PC** pairs it again. To send pages from elsewhere, use a VPN (WireGuard,
Tailscale…) rather than exposing the port to the Internet.

## Scanning

- **New document**: title, author, kind (book or other), and **Flatten curved pages** (pages curved near the binding,
  done by the PC), on by default for a book and available for both kinds. **Create and scan** then opens the default
  camera, **Create and import** the photo picker. It works with the PC off: the PC gets the document with its first
  upload.
- **Scan** opens the default camera at once, with no question; in the library, the scan button of a card opens the
  document straight into it:
  - **Google scanner** (the default): detects the edges and crops the page. The **Google scanner retouching** setting
    chooses between **None — crop only** (the default), **Filters** and **Full** (filters plus finger and stain
    removal). This scanner never returns the original photo. To chain pages, tap "+" on its preview screen.
  - **Camera**: the app's own camera stays open. One tap is one photo and one page, at full resolution and without
    retouching. Turn the page and tap again, then **Done**. Only this camera asks for the camera permission.

  The arrow next to **Scan** (or a long press on it) opens the other camera for this time only, or from now on with
  **Use as default**; the default is also in the settings ("“Scan” opens"). If Google's scanner cannot start on the
  phone (no Google Play services), **Scan** opens the app's camera instead, until the scanner, chosen again in **Scan
  with…** or in the settings, starts.
- **Import** opens the photo picker: photos taken with any app, put back in shooting order (EXIF date) and sent as they
  are. JPEG, PNG and WebP are accepted (no HEIC). A photo that cannot be read (a cloud photo while offline…) or that is
  too large (over 40 MB or 120 megapixels) is skipped with a message; the others are imported.
- **Share** from the gallery or another app: select photos, then **Share › ScanMyLib**, and choose their document (or
  create one). They join its pages to send, as with **Import**, and the review of the pages to send opens; Back then
  returns to the document, then to the gallery.
- **Before sending**, the pages wait on the phone, on a screen of their own, "N pages to send", which opens as soon as
  a camera or the photo picker returns pages: tap a page to see it full size or remove it (with TalkBack, its
  **Remove** action), use the last tile to add more (**Scan**, **Import**, or **Scan with…** for the other camera), and
  **Send N pages** to queue them for upload. **Undo** puts a removed page back in its place for 10 seconds, until
  another page is removed, pages are added, or the review ends.
  While pages are being prepared, their progress shows there, and an import can be canceled; leaving meanwhile loses
  none of them. Pages scanned during an import join the run as soon as they are copied, without waiting for its photos.
  **Close** (or Back) keeps the pages on the phone and returns to the document, whose banner then says "N pages to
  send" with **Review**; the library shows them too. **Delete these pages** asks for confirmation, since these pages
  exist nowhere else.
- **First page number** (optional, in the review): for pages without a printed number that should be numbered. With
  **Consecutive pages** (on by default), the following pages get the next numbers. Leave it blank for front matter
  (cover, title page, preface).

The web UI can also add pages to a document, from the PC or from the phone's browser: import photos, or take a photo.

## Page order

Pages can arrive in any order, in several batches.

- **Number of each page**, by priority: the one typed by hand, else the printed one (read by the OCR), else the "first
  page number" hint, else a number inferred from the neighboring pages of the same session. Roman numerals come before
  page 1.
- **Pages without a number** are placed next to their neighbors from the same session. Front matter scanned just before
  page 1 therefore comes before page 1, and a plate scanned between pages 12 and 13 stays between them. An unnumbered
  page scanned on its own, in a session without any numbered page, goes to the end ("Unnumbered pages"), where it can
  be placed by hand.
- **Manual order**: in the web UI, on a document, the **Organize** button. Drag and drop a page or a selection
  (Shift+click for a range), or use **Move selection…**. The displayed numbers do not change, only the order does.
  **Restore automatic order** undoes everything.
- **Coverage**: "1–12, 45–60" and the missing pages are shown in the app and the web UI.
- **Rescanned page**: the most recent one replaces the old one, which stays visible as a duplicate.

## OCR engine

OCR runs in the background. The model loads onto the GPU with the first page, then unloads after 5 minutes of
inactivity to free the VRAM for other workloads. Measured on an RTX 3090 (24 GB):

| | |
|---|---|
| model start | ~40 s (~70 s the very first time) |
| speed | ~1.8 s per page, ~30 pages per minute |
| VRAM while processing | ~4.4 GB (none when idle) |
| character error rate (19th-century French printed pages) | ~2 % on scans, 2 to 4 % on photos |

Settings in `.env`, applied with `scripts/prod.sh compose up -d ocr` in the production checkout:

- `OCR_IDLE_UNLOAD_S`: delay before the VRAM is freed (300 s by default).
- `OCR_VLLM_GPU_MEM`: share of the GPU's memory that vLLM reserves, 0.15 by default. That default is sized for a 24 GB
  card (about 3.6 GB); below that amount, vLLM does not start. On a smaller card, raise it to keep about 3.6 GB, for
  example 0.30 on 12 GB or 0.45 on 8 GB. Only the 24 GB setting has been measured.

Flattening of curved pages (UVDoc) is on by default for books; on curved pages, it halves the errors. For a document
photographed flat, turn it off in the document's details.

## Web UI

The web UI is served by the PC on port 8765 (`http://localhost:8765`), and can be opened from the phone's browser too.
Its header shows the state of the OCR engine.

- **Library**: every document with its cover, its pages and its coverage.
- **Document**: the grid of pages (in the document, unnumbered, waiting for OCR or failed, excluded, duplicates), the
  coverage, the downloads of `document.md` and of a `.zip` archive, and:
  - **Read document**: the whole document in reading order, as in `document.md`, with its formulas typeset. A marker at
    the start of each page opens that page, and a list of the pages jumps to any of them.
  - **Organize**: reorder the pages by hand (see "Page order").
- **Page**: the scan next to the recognized text, the page number (a number typed by hand corrects it), rotation,
  exclusion from the document, new OCR run, deletion.
- **Pairing**: installing the app and pairing a phone.

## Output

```
ScanMyLib/
  INDEX.md                  # list of documents: title, author, pages, coverage, link
  library.json              # same, machine-readable
  example-book/
    document.md             # the whole document in reading order (YAML front matter)
    document.json           # metadata, page order, coverage, missing pages
    pages/<scan>.md         # one page = one Markdown file
    images/<scan>_<n>.jpg   # illustrations and photos cropped from the pages
    ocr/<scan>.json         # raw result: blocks, positions, labels
    scans/<scan>.jpg        # original photos
```

`document.md` holds markers such as `<!-- page 42 · scan … -->`, so that an agent can cite a page. Tables are HTML and
formulas are LaTeX, as the model produces them.

Nothing is ever erased: deleted documents and pages go to `LIBRARY_DIR/.trash/`.

## Backup

- `LIBRARY_DIR`: the library itself.
- `DATA_DIR/state`: the database (page order, manual settings) and the access token. Each deployment also copies it into
  `DATA_DIR/backups/`.
- `ANDROID_DIR/keystore`: the app's signing key. Without it, a new version of the app cannot update the installed one.

Everything else can be downloaded again: the OCR sandbox by `ocr-setup` (`scripts/setup.sh` on a new installation), the
Android toolchain by the next app build.

## Security

The OCR sandbox has **no network access**, sees **none of the host's files** besides its models, its socket and its
cache, and runs read-only and without privileges. Details and checks: [`docs/SECURITY.md`](docs/SECURITY.md) and
`scripts/verify-sandbox.sh`, which tests the isolation of the running service.

## Operations

In the production checkout:

```bash
scripts/prod.sh compose ps                 # state of the services
scripts/prod.sh compose logs -f api ocr    # logs
scripts/prod.sh compose restart api        # restart the api
scripts/prod.sh compose down               # stop everything
scripts/verify-sandbox.sh                  # prove the sandbox is isolated
```

`scripts/prod.sh compose` runs docker compose with production's `.env` and nothing else: plain `docker compose` would
also read the shell's environment (`COMPOSE_*`, `DATA_DIR`…), which overrides `.env`. It only runs in the production
checkout, and refuses builds and one-off containers, since production changes only through `scripts/deploy.sh`. `up`
applies what the checkout describes, so it needs a clean release, and never builds; `restart` works in any state.

## Updating

A new version is a release, published on GitHub: its tag `vX.Y.Z` and its notes, also in `CHANGELOG.md`. It is
installed from the production checkout:

```bash
git fetch --tags origin
git checkout v0.3.0            # the release to install
scripts/deploy.sh --dry-run    # checks and plan; changes nothing
scripts/deploy.sh --apk        # deploys, and publishes the new app
```

`scripts/deploy.sh` refuses to run outside the production checkout, with local or untracked changes, on anything but
a release published on GitHub (the commit of its tag on `origin`), on a release older than the one production runs
(unless `--allow-downgrade`), or when `.env` is not production's. It then:

1. builds the images from the commit (`git archive HEAD`) and runs the unit tests on them; if they fail, production is
   unchanged;
2. copies the state into `DATA_DIR/backups/state-<date>-v<version>/` (a consistent copy of the database; the last 10
   are kept);
3. restarts `api` and `ocr`, checks their health and the sandbox's isolation (the sandbox is stopped if that check
   fails), and tags the images that now run `:deployed`, the rollback target;
4. with `--apk`, builds and publishes the new app, which the phones then offer to install (without it, phones keep
   their app).

If a step fails, it says what state production is in and prints the commands to roll back to the `:deployed` images and
the backup of the state. A closed terminal does not interrupt it, and each run is logged in
`DATA_DIR/logs/deploy-<date>.log`.

`VERSION` is the version of both the PC side and the app (shown in the web UI and in the app's connection check). The
app's version code is derived from it, so a new app always installs over the previous one.

## Development

Changes are made on branches, each in its own worktree under `.claude/worktrees/` (ignored by git), next to a running
installation and without touching it:

```bash
cd ~/Dev/scanmylib
git fetch origin
git worktree add --no-track -b feat/my-change .claude/worktrees/my-change origin/main
cd .claude/worktrees/my-change
scripts/dev-env.sh        # .env of the development stack
scripts/dev.sh up         # api + fake OCR; scripts/dev.sh up --real-ocr for the real one
scripts/e2e_test.py page1.jpg page2.jpg   # end-to-end test, acting like the phone
scripts/build-apk.sh      # the "ScanMyLib (dev)" app
scripts/dev.sh down
```

The development stack has its own web UI (`http://localhost:8770`), its own data and test library (production's
`DATA_DIR` followed by `-dev`), and its own app, "ScanMyLib (dev)" with an orange icon, tagged "dev" where the phone
themes its icons, which installs next to the production app from the Pairing tab of the development web UI. Its first
app build downloads its own Android toolchain. The fake OCR answers instantly with sample pages; the real one
(`--real-ocr`) runs a second engine next to production's (~4.4 GB of VRAM while it works). One development stack runs at
a time. Development builds are versioned from git, after the last release: `0.2.4-dev.27+g1a2b3c4d5e6f` is 27 commits
after `v0.2.3`, and the development app's version code is the time of its build, so that each build installs over the
previous one, whatever its branch.

In a worktree, `scripts/dev.sh` replaces `docker compose` (`scripts/dev.sh build ocr`, `scripts/dev.sh compose exec api
sh`…): it refuses any setting that would reach production or leave the stack's own `DATA_DIR`, and the docker compose
commands and options that could (`cp`, `run -v`, `exec --privileged`…). The guards and their limits are described in
[`docs/SECURITY.md`](docs/SECURITY.md). The repository's rules are in [`.claude/rules/`](.claude/rules/),
indexed in [`CLAUDE.md`](CLAUDE.md). A rehearsal of a deployment, on a throwaway stack, is described in the header of
`scripts/deploy.sh`.

`scripts/check.sh` is the gate: the formatters, linters and type checker of every language (Ruff and mypy for the
Python, ShellCheck and shfmt for the shell scripts, Biome for the web UI, ktlint for the app, zizmor for the workflows),
the unit and integration tests of the scripts, on the host's `python3`, and, in throwaway containers, those of the web
UI, the server and the OCR sandbox, and the Android tests and lint (`scripts/check.sh server web` checks those areas
only). `scripts/check.sh --fix` formats the code and applies the linters' safe fixes: ktlint to the app in place, the
other formatters to the files git tracks in `server/`, `ocr/`, `scripts/` and `.claude/skills/`; read `git diff`
before running what it changed. Each commit of a pull request passes the areas that read what it changes
(`scripts/check.sh --last-commit`), its last commit the whole gate, and every pull request runs it in the continuous
integration (`.github/workflows/ci.yml`, one job per area). Pull requests are merged when it is green.

The tools of the gate are pinned. `scripts/lint/requirements.lock`, the Python tools with their hashes, is regenerated
from `scripts/lint/requirements.in` in a container, and the web UI's `server/scanmylib/web/package-lock.json` the same
way:

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/scripts/lint:/work" -w /work \
    python:3.12-slim-bookworm sh -c 'pip install --quiet --target /tmp/uv uv==0.13.0 && /tmp/uv/bin/uv pip compile \
    requirements.in --generate-hashes --python-version 3.12 --no-header -o requirements.lock'
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e npm_config_cache=/tmp/npm \
    -v "$PWD/server/scanmylib/web:/web" -w /web node:22-bookworm-slim npm install --package-lock-only --ignore-scripts
```

## Releasing

Pull requests never change `VERSION`. A release is a pull request of its own, `chore(release): X.Y.Z`, prepared in a
worktree on `main`:

```bash
cd ~/Dev/scanmylib
git fetch --prune --tags origin
git worktree add --detach .claude/worktrees/release-next origin/main
cd .claude/worktrees/release-next
scripts/release.py            # the next version, why, and the draft of its section of CHANGELOG.md
git switch -c release/v0.4.0  # the branch of the version it proposes, 0.4.0 here, and its worktree:
git -C ~/Dev/scanmylib worktree move .claude/worktrees/release-next .claude/worktrees/release-v0.4.0
cd ~/Dev/scanmylib/.claude/worktrees/release-v0.4.0
scripts/release.py --commit   # writes VERSION and that section, and commits them
scripts/release.py --description   # the pull request's description: what merging does, then the notes
git push --set-upstream origin release/v0.4.0
```

`scripts/release.py` reads the Conventional Commits since the last release: a major release for breaking changes (a
minor one before 1.0), else a minor release for features, a patch otherwise (`--bump` chooses another). The section of
[`CHANGELOG.md`](CHANGELOG.md) is drafted from them, in the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
format, and edited in the pull request: by amending its commit, or with commits that change `CHANGELOG.md` only. Merge
nothing else while it is open. Once it is merged, `.github/workflows/release.yml` tags `vX.Y.Z` on its release commit
(or on the last edit of its notes right after it; later commits belong to the next release) and publishes a GitHub
release with that section as its notes. If a feature, fix or breaking change was merged in between, the notes miss it:
the workflow publishes nothing and says so, and `scripts/release.py`, run again on `main`, completes the release with
it in a new pull request. With Claude Code, the release skill (`.claude/skills/release/`) runs these steps.

## Technical documentation

- [`docs/foundations.md`](docs/foundations.md): the design of the project and its reasons
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): components, data flow, file layout, page ordering algorithm
- [`docs/API.md`](docs/API.md): HTTP API used by the app and the web UI
- [`docs/OCR_SANDBOX.md`](docs/OCR_SANDBOX.md): protocol between the api and the sandbox
- [`docs/SECURITY.md`](docs/SECURITY.md): threat model and guarantees

## Credits

[`CREDITS.md`](CREDITS.md) lists the external work ScanMyLib reuses: the libraries of the api, the web UI and
the app, the OCR engine and its models, and the development tools, with their terms.

## License

ScanMyLib is released under the MIT License: see [`LICENSE`](LICENSE).
