# OCR sandbox protocol (api ⇄ ocr)

Transport: **HTTP/1.1 over a Unix domain socket** at `/run/scanmylib/ocr.sock`
(host path `${DATA_DIR}/run/ocr.sock`). The `ocr` container has no network, so
this socket is its only channel to the outside world. Both containers run as the
same uid; the supervisor creates the socket with mode `0660`.

The supervisor is stdlib-only Python (`ocr/scanmylib_ocr/supervisor.py`, run
with the image's `/usr/local/bin/python3`). It owns the engine lifecycle:

- On the first `/v1/parse` (or `/v1/load`) it starts the vLLM server
  (`/opt/sandbox/venv-vllm`, listening on `127.0.0.1:${OCR_VLLM_PORT}` *inside*
  the sandbox's private network namespace) and the pipeline worker
  (`/opt/sandbox/venv-paddle/bin/python -m scanmylib_ocr.worker`, JSON-lines over
  pipes), in parallel.
- After `OCR_IDLE_UNLOAD_S` seconds (default 300) without requests, it stops
  the worker and vLLM so that **no VRAM is held while idle**.
- Requests are processed **one at a time** (FIFO); concurrent callers wait.

Configuration (env vars of the `ocr` service, set in `compose.yaml`, each
overridable from `.env`):

| variable | default | meaning |
|---|---|---|
| `OCR_ENGINE` | `paddleocr-vl` | engine module (see *Engines* below) |
| `OCR_BACKEND` | `vllm` | `vllm` (model served by vLLM) or `native` (model run by Paddle in the worker, much slower: see *Measurements*) |
| `OCR_IDLE_UNLOAD_S` | `300` | idle delay before the engine is stopped |
| `OCR_VLLM_GPU_MEM` | `0.15` | fraction of the GPU's memory vLLM may use (`--gpu-memory-utilization`); 0.15 ≈ 3.5 GiB on a 24 GiB card, the smallest value that is not slower |
| `OCR_VLLM_PORT` | `8118` | vLLM port on the sandbox's loopback |
| `OCR_MAX_CONCURRENCY` | `16` | VL sub-requests (one per layout block) in flight |
| `OCR_SOCKET` | `/run/scanmylib/ocr.sock` | API socket |
| `OCR_START_TIMEOUT_S` | `600` | engine start longer than this → `engine_unavailable` |
| `OCR_JOB_TIMEOUT_S` | `600` | page longer than this → `processing_failed`, engine restarted |

## `GET /health`

Always answers immediately (never blocks on a running job).

```json
{
  "status": "ok",
  "engine": {
    "name": "paddleocr-vl",
    "state": "idle",            // idle | starting | ready | stopping | error
    "backend": "vllm",
    "since": "2026-10-12T20:00:00+00:00",
    "last_error": null,           // string after a failed start or an engine crash
    "idle_unload_s": 300
  },
  "busy": false,                  // a page is being processed right now
  "queue": 0,                     // requests waiting
  "processed": 12,                // pages parsed successfully since container start
  "versions": { ... },            // content of /opt/sandbox/MANIFEST.json ({} when missing, unreadable or not an object)
  "gpu": { "name": "NVIDIA GeForce RTX 3090", "memory_used_mb": 5120, "memory_total_mb": 24576 }  // or null
}
```

`gpu` is the whole device (all processes, also outside the sandbox). When
`/health` is polled often, the reading may be up to 30 s old (refreshed in the
background); after a pause or an engine start/stop it is taken on the spot.

## `POST /v1/parse`

Request body: the raw image bytes. `Content-Type`: `image/jpeg`, `image/png` or
`image/webp`. Max body size 40 MiB, sent with a `Content-Length` (no chunked
encoding). Optional query parameters (`1`/`0`, also `true`/`false`):

| param | default | meaning |
|---|---|---|
| `orientation` | `1` | auto-rotate pages photographed at 90/180/270° (`use_doc_orientation_classify`) |
| `unwarp` | `0` | flatten curved/warped pages with UVDoc (`use_doc_unwarping`) |
| `charts` | `0` | convert charts to tables (`use_chart_recognition`) |
| `request_id` | – | echoed back, used in logs (`[A-Za-z0-9._:-]`, other characters become `_`; generated if absent) |

The call blocks until the page is processed (first call after idle includes the
engine start, typically 40 s — callers should use a long timeout, e.g. 900 s).

Response `200`:

```json
{
  "request_id": "…",
  "width": 2480, "height": 3508,          // size of the image the layout coordinates refer to
  "markdown": "## Title\n\nText…\n\n<div style=\"text-align: center;\"><img src=\"imgs/img_in_image_box_93_1129_1104_1716.jpg\" alt=\"Image\" width=\"61%\" /></div>\n",
  "images": [
    { "name": "img_in_image_box_93_1129_1104_1716.jpg", "mime": "image/jpeg", "data_b64": "…" }
  ],
  "blocks": [
    { "label": "paragraph_title", "content": "Title", "bbox": [x1, y1, x2, y2], "order": 1 },
    { "label": "number", "content": "42", "bbox": [ … ], "order": null }
  ],
  "page_numbers": ["42"],                 // contents of blocks labeled "number", in reading order
  "page_continuation": null,              // { "starts_mid_paragraph": …, "ends_mid_paragraph": … } if the engine knows
  "preprocess": { "angle": 0, "unwarped": false },
  "engine": { "name": "paddleocr-vl", "pipeline_version": "v1.6", "model": "PaddleOCR-VL-1.6", "backend": "vllm" },
  "timings": { "queue_s": 0.0, "load_s": 41.2, "infer_s": 2.31 }
}
```

Rules:

- Every image referenced by `markdown` appears in `images`, and it is referenced
  exactly as `imgs/<name>` (in `<img src="imgs/<name>">` or `![…](imgs/<name>)`).
  `name` is a plain basename (`[A-Za-z0-9._-]+`, always `….jpg`); `images` is in
  reading order and holds only images the Markdown shows.
- `markdown` excludes page furniture (page numbers, running headers/footers;
  footnotes and sidebars are kept, see `MARKDOWN_IGNORE_LABELS`), but `blocks`
  contains *all* detected blocks, including `number`, `header`, `footer`, and
  empty `text` blocks whose content was merged into the previous block (a
  paragraph continued in the next column).
- `blocks[].bbox` are pixel coordinates in the processed image (`width`×`height`):
  after rotation/unwarping, and after downscaling of images above 40 Mpx.
- Tables are HTML `<table>` elements inside the Markdown; figure and table
  captions are centered with `<div style="text-align: center;">`.
- `preprocess.angle` is the rotation that was undone (0, 90, 180 or 270).
- PaddleOCR-VL does not report paragraphs running across a page break:
  `page_continuation` is always `null` with this engine.

Errors (JSON `{"error": "<code>", "detail": "<message>"}`):

| status | error | when |
|---|---|---|
| 400 | `bad_request` | missing `Content-Length`, chunked body, invalid query parameter |
| 400 | `bad_image` | body is not a decodable JPEG/PNG/WebP image, or is larger than 250 Mpx |
| 413 | `too_large` | body > 40 MiB |
| 415 | `unsupported_type` | unsupported Content-Type |
| 503 | `engine_unavailable` | engine failed to start (detail has the reason, e.g. not enough free GPU memory); every page waiting for that start gets it; the api retries later |
| 500 | `processing_failed` | pipeline error on this page, the engine crashed / exceeded `OCR_JOB_TIMEOUT_S` on it, or its result exceeded 256 MiB (the engine is then restarted for the next page) |

## `POST /v1/load`

Starts the engine now (useful to pre-warm when the phone starts uploading).
Returns `202 {"state": "starting"}` or `200 {"state": "ready"}`.

## `POST /v1/unload`

Stops worker + vLLM immediately (frees VRAM) and answers `200 {"state": "idle"}`
once they are stopped. If a page is being processed, unload happens right after
it (pages still queued then start the engine again).

## Client notes (api side)

- Use `httpx` with `httpx.AsyncHTTPTransport(uds="/run/scanmylib/ocr.sock")`
  and base URL `http://ocr`.
- Treat every field of the response as untrusted (sizes, names, HTML in
  Markdown, base64 payloads): see `docs/SECURITY.md`.

## Inside the sandbox

```
supervisor (python3, stdlib)          HTTP on the Unix socket, FIFO queue, lifecycle
 ├─ vllm serve …  (venv-vllm)         own process group; its engine core is a child
 └─ worker        (venv-paddle)       own process group; PaddleOCRVL pipeline
      protocol: two dedicated pipes (fds named in $SCANMYLIB_OCR_PROTOCOL_FDS),
      one JSON object per line; stdout/stderr are only logs (relayed to `docker logs`)
```

- **Stopping the engine** sends the worker a `shutdown` message, then
  SIGTERM/SIGKILL to each whole process group: the GPU memory goes back to its
  baseline (measured: < 50 MiB difference).
- **vLLM command**: the official recipe
  (`--trust-remote-code --max-num-batched-tokens 16384 --no-enable-prefix-caching
  --mm-processor-cache-gb 0`, served name `PaddleOCR-VL-1.6`) plus
  `--trust-request-mm-kwargs` (PaddleOCR sends per-block `min_pixels`/`max_pixels`,
  which vLLM 0.31 refuses otherwise — the only client is the worker, on the
  sandbox's loopback), `--max-model-len 16384` (a block image plus up to 4096
  generated tokens fits; the model's default 131072 would need a larger GPU
  budget) and `--disable-uvicorn-access-log`. `VLLM_USE_FLASHINFER_SAMPLER=0`:
  FlashInfer's sampler is compiled at runtime with nvcc, which the sandbox
  doesn't have.
- **Read-only `/opt/sandbox`**: caches go to `/var/cache/ocr` (kept across
  restarts: vLLM's torch.compile cache, Triton kernels, PaddleX cache — it
  shortens the next starts by ~30 s) or to the `/tmp` tmpfs (`HOME`, page images
  in flight). Models are loaded from explicit directories, never downloaded.
- **Worker warm-up**: the worker runs its CNN models once on a blank page while
  vLLM starts. The first page after a start still takes ~8 s (mostly vLLM's first
  multimodal requests), then ~2 s.

## Engines

An engine is a module of `ocr/scanmylib_ocr/engines/` registered in its
`__init__.py`. It provides an `EngineSpec` (stdlib only, read by the
supervisor: worker command, model-specific `vllm serve` arguments, the
`engine` object of results) and a `PageEngine` (worker side: `load()`,
`parse(image_path, options)` returning the response fields above). Another
vLLM-served OCR model is added by writing such a module, installing its
weights with `ocr/setup/install.sh`, and selecting it with `OCR_ENGINE`.

## Measurements (RTX 3090, 2026-10-12)

Test set: 10 public-domain pages of 19th-century French scientific books
with proofread reference transcriptions, plus 15 simulated phone photos
(perspective, book curvature, uneven lighting, 90° rotation). The test set and
its list of sources stay outside the repository, in `${DATA_DIR}/testdata/`
(`sources.json`, provenance in `SOURCES.md`); tools in `ocr/bench/`.

| | value |
|---|---|
| engine start (`/v1/load` → ready), compile caches warm | 37–40 s |
| engine start, first ever (empty `/var/cache/ocr`) | 70 s |
| first page after a start | ~8 s |
| following pages (scans 2480 px, photos 3000×4000) | 1.8 s median (1.2–3.0 s) |
| throughput, pages sent one after another | 31 pages/min |
| VRAM while loaded, `OCR_VLLM_GPU_MEM=0.15` | 4.4 GB (vLLM 3.5 GB + worker 0.9 GB), peak +0.4 GB |
| VRAM while loaded, `OCR_VLLM_GPU_MEM=0.20` / `0.30` | 5.6 GB / 8.0 GB, same speed |
| VRAM after unload (explicit or idle) | back to the baseline, no sandbox process left on the GPU |
| `OCR_VLLM_GPU_MEM` ≤ 0.12 | vLLM cannot start (KV cache too small) |
| `OCR_BACKEND=native` | starts in 8 s, 8.2 GB, CPU-bound: 7–9 s on light pages, > 5 min on a dense page — not recommended |

Quality (character error rate against the reference transcriptions, table
cells included): clean scans 2.1 %; photos: 90° rotated 2.0 % (20 % with
`orientation=0`), uneven lighting 3.9 %, perspective 3.3 %, curved pages 3.7 %
with `unwarp=0` → 1.8 % with `unwarp=1` (text pages; the table page varies
between 1.4 % and 14 %: table structure is the weak point). Page numbers found
on 23/25 images.
Recommended: `orientation=1` always (no measurable cost), `unwarp=1` for bound
books photographed open (halves the errors on curved pages, slightly worse on
flat pages: 2.4 % vs 2.1 %, +0.1 s per page), `unwarp=0` for flat documents.
