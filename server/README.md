# ScanMyLib — api service

FastAPI server (Python 3.12) implementing `docs/API.md`: it receives scans from
the phone, drives the OCR sandbox over its Unix socket (`docs/OCR_SANDBOX.md`),
organizes the library on disk (`docs/ARCHITECTURE.md`) and serves the web UI
(`scanmylib/web/`, owned by the web UI). Security rules: `docs/SECURITY.md`.

Everything runs in Docker; nothing is installed on the host.

## Layout

| Module | Role |
|---|---|
| `config.py` | `SCANMYLIB_*` environment variables |
| `db.py`, `records.py` | SQLite state (`/state/scanmylib.db`, WAL) and typed rows; an older schema is upgraded in place at start, after a copy is saved as `scanmylib.db.v<N>.bak` |
| `library.py` | all mutations: documents, pages, OCR results; keeps DB and files in sync |
| `ordering.py` | page numbers (arabic, roman, spreads), inference, duplicates, placement and reading order, positions for a manual order, coverage |
| `assemble.py`, `publisher.py` | `document.md`, `document.json`, `INDEX.md`, `library.json` |
| `storage.py` | library folder: atomic writes, `.trash/`, safe file resolution |
| `sanitize.py`, `preview.py` | untrusted OCR Markdown → safe Markdown; Markdown → allowlisted HTML |
| `images.py` | Pillow: upload checks, thumbnails, image sent to the sandbox, re-encoded illustrations |
| `ocr_client.py`, `ocr_result.py`, `ocr_loop.py` | sandbox client, response validation, the single OCR loop |
| `auth.py`, `middleware.py` | token / cookie session / CSRF header, security headers, body limits |
| `api/` | HTTP routes |
| `devtools/fake_ocr.py` | fake sandbox for tests and UI development |

## Build and test

```sh
cd server
docker build --target test -t scanmylib-dev-api:test .
docker run --rm --name scanmylib-dev-pytest --network none --read-only --tmpfs /tmp scanmylib-dev-api:test
```

The test suite runs the real app against the fake sandbox over a real Unix socket.
Pass pytest options after the image name, e.g. `... scanmylib-dev-api:test python -m pytest -k sanitize -x`.

The runtime image (default target) is built by docker compose (`scripts/dev.sh build api`
in a worktree, `scripts/deploy.sh` in production), which also
passes the repository root as the build context `project`: the image gets the
repository's `VERSION`, the version the api reports (`scanmylib/__init__.py`). `scripts/dev.sh`
passes the version of a development build instead, derived from git (build argument
`DEV_VERSION`, `scripts/lib/version.py`). A plain `docker build` of this directory reports
`unknown`.

Dependencies are pinned with hashes in `requirements.lock` / `requirements-test.lock`,
generated from `pyproject.toml` in a throwaway container:

```sh
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/work" -w /work python:3.12-slim-bookworm sh -c '
  pip install --quiet --target /tmp/uv uv==0.13.0 && for extra in "" test; do
    /tmp/uv/bin/uv pip compile pyproject.toml ${extra:+--extra $extra} --generate-hashes --python-version 3.12 \
      --python-platform x86_64-manylinux_2_36 --no-header --annotation-style line \
      -o requirements${extra:+-$extra}.lock; done'
```

## Configuration

| Variable | Default | |
|---|---|---|
| `SCANMYLIB_LIBRARY_DIR` | `/library` | the organized library |
| `SCANMYLIB_LIBRARY_HOST_PATH` | library dir | host path shown in the UI |
| `SCANMYLIB_STATE_DIR` | `/state` | database, `token`, `thumbs/` |
| `SCANMYLIB_OCR_SOCKET` | `/run/scanmylib/ocr.sock` | sandbox socket |
| `SCANMYLIB_PUBLIC_URL` | request origin | URL the phone uses (pairing QR code) |
| `SCANMYLIB_APK_PATH` | `/app-dist/scanmylib.apk` | served at `/download/scanmylib.apk` |
| `SCANMYLIB_TOKEN` | generated in `/state/token` | fixed token (development) |
| `SCANMYLIB_WEB_DIR` | `scanmylib/web` in the image | web UI files (`index.html`, `static/`) |
| `SCANMYLIB_OCR_MAX_SIDE` | `4096` | longest side of the image sent to the sandbox |
| `SCANMYLIB_OCR_TIMEOUT_S` | `900` | timeout of one `/v1/parse` call |
| `SCANMYLIB_ASSEMBLE_DELAY_S` | `2` | quiet time before `document.md` / `INDEX.md` are rewritten |
| `SCANMYLIB_HOST`, `SCANMYLIB_PORT` | `0.0.0.0`, `8765` | listening address |

Time stamps use the container's `TZ` (compose sets `UTC` by default).

## Fake OCR sandbox (development and tests)

`python -m scanmylib.devtools.fake_ocr` implements the sandbox protocol with the
standard library only: no model, no GPU, canned English Markdown with one
generated illustration per page. It is part of the api image.

```text
--socket PATH      Unix socket to create (default /run/scanmylib/ocr.sock)
--delay S          seconds spent per page (default 0.5)
--load-delay S     simulated engine start on first use (default 2)
--evil             return hostile markup (to see the sanitizer at work)
--check            health probe: exit 0 if a sandbox answers on --socket
```

Like the real sandbox, it never replaces a socket that something answers on
(only a stale one), and it refuses to start when `SCANMYLIB_PROJECT` is the
production project (`scanmylib`; compose sets it from `COMPOSE_PROJECT_NAME`):
production's library only ever gets the real OCR's results.

The page number it "finds" is derived from the image size, so you can choose it:
**N = image height mod 1000** (none when 0), and **image width mod 10** selects a
variant: `1` two-page spread (N–N+1), `2` roman numeral (front matter),
`3` number in the running header, `4` no number, other: plain number N.
A 1200×1042 JPEG is page 42, a 1201×1042 one is the spread 42–43,
a 1202×1012 one is page xii.

### Running the api against it (e.g. for web UI work)

The development stack of a worktree runs the api with this fake sandbox, as the
compose service `ocr-fake`: `scripts/dev-env.sh`, then `scripts/dev.sh up`
(`http://localhost:8770`, see `CLAUDE.md`). For quick web UI iterations, two
standalone containers can share a socket directory instead; use your own names,
port and directories, never production's (`scanmylib-api:latest`, port 8765,
production's `DATA_DIR`).

```sh
DEV=/data/USER/scanmylib-dev/webui; mkdir -p $DEV/run $DEV/library $DEV/state
docker build -t scanmylib-webui:latest server/

docker run -d --name webui-fakeocr --network none --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000 \
  -v $DEV/run:/run/scanmylib \
  scanmylib-webui:latest python -m scanmylib.devtools.fake_ocr --delay 1

docker run -d --name webui-api --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000 \
  -p 127.0.0.1:8780:8765 \
  -v $DEV/library:/library -v $DEV/state:/state -v $DEV/run:/run/scanmylib \
  -v "$PWD/server/scanmylib/web:/web:ro" -e SCANMYLIB_WEB_DIR=/web \
  -e SCANMYLIB_TOKEN=dev-token -e SCANMYLIB_PUBLIC_URL=http://127.0.0.1:8780 \
  scanmylib-webui:latest
```

Mounting the web directory makes UI edits visible without rebuilding. Some data:

```sh
T='Authorization: Bearer dev-token'; U=http://127.0.0.1:8780
DOC=$(cat /proc/sys/kernel/random/uuid)
curl -sX PUT -H "$T" -H 'Content-Type: application/json' \
  -d '{"title":"Example Book","author":"Jane Doe","kind":"book"}' $U/api/documents/$DOC
curl -s -H "$T" -F file=@page.jpg -F page_id=$(cat /proc/sys/kernel/random/uuid) \
  -F session_id=$(cat /proc/sys/kernel/random/uuid) -F seq=0 $U/api/documents/$DOC/pages
```

## Notes for the clients

- Authentication: `Authorization: Bearer <token>`, or the `scanmylib_session`
  cookie from `POST /api/session`; with the cookie, `POST`/`PUT`/`PATCH`/`DELETE`
  need `X-ScanMyLib: 1` (403 otherwise).
- CSP: `default-src 'self'; img-src 'self' data: blob:; object-src 'none';
  base-uri 'none'; form-action 'self'; frame-ancestors 'none'` — no inline
  script or style; scripts and stylesheets must be files under `/static/`.
- `GET /api/documents/{id}/html` returns the pages in reading order:
  `<h1>` title, then `<section class="page" data-key="…"><p class="page-marker" data-label="42">Page 42</p>…</section>`
  (`data-label=""` and "Unnumbered page" for a page without number), gaps as
  `<p class="missing-pages" data-range="13–44">Missing pages: 13–44</p>` ("Missing page: 13" for one page),
  unnumbered pages after `<h2 class="unnumbered">Unnumbered pages</h2>`. These texts are English: the web UI
  translates them from the classes and data attributes. Images point to
  `/api/documents/{id}/files/images/…` (authenticated, same origin).
  The Markdown of a page longer than 128 KiB (no real OCR page comes close) is
  previewed as escaped text, `<pre class="markdown-source">…</pre>`.
- Thumbnails show the page as it is OCRed (EXIF orientation and `rotation` applied);
  `/api/pages/{id}/image` is the original file. `rotation` is clockwise.
- `document.md` lists only `done`, non-excluded, non-duplicate pages;
  reprocessing a page removes it from `document.md` until its new result arrives.
