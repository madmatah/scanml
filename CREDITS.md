# Credits

ScanMyLib reuses the work below. Each entry says what is reused, where it lives in this repository or where the
project installs it, where it comes from, and under which terms; guidance that borrows here and there is credited as a
whole. License notices that must be kept are copied verbatim.

## Libraries

### The base of the images

The api's image, the OCR sandbox's and the image of the gate's Python tools are built on the official
`python:3.12-slim-trixie` image: CPython 3.12 (PSF-2.0, https://www.python.org) on Debian 13 "trixie" (its packages
under their own free-software licenses, https://www.debian.org). The api's image adds the Debian package `tzdata-legacy`
(public domain), which keeps the former names of the time zones. The sandbox's image adds the Debian packages `gcc`,
`libc6-dev` and `libgomp1`, which the engine's wheels need, and its setup image, which `ocr-setup` runs, adds uv 0.13.4
(MIT or Apache-2.0, https://github.com/astral-sh/uv), which installs the engine's environments.

### The api's image

The api's Python packages, pinned with their hashes in `server/requirements.lock` and installed in its image.

| Package | Version | Role | License | Source |
|---|---|---|---|---|
| FastAPI | 0.143.0 | HTTP routes | MIT | https://github.com/fastapi/fastapi |
| Starlette | 1.7.0 | The ASGI toolkit under FastAPI | BSD-3-Clause | https://github.com/Kludex/starlette |
| Uvicorn | 0.54.0 | HTTP server | BSD-3-Clause | https://github.com/Kludex/uvicorn |
| Pydantic, pydantic-core | 2.14.1, 2.50.1 | Validation of request bodies | MIT | https://github.com/pydantic/pydantic |
| python-multipart | 0.0.32 | Uploads | Apache-2.0 | https://github.com/Kludex/python-multipart |
| Pillow | 13.0.0 | Images | MIT-CMU | https://github.com/python-pillow/Pillow |
| HTTPX, httpcore, h11 | 0.28.1, 1.0.9, 0.16.0 | The client of the OCR sandbox | BSD-3-Clause, BSD-3-Clause, MIT | https://github.com/encode/httpx |
| markdown-it-py, mdurl | 4.2.0, 0.1.2 | Markdown to HTML, for the previews | MIT | https://github.com/executablebooks/markdown-it-py |
| nh3 | 0.3.7 | Allowlist sanitizer of HTML | MIT | https://github.com/messense/nh3 |
| qrcode | 8.2 | QR codes of pairing | BSD | https://github.com/lincolnloop/python-qrcode |
| AnyIO | 4.15.1 | Async I/O under Starlette and HTTPX | MIT | https://github.com/agronholm/anyio |
| click | 8.5.0 | Uvicorn's command line | BSD-3-Clause | https://github.com/pallets/click |
| idna, certifi | 3.20, 2026.10.18 | Host names and certificates for HTTPX | BSD-3-Clause, MPL-2.0 | https://github.com/kjd/idna, https://github.com/certifi/python-certifi |
| annotated-types, annotated-doc, typing-extensions, typing-inspection | 0.8.0, 0.0.5, 4.16.0, 0.4.4 | Typing support of Pydantic and FastAPI | MIT, MIT, PSF-2.0, MIT | https://github.com/annotated-types/annotated-types |
| opentelemetry-api | 1.45.1 | A dependency of FastAPI | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python |

### The web UI

| Library | Version | Role | License | Where |
|---|---|---|---|---|
| React, React DOM, and their scheduler and `use-sync-external-store` | 19.3.1, 19.3.1, 0.28.0, 1.7.0 | The screens, as function components | MIT | bundled into the web UI's script by esbuild, from `server/scanmylib/web/pnpm-lock.yaml`; https://react.dev |
| React Router | 8.5.1 | The navigation, in the URL's fragment | MIT | bundled into the web UI's script by esbuild, from `server/scanmylib/web/pnpm-lock.yaml`; https://reactrouter.com |
| i18next | 26.7.1 | The translations | MIT | bundled into the web UI's script by esbuild, from `server/scanmylib/web/pnpm-lock.yaml`; https://www.i18next.com |
| react-i18next, and `html-parse-stringify`, which reads the elements of a translated sentence | 17.1.12, 4.0.1 | The translations of the React components | MIT | bundled into the web UI's script by esbuild, from `server/scanmylib/web/pnpm-lock.yaml`; https://react.i18next.com |
| i18next-browser-languagedetector | 8.3.0 | The language the browser prefers | MIT | bundled into the web UI's script by esbuild, from `server/scanmylib/web/pnpm-lock.yaml`; https://github.com/i18next/i18next-browser-languageDetector |
| KaTeX, with its fonts | 0.19.0 | Typesetting of LaTeX formulas | MIT | `server/scanmylib/web/static/vendor/katex/`, from the npm package `katex`, fetched and checked by `scripts/vendor-katex.sh`; https://katex.org |

The notices of the packages bundled into the web UI's script:

React, React DOM, their scheduler and `use-sync-external-store`:

```
MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

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

React Router:

```
MIT License

Copyright (c) React Training LLC 2015-2019
Copyright (c) Remix Software Inc. 2020-2021
Copyright (c) Shopify Inc. 2022-2023

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

i18next:

```
The MIT License (MIT)

Copyright (c) 2011-present i18next

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

react-i18next and i18next-browser-languagedetector:

```
The MIT License (MIT)

Copyright (c) 2015-present i18next

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

`html-parse-stringify`:

```
MIT License

Copyright (c) 2025 Henrik Joreteg <henrik@joreteg.com>
Copyright (c) 2026-present i18next (https://github.com/i18next)

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

The app's icons, the vector drawables of `android/app/src/main/res/drawable/` apart from the launcher's layers
(`ic_launcher_*.xml`) and the brand mark (`brand_mark.xml`), are Google's Material Symbols (Outlined, 24 px) and, for a
few older ones, Material Icons, from https://github.com/google/material-design-icons (the symbols from
`symbols/web/<name>/materialsymbolsoutlined/<name>_24px.svg`), under the Apache License 2.0
(https://www.apache.org/licenses/LICENSE-2.0). Each drawable is the icon converted from SVG to an Android vector
drawable, and names its icon and its license in a comment. The launcher's layers and the brand mark are the project's
own drawing.

## The OCR engine

`ocr/setup/install.sh` installs the engine into the sandbox (`SANDBOX_DIR`) on the user's machine; none of it is in
this repository.

| Work | Version | Role | License | Source |
|---|---|---|---|---|
| PaddlePaddle (GPU build) | 3.2.1 | The framework of the layout and recognition models | Apache-2.0 | https://github.com/PaddlePaddle/Paddle |
| PaddleOCR, and PaddleX | 3.7.0 for PaddleOCR; PaddleX as PaddleOCR requires it, unpinned | The document-parsing pipeline | Apache-2.0 | https://github.com/PaddlePaddle/PaddleOCR |
| OpenCV, its headless build with the contributed modules (`opencv-contrib-python-headless`) | 4.10.0.84 | The pipeline's image processing, installed under the name `opencv-contrib-python` that PaddleX requires | Apache-2.0 | https://github.com/opencv/opencv-python |
| vLLM | 0.31.0 | Serves the recognition model | Apache-2.0 | https://github.com/vllm-project/vllm |
| PaddleOCR-VL-1.6 | Hugging Face commit pinned in `ocr/setup/install.sh` | The recognition model (0.9B) | Apache-2.0 | https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6 |
| PP-DocLayoutV3, PP-LCNet_x1_0_doc_ori, UVDoc | Hugging Face commits pinned in `ocr/setup/install.sh` | Layout analysis, page orientation, unwarping of curved pages | Apache-2.0 | https://huggingface.co/PaddlePaddle |

## Development tools

Tools that build and test the project, run in containers and never shipped.

| Tool | Role | License | Source |
|---|---|---|---|
| pytest | The api's tests | MIT | https://github.com/pytest-dev/pytest |
| Node.js (`node:26-trixie-slim`, pinned by digest) | The web UI's tools and unit tests, in the image of its tools (`scripts/lint/Dockerfile.web`), its build, in the stages of the api's image that build it (`server/Dockerfile`), and the regeneration of its lockfile | MIT | https://nodejs.org |
| pnpm 12.17.0 | Installs the web UI's dependencies and tools, and regenerates its lockfile; its standalone build for Linux, checked against its SHA-256 in `scripts/lint/Dockerfile.web` and `server/Dockerfile` | MIT | https://pnpm.io |
| Eclipse Temurin JDK 21 (`eclipse-temurin:21-jdk`) | The app's build | GPL-2.0 with the Classpath Exception | https://adoptium.net |
| Gradle, Android Gradle Plugin | The app's build | Apache-2.0 | https://gradle.org, https://developer.android.com/build |
| Android SDK | The app's build and signing tools | Android Software Development Kit License | https://developer.android.com/studio |
| JUnit 4, kotlinx-coroutines-test, OkHttp MockWebServer | The app's unit tests | EPL-1.0, Apache-2.0, Apache-2.0 | https://junit.org/junit4 |
| Robolectric and its image of Android 16, Roborazzi, Compose UI test | The app's screenshot tests, and its tests that need Android's framework | MIT; Apache-2.0 for the image of Android, Roborazzi and Compose UI test | https://robolectric.org, https://github.com/takahirom/roborazzi, https://developer.android.com/jetpack/androidx/releases/compose-ui |
| uv 0.13.0 | Compiles the api's locks (`server/README.md`) and the lock of the gate's Python tools (`README.md` > Development) | MIT or Apache-2.0 | https://github.com/astral-sh/uv |
| Ruff | Formats and lints the Python; installed from `scripts/lint/requirements.lock` | MIT | https://github.com/astral-sh/ruff |
| mypy, and librt, ast-serialize, pathspec, mypy-extensions, typing-extensions | Checks the types of the Python; installed from `scripts/lint/requirements.lock` | MIT; pathspec MPL-2.0; typing-extensions PSF-2.0 | https://github.com/python/mypy |
| zizmor | Audits the GitHub workflows; installed from `scripts/lint/requirements.lock` | MIT | https://github.com/zizmorcore/zizmor |
| OSV-Scanner | Reports the known vulnerabilities of what Dependabot cannot read, in the continuous integration; Google's image `ghcr.io/google/osv-scanner`, pinned by digest in `.github/workflows/vulnerability-scan.yml` | Apache-2.0 | https://github.com/google/osv-scanner |
| ShellCheck | Lints the shell scripts; its author's image `koalaman/shellcheck`, pinned by digest in `scripts/check.sh` | GPL-3.0 (a tool run in a container, never shipped or linked) | https://github.com/koalaman/shellcheck |
| shfmt | Formats the shell scripts; its author's image `mvdan/shfmt`, pinned by digest in `scripts/check.sh` | BSD-3-Clause | https://github.com/mvdan/sh |
| ktlint, and the libraries it runs on: logback, JNA, SLF4J, colormath, Clikt, Mordant, kotlin-logging, ec4j, sarif4k, Poko, the Kotlin compiler and standard library, kotlinx.serialization, kotlinx.coroutines, JetBrains annotations | Formats and lints the app's Kotlin; from Maven Central, through the version catalog (`android/gradle/libs.versions.toml`) | MIT; logback EPL-1.0 or LGPL-2.1; JNA LGPL-2.1-or-later or Apache-2.0; SLF4J and colormath MIT; the others Apache-2.0 | https://github.com/pinterest/ktlint |
| Biome | Formats and lints the web UI; installed from `server/scanmylib/web/pnpm-lock.yaml` | MIT or Apache-2.0 | https://github.com/biomejs/biome |
| i18next-cli, and `@swc/core`, its parser, with its native addon for Linux | Checks the web UI's translation catalogs against its code, and writes them in `scripts/check.sh --fix`; installed from `server/scanmylib/web/pnpm-lock.yaml` | MIT; `@swc/core` Apache-2.0 and its addon Apache-2.0 AND MIT | https://github.com/i18next/i18next-cli, https://github.com/swc-project/swc |
| TypeScript, and the types of Node.js, React and React DOM (`@types/node`, `@types/react`, `@types/react-dom`, from DefinitelyTyped) | Checks the types of the web UI's TypeScript and of its tests; installed from `server/scanmylib/web/pnpm-lock.yaml` | Apache-2.0; the types MIT | https://github.com/microsoft/TypeScript, https://github.com/DefinitelyTyped/DefinitelyTyped |
| esbuild, with its native binary for Linux (`@esbuild/linux-x64`) | Builds the web UI (`server/scanmylib/web/build.ts`): bundles its TypeScript, its packages and its stylesheet into files whose names carry a hash of their content; installed from `server/scanmylib/web/pnpm-lock.yaml` | MIT | https://github.com/evanw/esbuild |

## Agent guidance

- **mattpocock/skills:** parts of the agent guidance in `.claude/` draw on https://github.com/mattpocock/skills, by Matt
  Pocock, under the MIT License:

  ```
  MIT License

  Copyright (c) 2026 Matt Pocock

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
