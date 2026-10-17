---
paths:
  - "**/*.sh"
---

# Bash

The scripts of `scripts/` and `ocr/setup/` are written in Bash, from Google's Shell Style Guide and ShellCheck's checks.
These rules come on top of `conventions.md`.

- **Strict mode:** `#!/usr/bin/env bash`, then `set -euo pipefail`. A library that scripts source, such as
  `scripts/lib/common.sh`, has no shebang.
- **Logic goes to Python.** A script runs commands. Parsing text, checking paths or settings, and any data structure go
  to a module of `scripts/lib/` written with the standard library only, such as `stack.py` and `version.py`, where
  `scripts/tests/` tests them.
- **Every expansion is quoted** (`"$path"`, `"${arguments[@]}"`), and a list is an array, never a string split on
  spaces. Tests use `[[ … ]]`, command substitution `$(…)`, and arithmetic `(( … ))`. An operand of `[[ … ]]`, the word
  of a `case` and the value of an assignment may stay unquoted, since Bash never splits them. On the right side of `==`,
  `!=` and `=~`, a quoted part matches literally: quote what must match as it is, and leave a pattern or a regular
  expression unquoted.
- **Casing and scope:** functions and local variables in `snake_case`, declared `local` inside a function; constants and
  environment variables in `UPPER_SNAKE_CASE`. A positional parameter is read once into a named variable
  (`local checkout=$1`).
- **No `eval`, and a `.env` is never sourced:** `scripts/lib/stack.py env` checks it, then prints its lines. A command
  is never built from a string.
- **Errors go through `die`** (`scripts/lib/common.sh`): to stderr, with a message that says what to do, and a non-zero
  exit status.
- **Temporary files** come from `mktemp`, and a `trap … EXIT` removes them.
- **Layout:** 4-space indentation, 120 columns.
- **Directives:** `# shellcheck disable=SCxxxx  # reason` and `# shellcheck source=…`.
