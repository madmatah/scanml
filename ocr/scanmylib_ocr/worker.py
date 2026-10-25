"""Pipeline worker: loads the configured OCR engine and parses pages for the supervisor.

Started by the supervisor with the engine's venv interpreter, e.g.
``/opt/sandbox/venv-paddle/bin/python -m scanmylib_ocr.worker``. It receives
requests and sends results only through the protocol pipes named in
``$SCANMYLIB_OCR_PROTOCOL_FDS`` (see ``protocol.py``); its stdout and stderr
are plain logs, so library output can never corrupt a message.

``--check`` opens no protocol pipe: ``engine_environment.py`` runs it without a
supervisor.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections.abc import Sequence
from typing import Any

from .config import Settings
from .engines import get_spec
from .engines.base import PageEngine, PageInputError, PageOptions
from .protocol import BAD_IMAGE, PROCESSING_FAILED, PROTOCOL_FDS_ENV, Channel

log = logging.getLogger("scanmylib_ocr.worker")

MAX_DETAIL_CHARS = 2000


def describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_DETAIL_CHARS]


def _protocol_fds() -> tuple[int, int]:
    try:
        read_fd, write_fd = (int(fd) for fd in os.environ[PROTOCOL_FDS_ENV].split(","))
    except (KeyError, ValueError):
        sys.exit(f"{PROTOCOL_FDS_ENV} must name the protocol pipes; this module is started by the supervisor")
    return read_fd, write_fd


def handle_parse(engine: PageEngine, message: dict[str, Any]) -> dict[str, Any]:
    job_id = message.get("id")
    started = time.monotonic()
    try:
        result = engine.parse(message["image_path"], PageOptions.from_dict(message.get("options") or {}))
    except PageInputError as exc:
        return {"id": job_id, "ok": False, "error": BAD_IMAGE, "detail": str(exc)[:MAX_DETAIL_CHARS]}
    except Exception as exc:
        log.exception("page %s failed", job_id)
        return {"id": job_id, "ok": False, "error": PROCESSING_FAILED, "detail": describe(exc)}
    return {"id": job_id, "ok": True, "result": result, "infer_s": round(time.monotonic() - started, 3)}


def serve(channel: Channel, engine: PageEngine) -> None:
    while (message := channel.receive()) is not None:
        operation = message.get("op")
        if operation == "shutdown":
            return
        if operation != "parse":
            log.warning("ignoring unknown operation %r", operation)
            continue
        reply = handle_parse(engine, message)
        try:
            channel.send(reply)
        except (TypeError, ValueError) as exc:  # a result that is not JSON-serializable, or too large
            log.exception("cannot send the result of page %s", reply.get("id"))
            channel.send({"id": reply.get("id"), "ok": False, "error": PROCESSING_FAILED, "detail": describe(exc)})


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scanmylib_ocr.worker")
    parser.add_argument(
        "--check", action="store_true", help="import the engine's libraries without loading a model, then exit"
    )
    return parser.parse_args(argv)


def _check_libraries() -> int:
    settings = Settings.from_env()
    get_spec(settings.engine).create_engine(settings).import_libraries()
    print(f"ok: the {settings.engine} engine's libraries import")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if _parse_arguments(argv).check:
        return _check_libraries()
    read_fd, write_fd = _protocol_fds()
    # Whatever libraries print on stdout (from Python or C) joins the log stream.
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    for noisy in ("httpx", "httpx2"):  # one line per VLM sub-request, dozens per page
        logging.getLogger(noisy).setLevel(logging.WARNING)
    channel = Channel(read_fd, write_fd)

    try:
        settings = Settings.from_env()
        engine = get_spec(settings.engine).create_engine(settings)
        started = time.monotonic()
        engine.load()
    except Exception as exc:
        log.exception("the OCR engine failed to load")
        channel.send({"event": "fatal", "detail": describe(exc)})
        return 1
    log.info("engine %s loaded in %.1f s", settings.engine, time.monotonic() - started)
    channel.send({"event": "ready"})

    try:
        serve(channel, engine)
    finally:
        engine.close()
        channel.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
