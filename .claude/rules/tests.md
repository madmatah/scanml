---
paths:
  - "server/tests/**"
  - "server/scanmylib/devtools/**"
  - "server/scanmylib/web/tests/**"
  - "ocr/tests/**"
  - "ocr/bench/**"
  - "android/app/src/test/**"
  - "scripts/tests/**"
  - "scripts/e2e_test.py"
  - "scripts/verify-sandbox.sh"
---

# Tests

Tests are the specification of the business rules: to learn how a part of the system behaves, read its tests.

## Writing a test

- **A test name is a sentence that states one rule**, in domain vocabulary: `test_a_rescanned_page_replaces_the_old_one`
  in Python, `` `keeps the token out of its text form` `` in Kotlin,
  `'an unnumbered plate stays after the page scanned before it'` in JavaScript. A test group names the concept under
  test.
- **One rule per test.** The body reads top to bottom, setup, action, expectation, with no branching. Inputs are named
  values, not unexplained literals.
- **A bug fix starts with a test** that reproduces the bug.
- **Floating point:** compare with a tolerance, unless bit-exactness is the rule under test.
- **No test depends on timing, the wall clock or the order of the tests,** and randomness is seeded, or reports its
  seed, so that a failure replays. A coroutine runs on a test dispatcher that the test advances, and a clock is a port
  that the test sets.
- **A deleted test, or a loosened expectation, states its reason** in the change.
- **The fixtures name no real document** and hold no personal data: invented titles, authors and pages, as
  `repository.md` > No real document names says.

## Levels

- **Unit tests of the api:** `server/tests/`, with pytest, in the api's test image, without network and on a read-only
  filesystem. The HTTP API runs through FastAPI's test client, against the fake OCR sandbox on a real Unix socket.
- **Unit tests of the web UI:** `server/scanmylib/web/tests/`, with `node --test`, on the modules of the UI that hold no
  DOM, and on its translation catalog.
- **Unit tests of the OCR sandbox:** `ocr/tests/`, with `unittest`, in the sandbox's image, without network or models;
  the tests that need an engine's environment skip without it.
- **Unit tests of the app:** `android/app/src/test/`, with JUnit on the JVM: view models, the upload queue and the
  client of the PC, against fakes and a mock web server.
- **Tests of the scripts:** `scripts/tests/`, with `unittest` and the host's `python3`, against throwaway repositories
  and a docker stand-in (`scripts/tests/docker_shim.py`) that never reaches the Docker daemon.
- **End to end:** `scripts/e2e_test.py`, which acts like the phone against a running stack, the development stack by
  default.
- **Isolation of the sandbox:** `scripts/verify-sandbox.sh`, against the running `ocr` service.
- **Benchmarks:** `ocr/bench/`, on the real engine and the GPU, outside the gate.
- **A test that needs a real adapter** outside the test's own process and files, such as the GPU, the network, a running
  stack or the Docker daemon, has a level of its own, apart from the unit tests, so that the unit tests stay fast and
  need no outside resource.

## Test support

- **A fake lives next to the port it stands in for,** in the tests of the unit that declares the port, and refuses what
  the real adapter refuses, so that the code under test behaves the same on it as on the real adapter.
- **Only tests import test support.** The fake OCR sandbox (`server/scanmylib/devtools/fake_ocr.py`) is the exception:
  it ships in the api's image, since the development stack runs it as `ocr-fake`, and it refuses the production project
  and a socket that a real sandbox serves. Every other piece of test support lives in a test directory.
