"""Health, status, pairing and web session routes."""

from __future__ import annotations

from typing import TypedDict
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...application.catalog import QueueCounts
from ...application.ocr_engine import EngineStatus, GpuStatus
from ...application.status import report_ocr_status
from ...domain.web_sessions import SESSION_LIFETIME
from ..filesystem.published_apk import APK_DOWNLOAD_PATH, published_apk
from ..qr_codes import qr_svg
from .authentication import SESSION_COOKIE
from .dependencies import Services, ServicesDep, public_url, require_auth
from .schemas import SessionBody

#: Version of the HTTP API contract (docs/API.md), reported by /api/health.
API_LEVEL = 1

public = APIRouter()
protected = APIRouter(dependencies=[Depends(require_auth)])


class _Pairing(TypedDict):
    url: str
    token: str
    pair_uri: str
    apk_available: bool
    apk_url: str


# Not async: it reads the APK's metadata file (FastAPI runs it in its thread pool).
@public.get("/api/health")
def health(services: ServicesDep) -> dict[str, object]:
    # The published APK: the app offers it as an update when its version code is higher.
    return {
        "name": "ScanMyLib",
        "version": services.settings.version,
        "api": API_LEVEL,
        "apk": published_apk(services.settings.apk_path),
    }


@public.post("/api/session", status_code=204)
async def open_session(body: SessionBody, request: Request, services: ServicesDep) -> Response:
    if not services.access.token_matches(body.token.strip()):
        raise HTTPException(401, "unauthorized")
    response = Response(status_code=204)
    response.set_cookie(
        SESSION_COOKIE,
        services.access.open_session(),
        max_age=int(SESSION_LIFETIME.total_seconds()),
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
        services.access.close_session(session_id)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response


def _build_gpu_status_json(gpu: GpuStatus | None) -> dict[str, object] | None:
    if gpu is None:
        return None
    return {
        "name": gpu.name,
        "memory_used_mb": gpu.memory_used_mebibytes,
        "memory_total_mb": gpu.memory_total_mebibytes,
    }


def _build_engine_status_json(engine_status: EngineStatus) -> dict[str, object]:
    return {
        "reachable": engine_status.is_reachable,
        "state": engine_status.state,
        "backend": engine_status.backend,
        "last_error": engine_status.last_error,
        "gpu": _build_gpu_status_json(engine_status.gpu),
    }


def _build_queue_counts_json(queue_counts: QueueCounts) -> dict[str, int]:
    return {
        "queued": queue_counts.queued_count,
        "processing": queue_counts.processing_count,
        "error": queue_counts.error_count,
        "done": queue_counts.done_count,
    }


@protected.get("/api/status")
async def status(services: ServicesDep) -> dict[str, object]:
    ocr_status = await report_ocr_status(services.ocr, services.library)
    return {
        "version": services.settings.version,
        "ocr": _build_engine_status_json(ocr_status.engine_status),
        "queue": _build_queue_counts_json(ocr_status.queue_counts),
        "library_dir": services.settings.library_host_path,
    }


def _pairing(services: Services, request: Request) -> _Pairing:
    url = public_url(services, request)
    token = services.access.token
    return {
        "url": url,
        "token": token,
        "pair_uri": f"scanmylib://pair?url={quote(url, safe='')}&token={quote(token, safe='')}",
        "apk_available": services.settings.apk_path.is_file(),
        "apk_url": url + APK_DOWNLOAD_PATH,
    }


@protected.get("/api/pairing")
async def pairing(request: Request, services: ServicesDep) -> _Pairing:
    return _pairing(services, request)


@protected.get("/api/pairing/qr.svg")
async def pairing_qr(request: Request, services: ServicesDep) -> Response:
    return Response(qr_svg(_pairing(services, request)["pair_uri"]), media_type="image/svg+xml")


@protected.get("/api/pairing/apk-qr.svg")
async def apk_qr(request: Request, services: ServicesDep) -> Response:
    return Response(qr_svg(_pairing(services, request)["apk_url"]), media_type="image/svg+xml")
