# ScanMyLib — architecture

Scan multi-page documents and (parts of) books with an Android phone, in any
order and over many sessions; OCR them on the PC's NVIDIA GPU inside a sandbox;
organize the results on disk as Markdown + illustrations that AI agents can read.

```
 Android app ──HTTP (LAN, bearer token)──▶  api container  ──HTTP over Unix socket──▶  ocr container (sandbox)
 (ML Kit scanner,                           (FastAPI, our code)                          network_mode: none, GPU only
  offline upload queue)                      ├─ SQLite state  (/state)                    ├─ supervisor (stdlib HTTP on UDS)
                                             ├─ library files (/library)                  ├─ vLLM server (127.0.0.1 inside)
 Web UI (PC or phone browser) ──────────────▶└─ web UI static files                       └─ PaddleOCR-VL pipeline worker
```

## Components

| Component | Where | Trust | Network | Sees |
|---|---|---|---|---|
| `ocr` (sandbox) | `ocr/` → image `scanmylib-ocr` | **untrusted** (Paddle, vLLM, model code) | **none** (only `lo`) | `/opt/sandbox` (ro: venvs+models), `/run/scanmylib` (socket), `/var/cache/ocr` (rw cache), tmpfs `/tmp` |
| `ocr-setup` | same image, profile `setup` | untrusted | yes (downloads only) | only `/opt/sandbox` (rw: `SANDBOX_SETUP_DIR`, set in production's `.env` only) |
| `api` | `server/` → image `scanmylib-api` | ours | LAN (published port) | `/library`, `/state`, `/run/scanmylib`, `/app-dist` (ro) |
| `ocr-fake` (development only) | api image, profile `fake-ocr`: canned results instead of `ocr`; refuses the production project and a socket that a sandbox serves | ours | **none** | `/run/scanmylib` (socket), tmpfs `/tmp` |
| Android app | `android/` | ours | LAN | its own app storage |
| APK builder | throwaway `eclipse-temurin` container | Google/Gradle toolchain (checksums verified) | yes (build only) | `android/`, `VERSION` (ro), SDK/Gradle caches under `ANDROID_DIR` (the development stack has its own) |
| APK signer | second throwaway container | ours | **none** | unsigned APK, build-tools (ro; it runs copies of `zipalign` and `apksigner` checked against pinned SHA-256, and signs only the variant's application id and versionCode), the signing key `ANDROID_KEYSTORE_DIR` (ro; the build never sees it) |

Nothing is installed on the host itself. Host paths are configured in `.env` (a strict `KEY=VALUE` format that every
script checks, `scripts/lib/stack.py`), which also names the stack (`COMPOSE_PROJECT_NAME`, `IMAGE_PREFIX`: `scanmylib`
in production, written by `scripts/setup.sh`; a worktree's development stack is `scanmylib-dev`, written by
`scripts/dev-env.sh`, see `CLAUDE.md`):

- `DATA_DIR` (e.g. `/data/USER/scanmylib`) → `run/` (Unix socket), `ocr-cache/`, `state/` (api DB, token, thumbnails), `app/` (built APK), `backups/` (state copies made by `scripts/deploy.sh`), `logs/`.
- `SANDBOX_DIR` (e.g. `DATA_DIR/sandbox`) → the OCR venvs and models, mounted read-only; `SANDBOX_SETUP_DIR` (production only, the same directory) is where `ocr-setup` writes them.
- `ANDROID_DIR` (e.g. `DATA_DIR/android`) → Android SDK, Gradle caches, signing key (`keystore/`, or `ANDROID_KEYSTORE_DIR`: the development stack uses production's key, read-only, with its own toolchain).
- `LIBRARY_DIR` (e.g. `~/Documents/ScanMyLib`) → the organized library (pure content, see below).

Every path variable is required by `compose.yaml` (`${VAR:?}`): a `.env` without one makes docker compose stop instead
of mounting a host directory such as `/run`. In a worktree, `scripts/dev.sh` checks what docker compose resolves for
the stack before running it, and refuses any project, image, port or host path that production owns, any host path
outside the stack's own `DATA_DIR` (production's models and signing key excepted, read-only) and any service setting
outside an allowlist (`scripts/lib/stack.py`). In production's checkout, `scripts/prod.sh compose ...` runs docker
compose with production's `.env` only.

## Security model (summary — details in `docs/SECURITY.md`)

- The sandbox has **no network interface** besides loopback, a **read-only root FS**, **no capabilities**, `no-new-privileges`, runs as the user's uid but **sees no host file** except the dirs listed above. It cannot read secrets, cannot exfiltrate, cannot persist outside its cache dir.
- Packages and model weights are downloaded **once** by `ocr-setup` (network, but it only sees the sandbox dir, `SANDBOX_SETUP_DIR`), pinned by version / Hugging Face commit; no Paddle code ever runs with network access.
- Everything coming out of the sandbox is **untrusted data**: the api validates sizes, re-encodes images with Pillow, sanitizes image names and HTML in Markdown, renders previews through an allowlist sanitizer, and serves the web UI with a strict CSP.
- The api requires a random bearer token (shown as a QR code for pairing). The web UI exchanges it for an HttpOnly SameSite=Strict cookie.

## Data flow of one page

1. The phone captures pages from one of three sources: the ML Kit document scanner (auto-crop; retouching level set in the app: none / filters / full), the app's own camera (CameraX, one tap per page, original full-resolution JPEG, no processing), or photos imported from the gallery (system photo picker, ordered by EXIF capture time, uploaded untouched). Each page gets a client UUID (`page_id`), a `session_id` (one per scanner launch), a `seq` (order in the session), `captured_at`, and optionally a `page_number_hint`.
2. Pages are stored in the app's private storage and uploaded by a WorkManager job when the PC is reachable (offline-first; retries with backoff; idempotent on `page_id`).
3. The api stores the original in `<doc>/scans/`, makes a thumbnail, inserts a `queued` page row.
4. The api's single OCR loop sends the image (EXIF-transposed, rotated if requested, re-encoded, metadata stripped) to the sandbox over the Unix socket. The sandbox lazily starts vLLM + the pipeline worker on first use and unloads them (freeing VRAM) after `OCR_IDLE_UNLOAD_S` of inactivity.
5. The api validates the result, writes `pages/<key>.md`, `images/<key>_<n>.jpg`, `ocr/<key>.json`, updates the page row (detected page numbers...), then re-assembles the document (`document.md`, `document.json`) and the library index (`INDEX.md`, `library.json`).

## Library layout (LIBRARY_DIR) — the deliverable for agents

```
ScanMyLib/
  INDEX.md                      # human/agent index of all documents (title, author, coverage, link)
  library.json                  # same, machine-readable
  .trash/                       # deleted documents/pages are moved here, never hard-deleted
  <slug>/                       # one folder per document, slug from title at creation (stable)
    document.md                 # assembled Markdown: YAML front matter + pages in reading order
    document.json               # metadata + ordered page list + coverage/gaps (+ per-page info)
    pages/<key>.md              # one Markdown file per scanned page (images → ../images/...)
    images/<key>_<n>.jpg        # illustrations/photos cropped by the OCR layout model
    ocr/<key>.json              # raw OCR result: blocks with labels, bboxes, reading order
    scans/<key>.<ext>           # original photo as received from the phone
```

`<key>` = `<captured_at as YYYYMMDD-HHMMSS>_<first 8 hex chars of page_id>` — stable, sorts by capture time.

`document.md` format:

```markdown
---
title: "Example Book"
author: "Jane Doe"
kind: book
source: "ScanMyLib — OCR PaddleOCR-VL-1.6"
pages_scanned: 42
coverage: "1–12, 45–60"
missing: "13–44"
updated: 2026-10-12T20:00:00+02:00
---

# Example Book

<!-- page 1 · scan 20261012-201530_1a2b3c4d -->

…page markdown (images as images/<key>_<n>.jpg)…

<!-- missing pages: 13–44 -->

<!-- page 45 · scan … -->
…

## Unnumbered pages

<!-- scan … -->
…
```

## Page numbering & ordering (out-of-order, multi-session scanning)

For each page:

- `detected_numbers`: strings from OCR blocks labeled `number` (page-number blocks). If none, fall back to a standalone number at the very start or end of a `header`/`footer` block text (`^\s*(\d{1,4})\b` / `\b(\d{1,4})\s*$`). Arabic `^\d{1,4}$` → int. Roman numerals (`^[ivxlcdm]+$`, case-insensitive) → front matter (sorted before arabic pages). Two consecutive arabic numbers (n, n+1) on one image → spread: number = n, `number_end` = n+1.
- Effective number = `manual_number` (set by the user) ?? detected ?? `hint_number` (from the phone) ?? inferred.
- Inference: within the same `session_id` ordered by `seq`, a page without number takes `prev + d` from the nearest previous numbered page (distance `d` in seq), in its numbering system (arabic, or roman front matter), unless that reaches the next page numbered in that system (an unnumbered plate between pages 12 and 13 stays unnumbered); without a previous numbered page, `next − d` from the nearest following one (only if ≥ 1). No system is carried across the start of the main text (page 1): between a roman page and an arabic page n, the page `d` before n is `n − d` when that is ≥ 1 (and above the previous arabic page of the session, if any), else front matter `prev + d` — xxv, ?, ?, 3 gives xxv, 1, 2, 3 and xxv, ?, ?, 2 gives xxv, xxvi, 1, 2. Between an arabic page and a roman one (front matter scanned after the main text), only the arabic `prev + d` applies, below the next arabic page: no roman number is counted back. Manual numbers always win, and anchor the inference like the other numbers. `number_source = "inferred"`.
- Duplicates: among non-excluded `done` pages with the same effective number, the most recently captured one wins; others get `duplicate_of` and are left out of `document.md` (kept on disk, visible in UI).
- Placement: the pages of the reading order (`done`, not excluded, not duplicates) sit on a number line, at `position ?? natural ?? anchored` (API field `placement`: `manual`, `number`, `session`, or `unplaced` when none applies):
  - `natural`: page n (or the spread n–n+1) at n, roman front matter v at v − 10000 (before page 1); none without effective number.
  - `position` (column `pages.position`, REAL): a place chosen by the user, set only by `PUT /api/documents/{id}/order` and cleared by its `DELETE`. It changes neither the number nor the label, coverage or duplicates.
  - `anchored` (no position, no number): within the page's session, `prev + d × 0.0001` from the nearest previous page that has a position or a number (distance `d` in seq), else `next − d × 0.0001` from the nearest following one. Excluded pages are not anchors; duplicates and pages waiting for OCR are. The title page and preface scanned just before page 1 stay before it; a plate stays after the page scanned before it.
- Reading order: placed pages by (place, captured_at, id); then unplaced pages (e.g. unnumbered pages scanned in a session of their own) by (session start, seq, captured_at), under "Unnumbered pages" when other pages have a number. If no page has a place (typical for letters/forms), that is the capture order. A gap in the numbering is marked just before the page that follows it.
- Manual order (`PUT /api/documents/{id}/order`, the ids of exactly the pages of the reading order, else 409): only the pages the user actually moved get a `position` (plus, when needed, a session neighbor that would otherwise follow a moved page). Numbered pages keep their natural place along a longest increasing subsequence; unnumbered pages whose automatic place (session anchoring, or unplaced at the end) already gives the wanted order keep no position. Every trial is checked against the real layout, so the result is always exactly the wanted order, and a page scanned later still slots in by its number. Details and examples: `docs/API.md`, "Page order". `DELETE …/order` returns to the automatic order.
- Coverage: ranges of effective arabic numbers of included pages, plus gaps between min and max.

## OCR engine

PaddleOCR-VL-1.6 pipeline (`pipeline_version="v1.6"`: PP-DocLayoutV3 layout detection + reading order, VL recognition by the 0.9B model served by vLLM inside the sandbox; optional orientation classification and UVDoc unwarping). The sandbox protocol (`docs/OCR_SANDBOX.md`) is engine-agnostic: another model can be plugged in by implementing a new worker.
