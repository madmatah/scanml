# Code conventions

These rules apply to code, tests and configuration, in every part of the repository. Each language adds its own rules,
and the idioms that override the naming rules below, in a rules file of its own: `python.md`, `kotlin.md`, `web.md`
(TypeScript and React, and JavaScript until the web UI moves to them) and `bash.md`.

## Naming

Names carry the meaning that comments may not carry.

- **Explicit, in the vocabulary of the domain.** A name says what a thing is or does: `page_number_hint`,
  `assemble_document`, `isDuplicate`. A concept keeps one name everywhere: in the documents, the code, the tests, the
  API and the UI's English text (a page, a document, a scan, the library, the reading order, the coverage).
- **No generic names:** `data`, `info`, `value`, `item`, `result`, `temp`, `obj`, `manager`, `handler`, `helper`,
  `util`.
- **No abbreviations and no single letters.** Write `elapsed_seconds`, not `dt`; `row_index`, not `i`; `request`, not
  `req`. Type parameters are named too: `Entry`, not `T`.
- **Acronyms are written as words:** `page_id`, `OcrClient`, `httpClient`. Only the acronyms established in the domain
  or on the platform are allowed: `api`, `apk`, `ci`, `css`, `csp`, `dom`, `exif`, `gpu`, `html`, `http`, `id`, `ip`,
  `jpeg`, `json`, `lan`, `ocr`, `png`, `qr`, `sdk`, `sha256`, `ui`, `url`, `uuid`, `vram` and `webp`. Anything else is
  spelled out.
- **Booleans are predicates:** `is_excluded`, `hasMarkdown`, `canRetry`.
- **Functions start with a verb:** `assemble_document`, `uploadPage`. Types and values are nouns.
- **Casing** is the language's own, as its rules file states it. A file is named after the concept it holds, and so is
  its test.
- **Only the idioms that a language's rules file allows override these rules.**
- **A name outside the program keeps its spelling** until a change of that interface is worth breaking it: a variable of
  `.env` (`OCR_IDLE_UNLOAD_S`), a field of the HTTP API or of the sandbox protocol, a column of the database, a file of
  the library. Changing one breaks the installations, phones and agents that use it.

## Units

- **A quantity that has a unit carries it in its name, spelled out in full:** `idle_unload_seconds`, `size_bytes`,
  `max_side_pixels`. Discrete units count too: `retry_count` is dimensionless, `delay_milliseconds` is not.
  Dimensionless quantities take no suffix: `scale_ratio`, `page_count`.
- **A type that carries the unit replaces the suffix.** A duration type already says the unit, and a name that repeats
  it could contradict it: `timeout: Duration`, not `timeoutSeconds: Duration`.
- **A vector or a structure carries its unit, and the axis or the field is a property:** `bbox_pixels.left`, never
  `bbox_left_pixels`.

## Comments

The names and the structure say what the code does, and the tests state the business rules, so a comment can only add a
why.

- **No comments, except a why.** A comment never says what the code does.
- **A business rule is never a comment.** It is a test whose name states it.
- **A why is a last resort,** written only when neither the code nor a test can say it. Typical cases: a workaround for
  a platform or library bug, with its link; a constraint taken from a reference, with its source; a security boundary
  whose reason the code cannot show.
- **A documentation comment follows the same rule.** A docstring or a doc block that restates the signature, carries
  tags such as `@param` or `@returns`, or says what the code does is forbidden: the names and the types already say it.
  One that gives a why is a comment like any other.
- **The usage header of a script is its help text,** which its `usage` prints: it documents the script for people, and
  is not a comment.
- **Allowed directives,** as comments or as attributes: those that the language's rules file lists. A directive that
  suppresses a check states its reason.
- **A version label next to a pinned commit SHA is allowed,** such as `# v7.0.1` after an action in a GitHub Actions
  workflow: it names the release, which the SHA cannot say.
- **Forbidden:** commented-out code, and banners.
- **Scope:** every file but prose documents, configuration and scripts included. Ruff flags commented-out Python code;
  review checks the rest.

## Characters a reader cannot see

- **A character a reader cannot see is written as an escape, never as such:** a control character other than a tab or a
  line end (a line feed, or a carriage return before it in a file that already ends a line so), a format character
  (bidirectional, zero-width, tags), another default-ignorable one such as a variation selector, a line or paragraph
  separator, a private-use or unassigned code point, a letter or a symbol that renders as blank (a Hangul filler, the
  Braille blank), or a byte that is not UTF-8, anywhere in the source (`\N{ESCAPE}` or `\x1b` in Python, a Unicode
  escape in JavaScript). A review cannot judge what it cannot see. Ruff checks most bidirectional characters (not the
  left-to-right and Arabic letter marks), and the backspace, SUB, ESC, NUL and zero-width space in Python strings;
  review checks the rest.

## Input from outside the program

Outside input reaches the project from the phone and the web UI (requests, uploads, the pairing QR code), from other
Android apps (shared photos), from the OCR sandbox (its results), from `.env` files, and from the command line.

- **Outside input is checked before use.** A request, an upload, a shared file, a sandbox result, a command-line
  argument, a URL parameter or a `.env` value is checked for its shape and its bounds. Malformed input fails cleanly,
  without crashing the program or corrupting its state.
- **Outside text never reaches a parser of markup, script, queries, URLs or command lines,** nor a path. Markup is built
  with the platform's text APIs, queries with parameters, paths from checked ids, and a command's arguments are passed
  as a list, never through a shell. For example:
  - the web UI sets `textContent`, never `innerHTML` or `insertAdjacentHTML`, and never builds an event-handler
    attribute, an `href`, a `src` or a `srcdoc` from outside text; the HTML that the server's allowlist sanitizer
    produces is the one exception, parsed in an inert `<template>`;
  - Python runs `subprocess.run` with a list, without `shell=True`, and SQLite with `?` parameters;
  - a path is built from an id checked against its format (a lowercase hyphenated UUID, a slug), never from a name the
    client or the sandbox sent;
  - Bash passes arguments as arrays, never through `eval`, and reads a `.env` through `scripts/lib/stack.py`, never with
    `source`.
