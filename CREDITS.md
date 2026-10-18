# Credits

ScanMyLib reuses the work below. Each entry says what is reused, where it lives in this repository or where the
project installs it, where it comes from, and under which terms. License notices that must be kept are copied
verbatim.

## Libraries

### The base of the images

The api's image, the OCR sandbox's and the image of the gate's Python tools are built on the official
`python:3.12-slim-bookworm` image: CPython 3.12
(PSF-2.0, https://www.python.org) on Debian 12 "bookworm" (its packages under their own free-software licenses,
https://www.debian.org). The sandbox's image adds the Debian packages `gcc`, `libc6-dev`, `libgomp1`, `libgl1` and
`libglib2.0-0`, which the engine's wheels need, and uv 0.10.9 (MIT or Apache-2.0, https://github.com/astral-sh/uv),
which installs the engine's environments.

### The api's image

The api's Python packages, pinned with their hashes in `server/requirements.lock` and installed in its image.

| Package | Version | Role | License | Source |
|---|---|---|---|---|
| FastAPI | 0.143.0 | HTTP routes | MIT | https://github.com/fastapi/fastapi |
| Starlette | 1.7.0 | The ASGI toolkit under FastAPI | BSD-3-Clause | https://github.com/Kludex/starlette |
| Uvicorn | 0.54.0 | HTTP server | BSD-3-Clause | https://github.com/Kludex/uvicorn |
| Pydantic, pydantic-core | 2.14.1, 2.50.1 | Validation of request bodies | MIT | https://github.com/pydantic/pydantic |
| python-multipart | 0.0.32 | Uploads | Apache-2.0 | https://github.com/Kludex/python-multipart |
| Pillow | 12.3.0 | Images | MIT-CMU | https://github.com/python-pillow/Pillow |
| HTTPX, httpcore, h11 | 0.28.1, 1.0.9, 0.16.0 | The client of the OCR sandbox | BSD-3-Clause, BSD-3-Clause, MIT | https://github.com/encode/httpx |
| markdown-it-py, mdurl | 4.2.0, 0.1.2 | Markdown to HTML, for the previews | MIT | https://github.com/executablebooks/markdown-it-py |
| nh3 | 0.3.7 | Allowlist sanitizer of HTML | MIT | https://github.com/messense/nh3 |
| qrcode | 8.2 | QR codes of pairing | BSD | https://github.com/lincolnloop/python-qrcode |
| AnyIO | 4.15.1 | Async I/O under Starlette and HTTPX | MIT | https://github.com/agronholm/anyio |
| click | 8.5.0 | Uvicorn's command line | BSD-3-Clause | https://github.com/pallets/click |
| idna, certifi | 3.20, 2026.7.22 | Host names and certificates for HTTPX | BSD-3-Clause, MPL-2.0 | https://github.com/kjd/idna, https://github.com/certifi/python-certifi |
| annotated-types, annotated-doc, typing-extensions, typing-inspection | 0.8.0, 0.0.5, 4.16.0, 0.4.4 | Typing support of Pydantic and FastAPI | MIT, MIT, PSF-2.0, MIT | https://github.com/annotated-types/annotated-types |
| opentelemetry-api | 1.45.1 | A dependency of FastAPI | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python |

### The web UI

| Library | Version | Role | License | Where |
|---|---|---|---|---|
| KaTeX, with its fonts | 0.19.0 | Typesetting of LaTeX formulas | MIT | `server/scanmylib/web/static/vendor/katex/`, from the npm package `katex`, fetched and checked by `scripts/vendor-katex.sh`; https://katex.org |

KaTeX's notice, also in `server/scanmylib/web/static/vendor/katex/LICENSE`:

```
The MIT License (MIT)

Copyright (c) 2013-2020 Khan Academy and other contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### The app

The app's direct libraries, with their versions in `android/gradle/libs.versions.toml`; Gradle checks them and their
own dependencies against `android/gradle/verification-metadata.xml`.

| Library | Role | License | Source |
|---|---|---|---|
| Kotlin standard library, kotlinx.coroutines, kotlinx.serialization | Language, concurrency, JSON | Apache-2.0 | https://github.com/JetBrains/kotlin, https://github.com/Kotlin |
| AndroidX: Activity, CameraX, Compose (Material 3, UI), DataStore, ExifInterface, Lifecycle, Navigation, Room, WorkManager | Screens, camera, settings, photo metadata, lifecycles, navigation, database, upload queue | Apache-2.0 | https://developer.android.com/jetpack/androidx |
| Coil | Images in Compose | Apache-2.0 | https://github.com/coil-kt/coil |
| OkHttp | The client of the PC | Apache-2.0 | https://github.com/square/okhttp |
| Google Play services: ML Kit document scanner, code scanner | Google's document scanner, and the QR code reader of pairing | Google's terms: https://developers.google.com/ml-kit/terms | https://developers.google.com/ml-kit |

## The OCR engine

`ocr/setup/install.sh` installs the engine into the sandbox (`SANDBOX_DIR`) on the user's machine; none of it is in
this repository.

| Work | Version | Role | License | Source |
|---|---|---|---|---|
| PaddlePaddle (GPU build) | 3.2.1 | The framework of the layout and recognition models | Apache-2.0 | https://github.com/PaddlePaddle/Paddle |
| PaddleOCR, and PaddleX | 3.7.0 for PaddleOCR; PaddleX as PaddleOCR requires it, unpinned | The document-parsing pipeline | Apache-2.0 | https://github.com/PaddlePaddle/PaddleOCR |
| vLLM | 0.31.0 | Serves the recognition model | Apache-2.0 | https://github.com/vllm-project/vllm |
| PaddleOCR-VL-1.6 | Hugging Face commit pinned in `ocr/setup/install.sh` | The recognition model (0.9B) | Apache-2.0 | https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6 |
| PP-DocLayoutV3, PP-LCNet_x1_0_doc_ori, UVDoc | Hugging Face commits pinned in `ocr/setup/install.sh` | Layout analysis, page orientation, unwarping of curved pages | Apache-2.0 | https://huggingface.co/PaddlePaddle |

## Development tools

Tools that build and test the project, run in containers and never shipped.

| Tool | Role | License | Source |
|---|---|---|---|
| pytest | The api's tests | MIT | https://github.com/pytest-dev/pytest |
| Node.js (`node:22-bookworm-slim`) | The web UI's unit tests; the image of Biome (`scripts/lint/Dockerfile.web`), and the regeneration of its lockfile | MIT | https://nodejs.org |
| Eclipse Temurin JDK 21 (`eclipse-temurin:21-jdk`) | The app's build | GPL-2.0 with the Classpath Exception | https://adoptium.net |
| Gradle, Android Gradle Plugin | The app's build | Apache-2.0 | https://gradle.org, https://developer.android.com/build |
| Android SDK | The app's build and signing tools | Android Software Development Kit License | https://developer.android.com/studio |
| JUnit 4, kotlinx-coroutines-test, OkHttp MockWebServer | The app's unit tests | EPL-1.0, Apache-2.0, Apache-2.0 | https://junit.org/junit4 |
| uv 0.13.0 | Compiles the api's locks (`server/README.md`) and the lock of the gate's Python tools (`README.md` > Development) | MIT or Apache-2.0 | https://github.com/astral-sh/uv |
| Ruff | Formats and lints the Python; installed from `scripts/lint/requirements.lock` | MIT | https://github.com/astral-sh/ruff |
| mypy, and librt, ast-serialize, pathspec, mypy-extensions, typing-extensions | Checks the types of the Python; installed from `scripts/lint/requirements.lock` | MIT; pathspec MPL-2.0; typing-extensions PSF-2.0 | https://github.com/python/mypy |
| zizmor | Audits the GitHub workflows; installed from `scripts/lint/requirements.lock` | MIT | https://github.com/zizmorcore/zizmor |
| ShellCheck | Lints the shell scripts; its author's image `koalaman/shellcheck`, pinned by digest in `scripts/check.sh` | GPL-3.0 (a tool run in a container, never shipped or linked) | https://github.com/koalaman/shellcheck |
| shfmt | Formats the shell scripts; its author's image `mvdan/shfmt`, pinned by digest in `scripts/check.sh` | BSD-3-Clause | https://github.com/mvdan/sh |
| ktlint, and the libraries it runs on: logback, JNA, SLF4J, colormath, Clikt, Mordant, kotlin-logging, ec4j, sarif4k, Poko, the Kotlin compiler and standard library, kotlinx.serialization, kotlinx.coroutines, JetBrains annotations | Formats and lints the app's Kotlin; from Maven Central, through the version catalog (`android/gradle/libs.versions.toml`) | MIT; logback EPL-1.0 or LGPL-2.1; JNA LGPL-2.1-or-later or Apache-2.0; SLF4J and colormath MIT; the others Apache-2.0 | https://github.com/pinterest/ktlint |
| Biome | Formats and lints the web UI; installed from `server/scanmylib/web/package-lock.json` | MIT or Apache-2.0 | https://github.com/biomejs/biome |
