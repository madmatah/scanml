# ScanMyLib

Scan books and documents with an Android phone, OCR them on the PC's GPU inside a network-less sandbox, and organize
the results on disk as Markdown and illustrations for AI agents. Start with `docs/foundations.md`, then
`docs/ARCHITECTURE.md`.

## Language

English is the reference language of this repository. Everything committed is written in English: code, identifiers,
comments, documentation, commit messages, file names and UI text. Use American spelling (`color`, `behavior`,
`organize`).

The only exception is the French translation of user-facing UI text. English strings are the reference; their French
translations live only in the translation catalogs: `android/app/src/main/res/values-fr/` for the Android app and
`server/scanmylib/web/static/js/locales/fr.js` for the web UI (its unit tests fail on any untranslated string or on
French outside the catalog). Never write French anywhere else in the repository.

## What belongs in the repository

The repository holds the current state of the project and nothing else. Never commit project-management material:

- status or tracking files;
- decision records;
- roadmaps;
- handoffs;
- meeting or research notes;
- `TODO` comments.

That material lives in `.pm/`, a separate, private Git repository nested at the root of the primary checkout and
ignored by this one (from a worktree: `~/Dev/scanmylib/.pm/`). `.pm/README.md` describes its layout. At the
start of a session, if `.pm/` exists, read `.pm/roadmap.md` and the latest note in `.pm/handoffs/`.

When a decision changes the project:

- update `docs/foundations.md` to describe the new state;
- log the decision in `.pm/decisions.md`, then commit it in the `.pm/` repository.

## No real document names

No real document or book may be named anywhere in the repository: not in code, tests, fixtures, examples,
documentation or commit messages. This covers titles, authors, file and folder names, and excerpts, and above all
anything seen in the user's library. Use invented placeholders (`Example Book`, `Jane Doe`). This keeps contributors
from leaking the user's private data.

## No personal information

The repository is public. Nothing personal about the maintainer, a contributor or a user may be committed or written in
a pull request, apart from the author name and email of the commits and the copyright holder in `LICENSE` (the
maintainer's GitHub handle). This covers usernames, the paths of an installation (`/home/<name>`, `/data/<name>`), IP
and MAC addresses, hostnames, other projects found on a machine, devices tied to someone (naming the GPU a measurement
was made on is fine), and anything that locates a person, such as a time zone or a city. Write placeholders instead:
`/home/user`, `/data/USER/scanmylib`, `~/Dev/scanmylib`, `192.168.1.10`, `example.invalid`, a fixed offset (`+02:00`) or
`UTC` for a time zone. Values read on the machine (a path, an address, a time zone) never become defaults or examples.
Address any reader, never the maintainer's own setup.

## Security rules

The user's account holds many secrets, and the OCR stack (PaddlePaddle, PaddleOCR, vLLM, model code) is untrusted.

- Install nothing on the host. Builds, tests and tools run in Docker containers; the host's `python3` (standard
  library only) and `curl` are fine. Ask the user before downloading or installing anything new: models, images,
  toolchains or dependencies.
- The `ocr` service keeps `network_mode: none`, a read-only root filesystem, no capabilities, `no-new-privileges`, a
  non-root user, and no host mount besides the read-only `SANDBOX_DIR`, the socket directory and its cache directory.
  Never weaken this; `scripts/verify-sandbox.sh` must pass.
- Untrusted components are downloaded only by the `ocr-setup` container, pinned by version or commit. No Paddle code
  runs with network access. It writes the sandbox through `SANDBOX_SETUP_DIR`, which only production's `.env` sets;
  every other container mounts `SANDBOX_DIR` read-only.
- Everything the sandbox returns is untrusted data: sizes, names, HTML, Markdown. See `docs/SECURITY.md`.
- Never mount `$HOME` or any secret into a container.

## Engineering principles

- The pipeline is engine-agnostic: the api only knows the sandbox protocol (`docs/OCR_SANDBOX.md`). Never add
  post-processing that compensates for a specific model's mistakes. Keep OCR output as produced, raw LaTeX included,
  and fix display generically.
- Nothing is hard-deleted from the library: deletions go to `LIBRARY_DIR/.trash/`.
- Production is in real use. While developing, never touch the running containers, the library (`LIBRARY_DIR`, the
  user's private documents: do not read their content) or the state directory. Test on the development stack (see
  "Development workflow"), or with your own containers, ports and data directories, and remove these afterwards.

## Development workflow

- **Branches and pull requests.** `main` is what production runs. Every change is made on its own branch and reaches
  `main` through a pull request on GitHub (`origin`); nothing is committed to `main` directly. Pull requests are
  merged with "Rebase and merge" only, so `main` keeps their commits as they are.
- **Commits.** Each commit is atomic: one logical change, with its tests and documentation, and the project builds and
  passes its tests at every commit. Messages follow Conventional Commits: `type(scope): summary`, in the imperative
  and lowercase, with `feat`, `fix`, `refactor`, `test`, `docs`, `build`, `ci` or `chore`, and a scope when the
  change is confined to one part (`ocr`, `server`, `web`, `android`, `scripts`). The body says why. Before a pull
  request is merged, its history is cleaned up (fixups folded into the commits they fix).
- **One worktree per branch**, under `~/Dev/scanmylib-worktrees/<branch>`, created from the primary checkout
  with `git worktree add -b <branch> ../scanmylib-worktrees/<branch> main` and removed after the merge
  (`git worktree remove`). The primary checkout, `~/Dev/scanmylib`, stays on `main`: it is production's
  checkout (its `.env` is production's), never a place to develop. The scripts recognize production's checkout as the
  directory production's containers were started from (their `com.docker.compose.project.working_dir` label), or
  `~/Dev/scanmylib` when no production container exists; another clone holding a copy of production's `.env` is not
  production.
- **What the guards are for.** The checks of the scripts (`scripts/lib/stack.py`) protect production from
  misconfiguration, from mistakes in a branch (a wrong `.env`, a `compose.yaml` change, a command run in the wrong
  checkout) and from compromised build dependencies (code running in the containers a branch builds). They do not
  stop a deliberately malicious branch: its scripts run as the user. Review what a branch changes in `scripts/`,
  `compose.yaml` and the Dockerfiles before running it.
- **Development stack.** In a worktree, run `scripts/dev-env.sh` first: it writes the worktree's `.env` for the single
  development slot: project and images `scanmylib-dev`, port 8770, its own data in production's `DATA_DIR` followed by `-dev`
  (state, socket, caches, APK, logs, a test `LIBRARY_DIR`, never the user's library, and its own Android toolchain),
  and production's OCR models, mounted read-only. It refuses to run in production's checkout or to overwrite a `.env`
  that is not a development one. Then `scripts/dev.sh up` builds and starts `api` with the fake OCR (`ocr-fake`,
  canned results), `scripts/dev.sh status`, `logs`, `down`. `scripts/dev.sh up --real-ocr` starts the real sandbox
  instead: a second engine next to production's, ~4.4 GB of VRAM while it works, so only when the change needs it.
  One development stack runs at a time, next to production; `scripts/dev.sh up` in another worktree takes the slot
  over. `scripts/e2e_test.py` and `scripts/verify-sandbox.sh` target the stack of the checkout they run from;
  `scripts/e2e_test.py` refuses production unless given `--production`.
- **Never plain `docker compose`.** In a worktree, `scripts/dev.sh` first checks what docker compose resolves for the
  stack and refuses anything production owns (project, images, ports, host paths), any host path outside the stack's
  own `DATA_DIR` (except production's OCR models and signing key, read-only), `/tmp`, system directories and anything
  in the home directory, and any service setting outside the allowlist of `scripts/lib/stack.py` (no `privileged`,
  `cap_add`, `volumes_from`, `env_file`, host namespaces, other networks, devices but the GPU...); use
  `scripts/dev.sh build [api|ocr]` and `scripts/dev.sh compose COMMAND...` (e.g. `compose exec api sh`) for anything
  else, which refuses the commands and options that could leave the stack (`cp`, `commit`, `push`, `run -v`/`-p`,
  `exec --privileged`, `config -o`...) and `up` without service names (it would start both OCR services). A setting a
  change needs goes into that allowlist in the same pull request. In production's checkout, `scripts/prod.sh compose
  COMMAND...` runs docker compose with production's `.env` only (plain `docker compose` would let the shell's
  environment override it), for operations, never builds (`up` only on a clean `main`). A
  `.env` keeps to a strict format that every script checks
  (`KEY=VALUE`, comments, blank lines; see `.env.example`); never copy `.env.example` or production's `.env` into a
  worktree.
- **Dev app and production app.** In a worktree, `scripts/build-apk.sh` builds the development app (`APP_VARIANT=dev`,
  never the release one): application id `fr.scanmylib.dev`, named "ScanMyLib (dev)", orange icon. It is built with
  the development slot's own Android SDK and Gradle caches (`<DATA_DIR>-dev/android`, downloaded and verified
  by the first build) and signed with production's key, which only the signing container mounts, read-only, after
  checking its tools against pinned checksums; that container signs nothing but the variant's application id
  (`fr.scanmylib.dev`, or `fr.scanmylib` for the release) with the versionCode of `VERSION`, read from the APK itself,
  so a change that drops the `.dev` suffix never gets a production app signed. It installs next to the production
  app (`fr.scanmylib`, "ScanMyLib")
  and is published as `<DATA_DIR>-dev/app/scanmylib.apk`, offered by the development stack's Pairing tab
  (`http://<LAN IP>:8770`). The production APK is only built by `scripts/deploy.sh --apk`.
- **One version.** `VERSION` (MAJOR.MINOR.PATCH) is the version of the api (`/api/health`) and of the app: its
  `versionName` is `VERSION` and its `versionCode` is major × 10000 + minor × 100 + patch (minor and patch stay below
  100), so that every release installs over the previous one. Bump it in the pull request of any change to deploy;
  each deployed version is tagged `vX.Y.Z`.
- **Continuous integration.** `.github/workflows/ci.yml` runs the server, web UI, OCR sandbox (stdlib, no models),
  scripts (`scripts/tests/`) and Android (`scripts/build-apk.sh test lint`, never signed; without a `.env` it only
  runs with `CI=true`, never in production's directories nor in the home directory, except GitHub Actions'
  `RUNNER_TEMP`) checks on every pull request and on `main`. A pull
  request is merged only when CI is green. CI uses no secrets and never touches production.
- **Deployment.** Production changes only through `scripts/deploy.sh`, run in production's checkout on a clean `main`
  equal to main on `origin` (`--dry-run` first, `--apk` to publish the app): images built from the commit (`git
  archive HEAD`), unit tests of the new code, backup of the state, restart of `api` and `ocr`, health and isolation
  checks (then the new images are tagged `:deployed`), the app with `--apk`, then the tag `vVERSION`, pushed; on
  failure it says what state production is in and how to roll back. Never deploy from a worktree or with `docker
  compose` by hand. The release app is built only in production's checkout, on `main` as on `origin`. `scripts/setup.sh`
  only installs a new production and refuses once it exists. A rehearsal on a throwaway stack is described in
  `scripts/deploy.sh`'s header.

## Layout and commands

| Area | Path | Test or run |
|---|---|---|
| OCR sandbox | `ocr/` | `docker run --rm --init --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000 -v "$PWD/ocr:/app:ro" -v "$SANDBOX_DIR:/opt/sandbox:ro" scanmylib-dev-ocr:latest /opt/sandbox/venv-paddle/bin/python -m unittest discover -s /app/tests` (the image: `scripts/dev.sh build ocr` in a worktree); isolation of the running service: `scripts/verify-sandbox.sh` |
| api and web UI | `server/` | `cd server && docker build --target test -t scanmylib-dev-api:test . && docker run --rm --network none --read-only --tmpfs /tmp scanmylib-dev-api:test` |
| Web UI unit tests | `server/scanmylib/web/tests/` | `docker run --rm --network none --read-only --user 1000:1000 -v "$PWD/server/scanmylib/web:/web:ro" node:22-bookworm-slim node --test '/web/tests/*.test.js'` |
| Android app | `android/` | `scripts/build-apk.sh` (tests, build of the `APP_VARIANT` app, lint, offline signing) |
| Development stack | `compose.yaml`, `.env` | `scripts/dev-env.sh` once per worktree, then `scripts/dev.sh up`, `status`, `logs`, `down`, `build`, `compose ...` |
| Scripts | `scripts/`, `scripts/tests/` | `python3 -m unittest discover -s scripts/tests` (host `python3`, stdlib only; a docker stand-in, nothing is built or started) |
| Deployment | `scripts/deploy.sh` | `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh [--apk]`, in production's checkout on `main`; first install: `scripts/setup.sh` |
| Production operations | `scripts/prod.sh` | `scripts/prod.sh compose ps`, `logs -f api ocr`, `restart api`... in production's checkout |
| End to end | `scripts/e2e_test.py` | `scripts/e2e_test.py IMAGE...` against the stack of the checkout's `.env` (production refused without `--production`) |

## Safety

- Never run `git clean` with `-ff` at the repository root: a double `-f` deletes nested repositories, including
  `.pm/`.
- Never run `docker system prune`, `docker image prune`, `docker volume prune` or `docker builder prune`: the host runs
  other projects. Remove only the containers and images you created.
