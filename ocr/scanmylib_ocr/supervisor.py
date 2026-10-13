"""OCR sandbox supervisor: the HTTP/1.1 API on a Unix socket (docs/OCR_SANDBOX.md).

Runs with the image's own interpreter and the standard library only, outside
the untrusted venvs. It validates requests, hands pages to the
``EngineManager`` (which owns vLLM and the pipeline worker) and answers
``/health`` from a snapshot that never waits for the engine.

Usage (the container's command): ``python3 -m scanmylib_ocr.supervisor``
"""

from __future__ import annotations

import errno
import http.server
import json
import logging
import os
import re
import signal
import socket
import socketserver
import sys
import threading
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .config import Settings
from .engines import get_spec
from .engines.base import EngineSpec, PageOptions
from .gpu import GpuMonitor
from .manager import EngineManager, ParseJob, Reply, error_reply
from .protocol import BAD_IMAGE, BAD_REQUEST, TOO_LARGE, UNSUPPORTED_TYPE

log = logging.getLogger("scanmylib_ocr.supervisor")

MAX_BODY_BYTES = 40 * 1024 * 1024
MAX_CONTROL_BODY_BYTES = 64 * 1024
CONTENT_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
SHUTDOWN_TIMEOUT_S = 25.0
_REQUEST_ID_UNSAFE = re.compile(r"[^A-Za-z0-9._:-]")


class BadRequest(ValueError):
    pass


def sniff_image_format(data: bytes) -> str | None:
    """File extension matching the image signature of ``data``, if supported."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def parse_flag(query: dict[str, list[str]], name: str, default: bool) -> bool:
    values = query.get(name)
    if not values:
        return default
    value = values[-1].strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise BadRequest(f"query parameter {name!r} must be 0 or 1")


def read_manifest(settings: Settings) -> dict[str, Any]:
    try:
        with open(os.path.join(settings.sandbox_dir, "MANIFEST.json"), encoding="utf-8") as manifest:
            return json.load(manifest)
    except (OSError, ValueError) as exc:
        log.warning("cannot read the sandbox manifest: %s", exc)
        return {}


class Supervisor:
    """The API operations, independent of HTTP plumbing."""

    def __init__(self, settings: Settings, spec: EngineSpec, manager: EngineManager, gpu: GpuMonitor) -> None:
        self.settings = settings
        self.spec = spec
        self.manager = manager
        self.gpu = gpu
        self.versions = read_manifest(settings)

    def health(self) -> dict[str, Any]:
        engine = self.manager.snapshot()
        idle_unload_s = self.settings.idle_unload_s
        return {
            "status": "ok",
            "engine": {
                "name": self.spec.name,
                "state": engine["state"],
                "backend": self.settings.backend,
                "since": engine["since"],
                "last_error": engine["last_error"],
                "idle_unload_s": int(idle_unload_s) if idle_unload_s.is_integer() else idle_unload_s,
            },
            "busy": engine["busy"],
            "queue": engine["queue"],
            "processed": engine["processed"],
            "versions": self.versions,
            # Starting or stopping the engine changes the GPU memory in use.
            "gpu": self.gpu.current(changed_at=engine["state_changed_at"]),
        }

    def parse(self, image: bytes, extension: str, request_id: str, options: PageOptions) -> Reply:
        job = ParseJob(request_id, image, extension, options.to_dict())
        log.info("request %s queued (%d bytes, %s)", request_id, len(image), options)
        self.manager.submit(job)
        return job.wait()

    def load(self) -> Reply:
        state = self.manager.request_load()
        return Reply(200 if state == "ready" else 202, {"state": state})

    def unload(self) -> Reply:
        self.manager.request_unload()
        return Reply(200, {"state": "idle"})


class RequestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "scanmylib-ocr"
    sys_version = ""
    timeout = 300  # seconds allowed to send a request; a page reply may take much longer
    server: UnixHTTPServer

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/health":
            self._send(Reply(200, self.server.supervisor.health()))
        else:
            self._send_not_found()

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        supervisor = self.server.supervisor
        if url.path == "/v1/parse":
            self._send(self._parse(url.query))
        elif url.path in ("/v1/load", "/v1/unload"):
            if not self._discard_body():
                return
            self._send(supervisor.load() if url.path == "/v1/load" else supervisor.unload())
        else:
            self._send_not_found()

    def _parse(self, raw_query: str) -> Reply:
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type not in CONTENT_TYPES:
            self.close_connection = True
            return error_reply(415, UNSUPPORTED_TYPE, f"Content-Type must be one of {', '.join(CONTENT_TYPES)}")
        try:
            length = self._content_length()
            query = parse_qs(raw_query)
            options = PageOptions(
                orientation=parse_flag(query, "orientation", True),
                unwarp=parse_flag(query, "unwarp", False),
                charts=parse_flag(query, "charts", False),
            )
        except BadRequest as exc:
            self.close_connection = True
            return error_reply(400, BAD_REQUEST, str(exc))
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            return error_reply(413, TOO_LARGE, f"image larger than {MAX_BODY_BYTES // (1024 * 1024)} MiB")

        image = self.rfile.read(length)
        if len(image) != length:
            self.close_connection = True
            return error_reply(400, BAD_REQUEST, "request body shorter than its Content-Length")
        extension = sniff_image_format(image)
        if extension is None:
            return error_reply(400, BAD_IMAGE, "body is not a JPEG, PNG or WebP image")
        request_id = _REQUEST_ID_UNSAFE.sub("_", (query.get("request_id") or [""])[-1])[:128] or os.urandom(6).hex()
        return self.server.supervisor.parse(image, extension, request_id, options)

    def _content_length(self) -> int:
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            raise BadRequest("chunked request bodies are not supported: send Content-Length")
        raw = self.headers.get("Content-Length")
        try:
            length = int(raw) if raw is not None else -1
        except ValueError:
            length = -1
        if length < 0:
            raise BadRequest("a valid Content-Length header is required")
        return length

    def _discard_body(self) -> bool:
        """Consume the (normally empty) body of a control request to keep the connection in sync."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_CONTROL_BODY_BYTES:
            self.close_connection = True
            self._send(error_reply(400, BAD_REQUEST, "unexpected request body"))
            return False
        self.rfile.read(length)
        return True

    def _send_not_found(self) -> None:
        self.close_connection = True
        self._send(Reply(404, {"error": "not_found", "detail": f"no route for {self.command} {self.path}"}))

    def _send(self, reply: Reply) -> None:
        payload = json.dumps(reply.body, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(reply.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            log.warning("client went away before the reply to %s %s", self.command, self.path)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (stdlib signature)
        # The default implementation prints the client address, which AF_UNIX peers do not have.
        log.debug("%s", format % args)


class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """Threaded HTTP server on a Unix socket (mode 0660, shared with the api container)."""

    daemon_threads = True

    def __init__(self, path: str, supervisor: Supervisor) -> None:
        self.supervisor = supervisor
        self._bound = False
        super().__init__(path, RequestHandler, bind_and_activate=False)
        try:
            self.server_bind()
            self.server_activate()
        except BaseException:
            self.server_close()
            raise

    def server_bind(self) -> None:
        path = self.server_address
        if os.path.exists(path):
            if _socket_in_use(path):
                raise RuntimeError(f"{path} is served by another process (another ocr container?)")
            os.unlink(path)  # left over by a previous run
        previous_umask = os.umask(0o117)
        try:
            self.socket.bind(path)
        finally:
            os.umask(previous_umask)
        self._bound = True
        os.chmod(path, 0o660)

    def server_close(self) -> None:
        super().server_close()
        if self._bound:
            self._bound = False
            try:
                os.unlink(self.server_address)
            except FileNotFoundError:
                pass


def _socket_in_use(path: str) -> bool:
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(path)
    except OSError as exc:
        if exc.errno in (errno.ECONNREFUSED, errno.ENOENT):
            return False
        raise
    finally:
        probe.close()
    return True


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr
    )
    try:
        settings = Settings.from_env()
        spec = get_spec(settings.engine)
        if settings.backend not in spec.backends:
            raise ValueError(f"engine {spec.name} does not support OCR_BACKEND={settings.backend}")
    except ValueError as exc:
        log.error("invalid configuration: %s", exc)
        return 2
    os.makedirs(settings.work_dir, exist_ok=True)

    gpu = GpuMonitor()
    gpu.refresh()
    manager = EngineManager(settings, spec)
    supervisor = Supervisor(settings, spec, manager, gpu)
    try:
        server = UnixHTTPServer(settings.socket_path, supervisor)
    except (OSError, RuntimeError) as exc:
        log.error("cannot listen on %s: %s", settings.socket_path, exc)
        return 1

    stop_requested = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop_requested.set())

    manager.start()
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
    log.info(
        "listening on %s (engine %s, backend %s, idle unload after %.0f s)",
        settings.socket_path, spec.name, settings.backend, settings.idle_unload_s,
    )  # fmt: skip

    while not stop_requested.wait(1.0):
        pass
    log.info("shutting down")
    server.shutdown()
    manager.shutdown(SHUTDOWN_TIMEOUT_S)
    server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
