"""Pure ASGI middlewares: security headers on every response, request body limits."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from fastapi import HTTPException
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
_SECURITY_HEADERS = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
    # camera=(self): the web UI's photo button relies on <input capture>.
    "permissions-policy": "camera=(self), microphone=(), geolocation=()",
}
# No Cross-Origin-Opener-Policy: browsers ignore it on plain-HTTP LAN origins
# (Chrome logs an error on every page load) and the UI opens no popups.


class SecurityHeadersMiddleware:
    """Adds the security headers; API responses default to ``Cache-Control: no-store``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                headers.setdefault("cache-control", "no-store" if is_api else "no-cache")
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Rejects request bodies above a per-request limit with 413, before buffering them."""

    def __init__(self, app: ASGIApp, limit_for: Callable[[Scope], int]) -> None:
        self.app = app
        self.limit_for = limit_for

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await _send_json(send, 413, {"detail": "request body too large"})
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised from inside body parsing: FastAPI turns it into a 413 response.
                    raise HTTPException(413, "request body too large")
            return message

        await self.app(scope, limited_receive, send)


async def _send_json(send: Send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close")],
    })
    await send({"type": "http.response.body", "body": body})


UPLOAD_PATH = re.compile(r"/api/documents/[^/]+/pages")


def body_limit(upload_bytes: int, default_bytes: int) -> Callable[[Scope], int]:
    """Limit function: larger bodies for page uploads, small JSON bodies elsewhere."""

    def limit_for(scope: Scope) -> int:
        if scope["method"] == "POST" and UPLOAD_PATH.fullmatch(scope["path"]):
            return upload_bytes
        return default_bytes

    return limit_for
