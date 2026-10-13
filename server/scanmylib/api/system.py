"""Health, status, pairing and web session routes."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import API_LEVEL, __version__
from ..auth import SESSION_COOKIE, SESSION_MAX_AGE_S
from ..ocr_client import OcrUnavailable
from ..qr import qr_svg
from ..text import single_line
from .deps import Services, ServicesDep, public_url, require_auth
from .schemas import SessionBody

public = APIRouter()
protected = APIRouter(dependencies=[Depends(require_auth)])

APK_DOWNLOAD_PATH = "/download/scanmylib.apk"


@public.get("/api/health")
async def health() -> dict:
    return {"name": "ScanMyLib", "version": __version__, "api": API_LEVEL}


@public.post("/api/session", status_code=204)
async def open_session(body: SessionBody, request: Request, services: ServicesDep) -> Response:
    if not services.auth.token_matches(body.token.strip()):
        raise HTTPException(401, "unauthorized")
    response = Response(status_code=204)
    response.set_cookie(
        SESSION_COOKIE,
        services.auth.open_session(),
        max_age=SESSION_MAX_AGE_S,
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    return response


@public.delete("/api/session", status_code=204)
async def close_session(request: Request, services: ServicesDep) -> Response:
    """Log out: forget the session (if any) and clear the cookie."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        services.auth.close_session(session_id)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response


def _sandbox_text(value: Any, limit: int) -> str | None:
    """A string of the sandbox's /health (untrusted): one printable line, bounded."""
    if not isinstance(value, str):
        return None
    return single_line(value.encode("utf-8", "replace").decode("utf-8"))[:limit] or None


def _sandbox_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value if math.isfinite(value) else None


def _sandbox_gpu(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    return {
        "name": _sandbox_text(value.get("name"), 128),
        "memory_used_mb": _sandbox_number(value.get("memory_used_mb")),
        "memory_total_mb": _sandbox_number(value.get("memory_total_mb")),
    }


@protected.get("/api/status")
async def status(services: ServicesDep) -> dict:
    try:
        health = await services.ocr.health()
    except OcrUnavailable as exc:
        ocr = {"reachable": False, "state": "unreachable", "backend": None, "last_error": str(exc), "gpu": None}
    else:
        # Relayed to the web UI and the phone: only the documented fields, typed and bounded.
        engine = health.get("engine") if isinstance(health.get("engine"), dict) else {}
        ocr = {
            "reachable": True,
            "state": _sandbox_text(engine.get("state"), 32),
            "backend": _sandbox_text(engine.get("backend"), 32),
            "last_error": _sandbox_text(engine.get("last_error"), 1000),
            "gpu": _sandbox_gpu(health.get("gpu")),
        }
    return {
        "version": __version__,
        "ocr": ocr,
        "queue": services.library.queue_counts(),
        "library_dir": services.settings.library_host_path,
    }


def _pairing(services: Services, request: Request) -> dict:
    url = public_url(services, request)
    token = services.auth.token
    return {
        "url": url,
        "token": token,
        "pair_uri": f"scanmylib://pair?url={quote(url, safe='')}&token={quote(token, safe='')}",
        "apk_available": services.settings.apk_path.is_file(),
        "apk_url": url + APK_DOWNLOAD_PATH,
    }


@protected.get("/api/pairing")
async def pairing(request: Request, services: ServicesDep) -> dict:
    return _pairing(services, request)


@protected.get("/api/pairing/qr.svg")
async def pairing_qr(request: Request, services: ServicesDep) -> Response:
    return Response(qr_svg(_pairing(services, request)["pair_uri"]), media_type="image/svg+xml")


@protected.get("/api/pairing/apk-qr.svg")
async def apk_qr(request: Request, services: ServicesDep) -> Response:
    return Response(qr_svg(_pairing(services, request)["apk_url"]), media_type="image/svg+xml")
