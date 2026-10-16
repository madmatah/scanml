# Foundations

The structuring choices of ScanMyLib, as they stand today. When one of them changes, update this file to describe the
new state (the history of decisions is kept outside the repository).

## Purpose

Scan documents and books with an Android phone, a few pages at a time, in any order and over many sessions; OCR them on
a Linux PC with an NVIDIA GPU; keep a library of Markdown files with their illustrations that AI agents can read as
reference material.

## Principles

- **Untrusted OCR stack, sandboxed.** The OCR engine (PaddlePaddle, PaddleOCR, vLLM and model code) runs in a Docker
  container with no network interface, a read-only root filesystem, no capabilities and no access to the user's files.
  It talks to our api only through a Unix socket. Its output is treated as untrusted data.
- **Nothing installed on the host.** Every build, test and runtime component runs in Docker containers. Heavy data
  (Python environments, model weights, Android SDK) lives under `DATA_DIR`, outside the repository.
- **Pinned downloads.** Untrusted packages and weights are downloaded once by a dedicated setup container, pinned by
  version or commit; no OCR engine code runs with network access.
- **Engine-agnostic pipeline.** The api depends only on the sandbox protocol (`docs/OCR_SANDBOX.md`). OCR output is
  kept as the engine produces it; there is no post-processing that compensates for a particular model.
- **The library is the product.** Each document is a folder with `document.md` (pages in reading order), per-page
  Markdown, cropped illustrations, raw OCR results and the original scans; `INDEX.md` and `library.json` list the
  documents. Nothing is hard-deleted: deletions move to `.trash/`.
- **Offline-first phone.** The phone keeps every page until the PC has it, retries uploads on its own, and all creates
  are idempotent (client-generated ids).
- **Private content stays private.** No real document or book name ever appears in the repository.
- **English reference, French translations.** Code, documentation and UI reference text are in English; the UI also
  ships a French translation.

## Current choices

| Topic | Choice |
|---|---|
| OCR engine | PaddleOCR-VL-1.6 (PP-DocLayoutV3 layout + 0.9B vision-language model) served by vLLM inside the sandbox |
| GPU use | the engine starts on the first page and unloads after 300 s idle; ~4.4 GB of VRAM while loaded |
| OCR options | page orientation detection always on; unwarping of curved pages on by default for books; footnotes and sidebars kept in the Markdown |
| Formulas | kept as LaTeX in the Markdown; rendered with KaTeX (vendored, MIT) in the web UI |
| Page order | a page is placed by its manual position, else its effective page number (roman front matter before arabic pages), else next to its neighbors in the same capture session, else at the end; manual reordering stores positions only for the pages moved |
| Phone capture | Google's ML Kit document scanner (retouching off by default), the app's own camera (one original photo per tap) or photos imported from the gallery, from the app or shared to it by another app (only content that app's provider grants) |
| Android build | Kotlin and Jetpack Compose; built and tested in throwaway containers; signed offline with a key kept outside the repository; no R8 shrinking |
| App updates | offered by the paired PC (`/api/health` describes the APK it publishes), asked when the library shows or is refreshed, at most once an hour, again once the library reaches the PC after a failed check, and from the settings; the app downloads it from that PC, checks its digest, package, version and signing certificate (where Android reports it), and hands it to Android's installer, which asks the user each time |
| Pairing and access | random bearer token, shared by QR code; plain HTTP on the local network; remote use through a VPN |
| Deployment | Docker Compose (`api`, `ocr`), restarted automatically with Docker |
| Releases | one version for the api and the app (`VERSION`, tagged `vX.Y.Z`); development builds versioned from git (`0.2.4-dev.27+g1a2b3c4d5e6f`, 27 commits after `v0.2.3`), the dev app's versionCode being the time of its build; changes on branches and worktrees, tried on a separate development stack and app (`fr.scanmylib.dev`); production deployed only by `scripts/deploy.sh` from `main`, in production's checkout; the scripts' guards protect production from misconfiguration, mistakes in a branch and compromised build dependencies, not from a deliberately malicious branch (`docs/SECURITY.md`) |
