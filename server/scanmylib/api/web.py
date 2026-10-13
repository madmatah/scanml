"""Public routes: the web UI page and the Android APK download."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from .deps import ServicesDep
from .system import APK_DOWNLOAD_PATH

router = APIRouter()

# Shown when the web UI files (scanmylib/web/) are not installed.
_PLACEHOLDER = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ScanMyLib</title></head>
<body>
<h1>ScanMyLib</h1>
<p>The server is running, but the web UI is not installed.</p>
<p>The API is still available to the Android app.</p>
</body>
</html>
"""


@router.get("/", include_in_schema=False)
async def index(services: ServicesDep) -> Response:
    page = services.settings.web_dir / "index.html"
    if page.is_file():
        return FileResponse(page, media_type="text/html; charset=utf-8")
    return HTMLResponse(_PLACEHOLDER)


@router.get(APK_DOWNLOAD_PATH, include_in_schema=False)
async def download_apk(services: ServicesDep) -> FileResponse:
    apk = services.settings.apk_path
    if not apk.is_file():
        raise HTTPException(404, "the Android app has not been built yet")
    return FileResponse(apk, media_type="application/vnd.android.package-archive", filename="scanmylib.apk")
