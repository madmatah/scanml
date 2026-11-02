"""The file of the API token in the state directory, readable by its owner only: it is written here, never with the
library's atomic writes, which leave a file every user can read."""

from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path


def load_or_create_token(path: Path, override: str | None = None) -> str:
    """The API token: `override` if set, else the content of `path`, created on first use.

    A missing or empty file gets a new token, written to a temporary file then
    renamed: a crash or a full disk never leaves an empty token file behind
    (an empty token would let anyone open a session with an empty token).
    """
    if override:
        return override
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")  # mode 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return token
