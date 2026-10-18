---
paths:
  - "server/pyproject.toml"
  - "server/requirements*.lock"
  - "**/Dockerfile"
  - "compose.yaml"
  - ".env.example"
  - "ocr/setup/**"
  - "android/*.gradle.kts"
  - "android/app/*.gradle.kts"
  - "android/gradle/**"
  - "android/gradle.properties"
  - "scripts/build-apk.sh"
  - "scripts/vendor-katex.sh"
  - "scripts/check.sh"
  - "scripts/lib/parallel_tests.py"
  - "scripts/lint/**"
  - "ruff.toml"
  - "mypy.ini"
  - ".editorconfig"
  - "android/.editorconfig"
  - ".shellcheckrc"
  - "server/scanmylib/web/biome.json"
  - "server/scanmylib/web/package*.json"
  - ".github/workflows/**"
  - ".claude/settings.json"
  - ".claude/agents/**"
  - ".claude/skills/**"
---

# Configuration

## Modules

- **A module** is a unit with its own build, or, within a unit, one directory of a layer. Until a unit is restructured
  into layers, its modules are its files and packages that hold one responsibility each, grouped in the rows of
  `docs/foundations.md` > Layers and modules.
- **The repository holds five units:** the api (`server/`: `pyproject.toml`, its locks and its `Dockerfile`), the web UI
  that the api serves (`server/scanmylib/web/`, with its own tests and the `package.json` of its tools), the app
  (`android/`: its Gradle build and version catalog), the OCR sandbox (`ocr/`: its `Dockerfile` and `ocr/setup/`, which
  installs its engines), and the scripts (`scripts/`: Bash and the host's Python standard library, and `scripts/lint/`,
  the images of the gate's tools). `compose.yaml` assembles the services of a stack from the first and the fourth.
- **Each unit has its tests, and its build where it has one:** the build file named above, and the tests at the level
  that `tests.md` > Levels gives it. A new unit comes with both, and with its job in `.github/workflows/ci.yml` through
  `scripts/check.sh`.
- **A tag marks a special treatment, and its absence is the default:** no module carries a tag that only says it is
  ordinary, so a new module needs none.
- **The documents list every module.** A change that adds, renames or removes a module, or changes its layer or its
  responsibility, updates its row in `docs/foundations.md` > Layers and modules in the same change.

## Dependencies

- **A new dependency comes from a known, maintained publisher, under a license compatible with the project's,** the MIT
  License. A tool that runs in a container and is never shipped, such as a linter, may have any open-source license.
- **Nothing new is downloaded without the user's approval:** a dependency, a model, an image or a toolchain. Ask first,
  listing exactly what would be installed: the packages, their sources, where they go and their sizes.
- **Never weaken what the lockfile or the registry settings guarantee,** nor any other pin of a download. What is
  checked against a hash stays so:
  - the api's Python packages, by `server/requirements.lock` and `server/requirements-test.lock`, installed with
    `pip install --require-hashes --no-deps`;
  - the app's libraries and Gradle plugins, by `android/gradle/verification-metadata.xml`, with their versions in
    `android/gradle/libs.versions.toml`;
  - the Gradle distribution, by the `distributionSha256Sum` of `android/gradle/wrapper/gradle-wrapper.properties`;
  - the signing tools, by the SHA-256 sums of `scripts/build-apk.sh`;
  - KaTeX, by its SHA-512 in `scripts/vendor-katex.sh`;
  - the Python tools of the gate, by `scripts/lint/requirements.lock`, installed with
    `pip install --require-hashes --no-deps`, and Biome, by `server/scanmylib/web/package-lock.json`, installed with
    `npm ci --ignore-scripts`;
  - ShellCheck and shfmt, by the image digests of `scripts/check.sh`.

  The rest is pinned by version, commit or tag, or checked as it downloads, and never loosened further: the Android SDK
  packages by version, which the Android CLI checks, and its command-line tools, the latest, against the SHA-1 Google
  publishes; the Gradle wrapper's jar against the SHA-256 Gradle publishes; the OCR sandbox's engines by version (their
  own dependencies as they resolve, and `safetensors` as it resolves), its models by Hugging Face commit
  (`ocr/setup/install.sh`), the uv of its image by version, and the base images by tag; the Debian packages of the OCR
  image are the release's current ones. No setting lets an install bypass or override a pin, such as another registry or
  index, or `--no-verify`.
- **A lock is regenerated, never edited by hand,** so that every hash comes from the file it pins: the api's locks with
  the `uv pip compile` command of `server/README.md`, the tools' lock with the one of `README.md` > Development, the web
  UI's lockfile with `npm install --package-lock-only --ignore-scripts`, the app's verification metadata with
  `scripts/build-apk.sh --write-verification-metadata`, as the header of `scripts/build-apk.sh` shows.

## Continuous integration

- **Actions are pinned to full commit SHAs,** each with its version label beside it, because a tag can move to other
  code.
- **Permissions stay read-only.** `.github/workflows/release.yml` is the one exception: it publishes a release, with
  `contents: write` and the run's own token, and runs nothing but `scripts/release.py` and the runner's `git` and `gh`.
- **Event data reaches a `run:` script only through `env:`,** never through `${{ }}` inside the script, where it would
  be spliced into shell code.
- **No `pull_request_target` workflow checks out untrusted code, and no secret reaches a run from a fork,** since either
  would hand the repository's credentials to code from outside.
- **CI uses no secret and never touches a stack:** it builds and tests in throwaway containers, and the Android build
  runs without a `.env`, unsigned, inside the runner's temporary directory.

## Checks

- **A check that enforces a rule is never narrowed to let a change pass:** in `scripts/check.sh`, Android lint, a guard
  of `scripts/lib/stack.py` or any other tool of the gate, no file excluded, no rule turned off or lowered, no threshold
  loosened, and no step dropped from the gate or from its CI run. The tests follow `tests.md`, where a loosened
  expectation states its reason. A change to the rule itself changes its rules file and its check together, and says
  why.

## Claude Code automation

- **No hook, skill or agent runs text taken from a pull request or a reviewed file** as a command, and no setting widens
  permissions.
