"""ScanMyLib API server: phone uploads, OCR orchestration, Markdown library for agents."""

from __future__ import annotations

import re
from pathlib import Path

#: Version of the HTTP API contract (docs/API.md), reported by /api/health.
API_LEVEL = 1

#: The repository's VERSION file, which the image build copies next to the package (/app/VERSION).
VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"

_VERSION_TEXT = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}")


def read_version(path: Path = VERSION_FILE) -> str:
    """The project version written in `path`, or "unknown" when the build did not provide it."""
    try:
        version = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return "unknown"
    return version if _VERSION_TEXT.fullmatch(version) else "unknown"


#: The project version, shared by the api and the Android app (VERSION at the repository root).
__version__ = read_version()
