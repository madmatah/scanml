"""Messages exchanged between the supervisor and the pipeline worker.

The two processes talk over a dedicated pair of pipes, never over the worker's
stdout/stderr: Paddle, vLLM clients and model code print freely, and none of
that output can end up inside a protocol message. Each message is one JSON
object on one line (JSON escapes newlines inside strings, so framing is safe).

supervisor -> worker::

    {"op": "parse", "id": "<job id>", "image_path": "/tmp/...", "options": {...}}
    {"op": "shutdown"}

worker -> supervisor::

    {"event": "ready"}                                   once, after loading
    {"event": "fatal", "detail": "..."}                  loading failed, worker exits
    {"id": "...", "ok": true, "result": {...}, "infer_s": 1.2}
    {"id": "...", "ok": false, "error": "<code>", "detail": "..."}
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, BinaryIO

# Error codes of the HTTP API (docs/OCR_SANDBOX.md). The worker only reports
# BAD_IMAGE and PROCESSING_FAILED; the others are decided by the supervisor.
BAD_REQUEST = "bad_request"
BAD_IMAGE = "bad_image"
TOO_LARGE = "too_large"
UNSUPPORTED_TYPE = "unsupported_type"
ENGINE_UNAVAILABLE = "engine_unavailable"
PROCESSING_FAILED = "processing_failed"

PROTOCOL_FDS_ENV = "SCANMYLIB_OCR_PROTOCOL_FDS"
"""Environment variable telling the worker which fds carry the protocol ("<in>,<out>")."""

MAX_MESSAGE_BYTES = 256 * 1024 * 1024
"""Longest message line (a page result). The api refuses larger parse responses
anyway; the bound keeps a misbehaving worker from making the supervisor buffer
an endless line."""


class Channel:
    """Newline-delimited JSON messages over a pair of pipe file descriptors."""

    def __init__(self, read_fd: int, write_fd: int) -> None:
        self._reader: BinaryIO = os.fdopen(read_fd, "rb")
        self._writer: BinaryIO = os.fdopen(write_fd, "wb")
        self._write_lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        """Send one message; ``ValueError`` (nothing sent) if it is not serializable or too large."""
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        if len(line) > MAX_MESSAGE_BYTES:
            raise ValueError(f"protocol message of {len(line)} bytes, larger than {MAX_MESSAGE_BYTES}")
        with self._write_lock:
            self._writer.write(line)
            self._writer.flush()

    def receive(self) -> dict[str, Any] | None:
        """Block until the next message; ``None`` when the other side closed the pipe."""
        line = self._reader.readline(MAX_MESSAGE_BYTES + 1)
        if not line:
            return None
        if len(line) > MAX_MESSAGE_BYTES:
            raise ValueError(f"protocol message larger than {MAX_MESSAGE_BYTES} bytes")
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ValueError("protocol message is not a JSON object")
        return message

    def close(self) -> None:
        for stream in (self._writer, self._reader):
            try:
                stream.close()
            except OSError:
                pass
