# ScanMyLib

Scan documents and books with your Android phone, a few pages at a time, in
any order and over many sessions. Your PC (RTX 3090) runs them through
**PaddleOCR-VL-1.6**, locked in a Docker sandbox without network access. The
result is filed on your disk as Markdown, with the extracted illustrations,
ready for your AI agents to read. The phone app and the web UI are in English,
or in French on a phone or browser set to French.

```
Phone (ScanMyLib app)  ──Wi-Fi──▶  PC: api ──socket──▶ OCR sandbox (GPU, no network)
                                        │
                                        ▼
                         ~/Documents/ScanMyLib/<document>/document.md + images/
```

## Installation

Requirements: Docker with access to the NVIDIA GPU (CDI `nvidia.com/gpu`),
already set up on your PC. **Nothing else is installed on the system**:
everything runs in containers.

```bash
cd ~/Dev/scanmylib
scripts/setup.sh          # everything: images, OCR sandbox (~16 GB), APK, start, checks
```

Paths are set in `.env`:

| Variable | Role | Current value |
|---|---|---|
| `LIBRARY_DIR` | the organized library | `/home/user/Documents/ScanMyLib` |
| `DATA_DIR` | sandbox (environments + models), state, socket, caches, Android SDK | `/data/user/scanmylib` |
| `PUBLIC_URL` | address of the PC as seen by the phone | `http://192.168.1.10:8765` |

The services restart automatically with Docker (`restart: unless-stopped`):
there is no systemd service to install.

## Pairing the phone

1. On the PC, open the web UI at the address printed by `scripts/setup.sh`
   (`http://localhost:8765/#token=…`), then the **Pairing** tab.
2. With the phone's camera, scan the QR code of step 1 to download the APK,
   then install it. Android asks once to allow installs from the browser.
3. Open the ScanMyLib app: on the **Pair with PC** screen, tap **Scan the QR
   code** and aim at the QR code of step 2. The app then knows the PC's
   address and its token. Without a QR code reader, type the **PC address**
   and the **Token** shown under the QR code, then tap **Test and pair**.

The phone and the PC must be on the same network. Away from home, the app
keeps the pages and sends them as soon as the PC is reachable again. To send
from elsewhere, use a VPN (WireGuard, Tailscale…) rather than opening a port.

## Scanning

- **New document**: title, author, kind (book or document). For a book,
  flattening of pages curved by the binding (**Bound book**) is on by default.
- **Scan pages** offers three capture sources:
  - **Google scanner**: detects the edges and crops the page. The **Google
    scanner retouching** setting (in the app's Settings) chooses between
    **None — crop only** (the default), **Filters** and **Full** (filters plus
    finger and stain removal). This scanner never returns the original photo.
    To chain pages, tap "+" on its preview screen.
  - **Camera, page by page**: the app's own camera stays open. One tap = one
    photo = one page, at full resolution and without any retouching. Turn the
    page and tap again, then **Done**. Only this mode asks for the camera
    permission.
  - **Import photos**: photos taken with any app, put back in shooting order
    (EXIF date) and sent as they are. Accepted formats: JPEG, PNG and WebP (no
    HEIC). A photo that cannot be read (a cloud photo while offline…) or that
    is too large for the PC (over 40 MB or 120 megapixels) is skipped with a
    message; the others are imported.
- **First page number** (optional): only for pages without a printed number
  that you want numbered; with **Consecutive pages** (on by default), the
  following pages get the next numbers. Leave it blank for front matter
  (cover, title page, preface).
- **Before sending**, the pages wait on the phone: tap a thumbnail to see it
  full size or remove it, **Add pages** to complete the series (with any
  source), **Send** to queue them for upload. **Later** (or Back) keeps them on
  the phone: the library then shows "N pages to check before sending".
  **Discard** asks for confirmation: these pages exist nowhere else.

The web UI can also add pages to a document from the PC or the phone's
browser: import photos, or take a photo.

## Page order

Pages can arrive in any order, in several batches.

- **Number of each page**, by priority: the one typed by hand, else the
  printed one (read by the OCR), else the "first page number" hint, else a
  number inferred from the neighboring pages of the same session. Roman
  numerals come before page 1.
- **Pages without a number**: they are placed next to their neighbors from
  the same session. Front matter scanned just before page 1 therefore comes
  before page 1, and a plate scanned between pages 12 and 13 stays between
  them. An unnumbered page scanned on its own, in a session without any
  numbered page, goes to the end ("Unnumbered pages"), where you can place it
  by hand.
- **Organize by hand**: in the web UI, on a document, the **Organize** button.
  Drag and drop a page or a selection (Shift+click for a range), or use **Move
  selection…**. The displayed numbers do not change, only the order does.
  **Restore automatic order** undoes everything.
- **Coverage**: "1–12, 45–60" and the missing pages are shown in the app and
  the web UI.
- **Rescanned page**: the most recent one replaces the old one, which stays
  visible as a duplicate.

OCR runs in the background. The model loads onto the GPU at the first page,
then unloads after 5 minutes of inactivity to free the VRAM for your other
models. Measured on your RTX 3090:

| | |
|---|---|
| model start | ~40 s (70 s the very first time) |
| speed | ~1.8 s per page, ~30 pages per minute |
| VRAM while processing | ~4.4 GB (0 when idle) |
| character error rate (19th-century French printed pages) | ~2 % on scans, 2 to 4 % on photos |

Settings in `.env`, followed by `docker compose up -d ocr`:

- `OCR_IDLE_UNLOAD_S`: delay before the VRAM is freed (300 s by default).
- `OCR_VLLM_GPU_MEM`: share of the VRAM reserved, 0.15 by default. Do not go below 0.15, or vLLM does not start.

Flattening of curved pages (UVDoc) is on by default for books: on curved
pages, it halves the errors. For a document photographed flat, turn it off in
the document's details.

## Web UI

Open it on the PC (`http://localhost:8765`) or from the phone's browser. Its
header shows the state of the OCR engine.

- **Library**: every document with its cover, its pages and its coverage.
- **Document**: the pages grid (in the document, unnumbered, waiting for OCR
  or failed, excluded, duplicates), the coverage, the downloads of
  `document.md` and of a `.zip` archive, and:
  - **Read document**: the reading view, with the whole document in reading
    order, as in `document.md`, and its formulas typeset; a marker at the
    start of each page opens that page, and a list of the pages jumps to any
    of them.
  - **Organize**: reorder the pages by hand (see "Page order").
- **Page**: the scan next to the recognized text, the page number (type one
  by hand to correct it), rotation, exclusion from the document, new OCR
  run, deletion.
- **Pairing**: installing the app and pairing the phone.

## What is produced (for your agents)

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

`document.md` holds markers such as `<!-- page 42 · scan … -->` that make it
possible to cite a page. Tables are HTML and formulas are LaTeX.

Nothing is ever erased: deleted documents and pages go to
`ScanMyLib/.trash/`.

## Backup

- `LIBRARY_DIR` (the library): this is your content.
- `DATA_DIR/state`: database (page order, manual settings) and token.
- `DATA_DIR/android/keystore`: the app's signing key. Without it, a new
  version of the APK cannot update the installed app.

The rest (`DATA_DIR/sandbox`, caches, Android SDK) is reinstalled by
`scripts/setup.sh`.

## Security

The OCR sandbox has **no network access**. It sees **none of your files** and
runs read-only, without privileges. Details and checks:
[`docs/SECURITY.md`](docs/SECURITY.md) and `scripts/verify-sandbox.sh`.

## Operations

```bash
docker compose ps                          # state of the services
docker compose logs -f api ocr             # logs
docker compose restart api                 # restart the api
docker compose down                        # stop everything
scripts/verify-sandbox.sh                  # prove the sandbox is isolated
scripts/e2e_test.py photo1.jpg photo2.jpg  # end-to-end test (like the phone)
scripts/build-apk.sh                       # rebuild the APK
```

## Technical documentation

- [`docs/foundations.md`](docs/foundations.md): the structuring choices of the project
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): components, data flow, file layout, page ordering algorithm
- [`docs/API.md`](docs/API.md): HTTP API used by the app and the web UI
- [`docs/OCR_SANDBOX.md`](docs/OCR_SANDBOX.md): protocol between the api and the sandbox
- [`docs/SECURITY.md`](docs/SECURITY.md): threat model and guarantees
