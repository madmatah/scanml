---
paths:
  - "**/*.py"
  - "server/pyproject.toml"
---

# Python

The api (`server/`), the OCR sandbox (`ocr/`) and the scripts (`scripts/`) are written in Python 3.12, from the Python
Software Foundation's style guide (PEP 8) and its typing PEPs. These rules come on top of `conventions.md`.

- **PEP 8, at 120 columns:** 4-space indentation, imports at the top, grouped as standard library, third party, then the
  project's own. The code is 120 columns wide, which PEP 8 allows a team to choose over 79.
- **Casing:** `snake_case` for modules, functions and variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for module
  constants. Acronyms are written as words in every case (`OcrClient`, `api_token`), where PEP 8 would capitalize them
  in class names (`OCRClient`), so that a name is spelled the same in the four languages of the project.
- **Every signature is typed,** its parameters and its return, in the current syntax: `str | None`, `list[str]`,
  `dict[str, int]`, never `Optional`, `List` or `Dict`. Each module starts with `from __future__ import annotations`, so
  that a type may name a class defined further down. No `Any`, except where untyped data enters, such as parsed JSON,
  which becomes typed values at once.
- **Plain data is a frozen dataclass** (`@dataclass(frozen=True)`), and a closed set of values an `enum.Enum`. A dict
  crosses no module boundary, except at the edge where it becomes JSON.
- **Errors say what went wrong.** An exception is named after it and derives from the nearest built-in one
  (`NotFound(LookupError)`, `ImageRejected(ValueError)`). `raise … from error` keeps the cause, and `from None` replaces
  it on purpose. Catch the narrowest exception. `except Exception` only at a boundary that must keep running, such as
  the OCR loop or an image decoder that raises assorted types, with a comment that says why, and `except BaseException`
  only to clean up and raise again.
- **What is internal starts with `_`,** and nothing imports another module's `_` name: a module's public names are its
  entry point. No `import *`. Inside a package, imports are relative (`from .records import PageRecord`).
- **Async code never blocks the event loop.** Blocking work in a coroutine (files, SQLite, images) runs in
  `asyncio.to_thread`.
- **No mutable default argument,** and no mutable class attribute shared between instances: a dataclass field takes
  `field(default_factory=…)`.
- **Idioms that override the naming rules:** `self` and `cls`; dunder names (`__init__`, `__main__.py`); `exc` for a
  caught exception; `_` for a value ignored on purpose; in tests, a pytest fixture named for the value it provides, and
  test groups named as their phrase (`TestWhenTheNumeralIsNotCanonical`,
  `TheReleaseCodeFunctionWhenTheMinorVersionChanges`), as `tests.md` > pytest and > unittest write them; and the names a
  library or the standard library imposes, such as the `format` parameter of `BaseHTTPRequestHandler.log_message`.
- **Directives:** `# type: ignore[code]` and `# noqa: CODE`, always with the code and the reason. A bare
  `# type: ignore` or `# noqa` is refused: it would silence every other error on its line. `# fmt: skip` keeps a call or
  a literal laid out by hand where the formatter would put each item on its own line and lose what reads together: a
  command's options and their values, a request's parameters, a log message and its values, the corners of a shape.
