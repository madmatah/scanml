"""Client of the OCR sandbox: HTTP/1.1 over its Unix socket (docs/OCR_SANDBOX.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

#: Upper bound of a /v1/parse response (64 images of ≤ 20 MiB, base64-encoded,
#: would be more, but no real page comes close; anything bigger is refused).
MAX_RESPONSE_BYTES = 128 * 1024 * 1024
#: Error bodies, /health and /v1/load answers: small JSON documents.
_MAX_ERROR_BYTES = 64 * 1024


class OcrUnavailable(Exception):
    """The sandbox cannot take work right now (socket absent, engine failed to start...)."""


class OcrPageFailed(Exception):
    """The sandbox failed on this page; it may succeed on a retry."""


class OcrPageRejected(Exception):
    """The sandbox refuses this page (bad image, too large...); retrying is pointless."""


async def _read_limited(response: httpx.Response, limit: int, error: type[Exception] = OcrPageFailed) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise error(f"response larger than {limit} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _error_message(status: int, body: bytes) -> str:
    try:
        payload = json.loads(body)
        error, detail = payload.get("error"), payload.get("detail")
    except (ValueError, AttributeError, RecursionError):
        error, detail = None, None
    text = ": ".join(str(part)[:300] for part in (error, detail) if part)
    return f"HTTP {status}" + (f" ({text})" if text else "")


class OcrClient:
    def __init__(self, socket_path: Path, parse_timeout_s: float) -> None:
        self._socket_path = socket_path
        self._parse_timeout = httpx.Timeout(parse_timeout_s, connect=5.0)
        # No keep-alive: after a sandbox restart a pooled connection would be stale.
        self._client = httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=str(socket_path), limits=httpx.Limits(max_keepalive_connections=0)),
            base_url="http://ocr",
            timeout=httpx.Timeout(5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        """The sandbox's /health document (untrusted); raises OcrUnavailable if it does not answer."""
        try:
            async with self._client.stream("GET", "/health", timeout=3.0) as response:
                response.raise_for_status()
                body = await _read_limited(response, _MAX_ERROR_BYTES, OcrUnavailable)
            payload = json.loads(body)
        except (httpx.HTTPError, ValueError, RecursionError) as exc:
            raise OcrUnavailable(self._describe(exc)) from exc
        if not isinstance(payload, dict):
            raise OcrUnavailable("unexpected /health response")
        return payload

    async def load(self) -> None:
        """Ask the sandbox to start its engine now (pre-warm)."""
        try:
            async with self._client.stream("POST", "/v1/load", timeout=10.0) as response:
                body = await _read_limited(response, _MAX_ERROR_BYTES, OcrUnavailable)
        except httpx.HTTPError as exc:
            raise OcrUnavailable(self._describe(exc)) from exc
        if response.status_code >= 400:
            raise OcrUnavailable(_error_message(response.status_code, body))

    async def parse(self, image: bytes, *, request_id: str, unwarp: bool, orientation: bool) -> Any:
        """OCR one page image (JPEG). Returns the decoded JSON response (untrusted)."""
        params = {
            "request_id": request_id,
            "unwarp": "1" if unwarp else "0",
            "orientation": "1" if orientation else "0",
        }
        try:
            async with self._client.stream(
                "POST",
                "/v1/parse",
                params=params,
                content=image,
                headers={"Content-Type": "image/jpeg"},
                timeout=self._parse_timeout,
            ) as response:
                if response.status_code == 200:
                    body = await _read_limited(response, MAX_RESPONSE_BYTES)
                else:
                    body = await _read_limited(response, _MAX_ERROR_BYTES)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise OcrUnavailable(self._describe(exc)) from exc
        except httpx.TimeoutException as exc:
            raise OcrPageFailed("the sandbox did not answer in time") from exc
        except httpx.HTTPError as exc:
            # Includes a connection dropped mid-request: counted as a failed
            # attempt, so a page that crashes the sandbox cannot loop forever.
            raise OcrPageFailed(self._describe(exc)) from exc

        status = response.status_code
        if status == 200:
            try:
                return json.loads(body)
            except (ValueError, RecursionError) as exc:
                raise OcrPageFailed("invalid JSON from the sandbox") from exc
        message = _error_message(status, body)
        if status == 503:
            raise OcrUnavailable(message)
        if status in (400, 413, 415):
            raise OcrPageRejected(message)
        raise OcrPageFailed(message)

    def _describe(self, exc: Exception) -> str:
        if isinstance(exc, httpx.ConnectError) and not self._socket_path.exists():
            return f"socket {self._socket_path} absent"
        return f"{type(exc).__name__}: {exc}"[:300]
