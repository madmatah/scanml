"""Minimal stdlib client for the sandbox socket.

Running the module is the container's health check: it exits 0 when the
supervisor answers ``GET /health`` (``python3 -m scanmylib_ocr.client``).
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import sys
from typing import Any

DEFAULT_SOCKET = "/run/scanmylib/ocr.sock"


class UnixHTTPConnection(http.client.HTTPConnection):
    """``http.client`` connection over a Unix domain socket."""

    def __init__(self, socket_path: str, timeout: float = 900.0) -> None:
        super().__init__("ocr", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._socket_path)


def request_json(
    socket_path: str,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 900.0,
) -> tuple[int, Any]:
    """Send one request and return ``(status, decoded JSON body)``."""
    connection = UnixHTTPConnection(socket_path, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b"null")
    finally:
        connection.close()


def main() -> int:
    socket_path = os.environ.get("OCR_SOCKET", DEFAULT_SOCKET)
    try:
        status, health = request_json(socket_path, "GET", "/health", timeout=5.0)
    except (OSError, ValueError) as exc:
        print(f"unhealthy: {exc}", file=sys.stderr)
        return 1
    if status != 200 or not isinstance(health, dict) or health.get("status") != "ok":
        print(f"unhealthy: HTTP {status}", file=sys.stderr)
        return 1
    print(f"ok: engine {health['engine']['state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
