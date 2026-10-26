---
paths:
  - "ocr/**"
  - "compose.yaml"
  - "**/Dockerfile"
  - ".env.example"
  - "scripts/**"
  - ".claude/skills/running-tests/SKILL.md"
  - "server/scanmylib/ocr_*.py"
  - "server/scanmylib/images.py"
  - "server/scanmylib/sanitize.py"
  - "server/scanmylib/preview.py"
  - "server/scanmylib/domain/assemble.py"
  - "server/scanmylib/devtools/**"
  - "android/app/src/main/AndroidManifest.xml"
---

# Isolation

The user's account holds many secrets, the OCR stack (PaddlePaddle, PaddleOCR, vLLM and model code) is untrusted, and
production runs next to the development stack on the same machine. These rules keep each of them in its place.

## The OCR sandbox

- **The `ocr` service stays isolated:** `network_mode: none`, a read-only root filesystem, no capabilities,
  `no-new-privileges`, a non-root user, and no host mount besides the read-only `SANDBOX_DIR`, the socket directory and
  its cache directory. `scripts/verify-sandbox.sh` must pass on it.
- **The sandbox's image keeps that isolation wherever a script or a procedure starts it outside the service,** apart
  from `ocr-setup`, which "Untrusted components are downloaded only by the `ocr-setup` container" allows: such a
  container, like the run of the sandbox's tests in the `running-tests` skill and in `scripts/check.sh`, has no network
  (`--network none`), a read-only root filesystem, with a tmpfs for what it must write such as `/tmp`, no capabilities
  (`--cap-drop ALL`), `no-new-privileges`, a non-root user, and no host mount besides the read-only `SANDBOX_DIR`, the
  code it runs, read-only, and a working directory of its own, never the library or production's state.
- **Untrusted components are downloaded only by the `ocr-setup` container,** pinned by version or commit, and no Paddle
  code runs with network access. `ocr-setup` writes the sandbox through `SANDBOX_SETUP_DIR`, which only production's
  `.env` sets; every other container mounts `SANDBOX_DIR` read-only.
- **Everything the sandbox returns is untrusted data:** its sizes, names, HTML and Markdown. The api checks every size
  and count against its limits, names every file it writes itself, re-encodes images with Pillow, sanitizes the Markdown
  before writing it, renders HTML through its allowlist sanitizer, and serves the web UI with a strict Content Security
  Policy. A change to what the api reads from the sandbox keeps each of these checks.

## Containers and the host

- **Nothing that the repository runs needs a host install:** builds, tests and tools run in Docker containers, and the
  scripts use only Bash, git, curl, the docker CLI, the standard library of the host's `python3`, and the tools of the
  base system, such as coreutils, findutils, util-linux, iproute2, grep, sed, awk, tar, gzip, openssl and getent.
- **No container mounts the home directory or a secret,** apart from the signing container of `scripts/build-apk.sh`,
  which mounts the signing key read-only, without network, and signs nothing but the variant's application id with the
  versionCode the script gave the build.

## Development stacks and production

- **A stack's settings come from its `.env` only:** the scripts read them in the strict format of
  `scripts/lib/stack.py`, and run docker compose with that `.env` and nothing else, so that a variable of the caller's
  shell never changes a stack. The one exception is `scripts/build-apk.sh` without a `.env`, which runs only in CI
  (`CI=true` or `GITHUB_ACTIONS=true`), never signs, and refuses production's directories and the home directory but
  GitHub's `RUNNER_TEMP`.
- **Every stack but production's is checked by `scripts/lib/stack.py` before docker compose runs it:** its `.env` in the
  strict format, and what docker compose resolves for it, every profile included, against what production owns (its
  project, images, ports and host paths) and against the allowlists of service and build settings and of compose
  commands. A script that starts, builds or changes such a stack goes through these checks.
- **Production is operated by hand only through `scripts/prod.sh compose`,** whose allowlist of compose commands
  (`scripts/lib/stack.py check-compose-command --production`) refuses builds, one-off containers and the commands that
  copy or push out of a stack: production changes only through `scripts/deploy.sh`. `scripts/deploy.sh` and
  `scripts/setup.sh`, which build and change production, run docker compose with production's `.env` only.
- **A setting that a change needs goes into the allowlist of `scripts/lib/stack.py` in the same pull request,** with the
  reason it is safe, and a test of `scripts/tests/` that shows what it allows.
- **A development stack writes only inside its own `DATA_DIR`,** and reads production's OCR models and signing key
  read-only, nothing else of production's. That `DATA_DIR` lies outside the system directories and the home directory,
  and neither is nor contains `/tmp`; every other host path the stack uses lies inside it.
- **The dev app keeps its own application id,** `fr.scanmylib.dev`, so that it installs next to the production app and a
  build of a branch never replaces it.
- **The production app trusts nothing on its signature:** no signature-level permission, no exported component protected
  by one, no `sharedUserId`. The dev app is signed with the same key, and could use any of them; revisit the shared key
  before adding one.
