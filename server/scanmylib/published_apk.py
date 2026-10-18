"""The Android APK the api serves, as described by the metadata published next to it.

`scripts/build-apk.sh` signs the APK and publishes it as `scanmylib.apk`, with its metadata as
`scanmylib.json` in the same directory, written after the APK: a publish cut short leaves no
metadata, never the previous APK's. `/api/health` relays it, so that the app can tell an update
from the version alone, without downloading the APK.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: The download route of the APK.
APK_DOWNLOAD_PATH = "/download/scanmylib.apk"

_APPLICATION_ID = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")
#: A release (MAJOR.MINOR.PATCH) or a development build, e.g. 0.2.4-dev.27+g1a2b3c4d5e6f
#: (scripts/lib/version.py).
_VERSION_NAME = re.compile(r"(?=.{5,64}$)[0-9]{1,3}\.[0-9]{1,2}\.[0-9]{1,3}(-[0-9A-Za-z.]+)?(\+[0-9A-Za-z.]+)?")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_METADATA_BYTES = 4096
_MAX_VERSION_CODE = 2**31 - 1


def metadata_path(apk_path: Path) -> Path:
    """Where the metadata of the APK at `apk_path` is published: `scanmylib.json` next to it."""
    return apk_path.with_suffix(".json")


def _count(value: object, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        return None
    return value


def published_apk(apk_path: Path) -> dict[str, object] | None:
    """The published APK's application id, version, versionCode, SHA-256, size and download path,
    or None when there is no APK, or no metadata that holds up (missing, unreadable, malformed, or
    of another APK: not the size of the one published, e.g. left by a build that published no
    metadata)."""
    metadata = metadata_path(apk_path)
    try:
        if not apk_path.is_file() or metadata.stat().st_size > _MAX_METADATA_BYTES:
            return None
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    application_id, version, sha256 = data.get("application_id"), data.get("version_name"), data.get("sha256")
    version_code = _count(data.get("version_code"), _MAX_VERSION_CODE)
    size = _count(data.get("size"), 2**40)
    if not (
        isinstance(application_id, str)
        and _APPLICATION_ID.fullmatch(application_id)
        and isinstance(version, str)
        and _VERSION_NAME.fullmatch(version)
        and isinstance(sha256, str)
        and _SHA256.fullmatch(sha256)
        and version_code is not None
        and size is not None
    ):
        return None
    try:
        if apk_path.stat().st_size != size:
            return None
    except OSError:
        return None
    return {
        "application_id": application_id,
        "version": version,
        "version_code": version_code,
        "sha256": sha256,
        "size": size,
        "path": APK_DOWNLOAD_PATH,
    }
