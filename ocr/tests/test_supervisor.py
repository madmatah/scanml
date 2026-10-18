"""Supervisor tests with a fake engine runtime (stdlib only, no GPU).

Run: docker run --rm --network none -v "$PWD/ocr:/app:ro" scanmylib-ocr:latest \
         python3 -m unittest discover -s /app/tests -v
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from typing import Any

from scanmylib_ocr.client import request_json
from scanmylib_ocr.config import Settings
from scanmylib_ocr.engines import get_spec
from scanmylib_ocr.gpu import GpuMonitor
from scanmylib_ocr.manager import EngineManager
from scanmylib_ocr.protocol import BAD_IMAGE
from scanmylib_ocr.runtime import EngineFailure, EngineStartError
from scanmylib_ocr.supervisor import Supervisor, UnixHTTPServer

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
MANIFEST = {"model": {"repo": "PaddlePaddle/PaddleOCR-VL-1.6", "revision": "test"}}


SIGNAL_TIMEOUT_S = 10.0
"""Upper bound for waiting on a test signal; reaching it means the test is broken, not slow."""


class Signals:
    """Lets a test hold the fake engine at precise points instead of guessing durations.

    ``slow`` pages report that they started, then wait until the test releases them;
    a start waits until the test allows it.
    """

    def __init__(self) -> None:
        self.page_started = threading.Event()
        self.release_pages = threading.Event()
        self.allow_start = threading.Event()
        self.allow_start.set()


class FakeRuntime:
    """Stands in for EngineRuntime. The image bytes select the behavior of a page."""

    def __init__(self, log: list[str], signals: Signals, start_error: str | None = None) -> None:
        self.log = log
        self.signals = signals
        self.start_error = start_error
        self.running = False

    def start(self) -> None:
        self.log.append("start")
        self.signals.allow_start.wait(SIGNAL_TIMEOUT_S)
        if self.start_error:
            raise EngineStartError(self.start_error)
        self.running = True

    def stop(self) -> None:
        self.log.append("stop")
        self.running = False

    def interrupt(self) -> None:
        self.running = False

    def alive(self) -> bool:
        return self.running

    def describe_failure(self) -> str:
        return "fake engine stopped"

    def parse(self, job_id: str, image_path: str, options: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        with open(image_path, "rb") as image_file:
            image = image_file.read()
        tag = image[-8:].rstrip(b"\x00").decode() or "page"
        self.log.append(f"parse:{tag}")
        if tag.startswith("slow"):
            self.signals.page_started.set()
            self.signals.release_pages.wait(SIGNAL_TIMEOUT_S)
        if tag == "crash":
            self.running = False
            raise EngineFailure("worker stopped while processing the page")
        if tag == "garbage":
            return {"id": job_id, "ok": False, "error": BAD_IMAGE, "detail": "cannot decode"}
        result = {
            "width": 100,
            "height": 200,
            "markdown": f"# {tag}",
            "images": [],
            "blocks": [{"label": "number", "content": "42", "bbox": [0, 0, 1, 1], "order": None}],
            "page_numbers": ["42"],
            "page_continuation": None,
            "preprocess": {"angle": 0, "unwarped": bool(options.get("unwarp"))},
        }
        return {"id": job_id, "ok": True, "result": result, "infer_s": 0.01}


def tagged(tag: str, base: bytes = JPEG) -> bytes:
    return base + tag.encode().ljust(8, b"\x00")


class SupervisorTest(unittest.TestCase):
    start_error: str | None = None
    idle_unload_s = 60.0

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.socket_path = os.path.join(self.tmp.name, "ocr.sock")
        with open(os.path.join(self.tmp.name, "MANIFEST.json"), "w") as manifest:
            json.dump(MANIFEST, manifest)
        settings = replace(
            Settings.from_env({}),
            socket_path=self.socket_path,
            work_dir=self.tmp.name,
            idle_unload_s=self.idle_unload_s,
            sandbox_dir=self.tmp.name,
        )
        self.events: list[str] = []
        self.runtimes: list[FakeRuntime] = []
        self.signals = Signals()
        # Never leave a slow page or a start blocked behind a failed assertion.
        self.addCleanup(self.signals.release_pages.set)
        self.addCleanup(self.signals.allow_start.set)

        def make_runtime() -> FakeRuntime:
            runtime = FakeRuntime(self.events, self.signals, self.start_error)
            self.runtimes.append(runtime)
            return runtime

        spec = get_spec(settings.engine)
        self.manager = EngineManager(settings, spec, runtime_factory=make_runtime)
        self.server = UnixHTTPServer(self.socket_path, Supervisor(settings, spec, self.manager, GpuMonitor()))
        self.manager.start()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.manager.shutdown(5)
        self.server.server_close()
        self.tmp.cleanup()

    def call(
        self, method: str, path: str, body: bytes | None = None, content_type: str = "image/jpeg"
    ) -> tuple[int, Any]:
        headers = {"Content-Type": content_type} if body is not None else {}
        return request_json(self.socket_path, method, path, body=body, headers=headers, timeout=10)

    def parse(self, tag: str, query: str = "") -> tuple[int, Any]:
        return self.call("POST", f"/v1/parse?request_id={tag}{query}", tagged(tag))

    def health(self) -> dict[str, Any]:
        status, body = self.call("GET", "/health")
        self.assertEqual(status, 200)
        return body

    def wait_for(self, predicate, what: str) -> dict[str, Any]:
        """Polls /health until ``predicate(health)`` holds."""
        deadline = time.monotonic() + SIGNAL_TIMEOUT_S
        while time.monotonic() < deadline:
            health = self.health()
            if predicate(health):
                return health
            time.sleep(0.01)
        self.fail(f"{what} never happened: {health}")

    def wait_until_a_slow_page_runs(self) -> None:
        self.assertTrue(self.signals.page_started.wait(SIGNAL_TIMEOUT_S), "the slow page never started")

    def wait_for_state(self, state: str, timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            health = self.health()
            if health["engine"]["state"] == state:
                return health
            time.sleep(0.02)
        self.fail(f"engine never reached state {state!r}: {health}")


class ParseTest(SupervisorTest):
    def test_successful_parse_has_the_contract_fields(self) -> None:
        status, body = self.parse("p1", "&unwarp=1")
        self.assertEqual(status, 200)
        self.assertEqual(body["request_id"], "p1")
        self.assertEqual(body["page_numbers"], ["42"])
        self.assertTrue(body["preprocess"]["unwarped"])
        self.assertEqual(body["engine"]["name"], "paddleocr-vl")
        self.assertEqual(body["engine"]["backend"], "vllm")
        self.assertEqual(set(body["timings"]), {"queue_s", "load_s", "infer_s"})
        self.assertEqual(self.events, ["start", "parse:p1"])

    def test_engine_starts_lazily_and_only_once(self) -> None:
        health = self.health()
        self.assertEqual(health["engine"]["state"], "idle")
        self.assertEqual(health["versions"], MANIFEST)
        self.assertEqual(self.parse("a")[0], 200)
        self.assertEqual(self.parse("b")[0], 200)
        self.assertEqual(self.events.count("start"), 1)
        health = self.health()
        self.assertEqual(health["engine"]["state"], "ready")
        self.assertEqual(health["processed"], 2)

    def test_pages_are_processed_one_at_a_time_in_arrival_order(self) -> None:
        results: dict[str, int] = {}
        threads = []
        for waiting, tag in enumerate(("slow1", "slow2", "slow3")):
            thread = threading.Thread(target=lambda t=tag: results.update({t: self.parse(t)[0]}))
            thread.start()
            threads.append(thread)
            if waiting == 0:
                self.wait_until_a_slow_page_runs()
            else:
                self.wait_for(lambda health, n=waiting: health["queue"] == n, f"{waiting} queued pages")
        self.signals.release_pages.set()
        for thread in threads:
            thread.join()
        self.assertEqual(results, {"slow1": 200, "slow2": 200, "slow3": 200})
        self.assertEqual(
            [e for e in self.events if e.startswith("parse")], ["parse:slow1", "parse:slow2", "parse:slow3"]
        )

    def test_health_answers_while_a_page_is_processed(self) -> None:
        worker = threading.Thread(target=self.parse, args=("slow",))
        worker.start()
        self.wait_until_a_slow_page_runs()
        # The page is held inside the engine until released: /health must answer anyway.
        health = self.health()
        self.assertTrue(health["busy"])
        self.assertEqual(health["engine"]["state"], "ready")
        self.signals.release_pages.set()
        worker.join()
        self.assertFalse(self.health()["busy"])

    def test_request_validation(self) -> None:
        status, body = self.call("POST", "/v1/parse", JPEG, content_type="text/plain")
        self.assertEqual((status, body["error"]), (415, "unsupported_type"))
        status, body = self.call("POST", "/v1/parse", b"not an image at all")
        self.assertEqual((status, body["error"]), (400, "bad_image"))
        status, body = self.call("POST", "/v1/parse?unwarp=maybe", JPEG)
        self.assertEqual((status, body["error"]), (400, "bad_request"))
        status, body = self.call("POST", "/v1/parse", tagged("png", PNG), content_type="image/png; charset=binary")
        self.assertEqual(status, 200)
        self.assertEqual(self.call("GET", "/nowhere")[0], 404)

    def test_body_over_40_mib_is_refused_without_reading_it(self) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(self.socket_path)
            client.sendall(
                b"POST /v1/parse HTTP/1.1\r\nHost: ocr\r\nContent-Type: image/jpeg\r\n"
                + f"Content-Length: {40 * 1024 * 1024 + 1}\r\n\r\n".encode()
            )
            # The answer may arrive in several reads; the server closes the connection after it.
            response = b""
            while chunk := client.recv(4096):
                response += chunk
        self.assertTrue(response.startswith(b"HTTP/1.1 413"), response)
        self.assertIn(b'"too_large"', response)
        self.assertEqual(self.events, [])

    def test_bad_image_reported_by_the_worker_is_a_400(self) -> None:
        status, body = self.parse("garbage")
        self.assertEqual((status, body["error"]), (400, "bad_image"))

    def test_crash_during_a_page_is_a_500_and_the_next_page_restarts_the_engine(self) -> None:
        status, body = self.parse("crash")
        self.assertEqual((status, body["error"]), (500, "processing_failed"))
        health = self.wait_for_state("idle")
        self.assertIn("worker stopped", health["engine"]["last_error"])
        self.assertEqual(self.parse("after")[0], 200)
        self.assertEqual(self.events, ["start", "parse:crash", "stop", "start", "parse:after"])

    def test_load_and_unload(self) -> None:
        self.assertEqual(self.call("POST", "/v1/load"), (202, {"state": "starting"}))
        self.wait_for_state("ready")
        self.assertEqual(self.call("POST", "/v1/load"), (200, {"state": "ready"}))
        self.assertEqual(self.call("POST", "/v1/unload"), (200, {"state": "idle"}))
        self.assertEqual(self.health()["engine"]["state"], "idle")
        self.assertEqual(self.events, ["start", "stop"])

    def test_unload_waits_for_the_page_in_progress(self) -> None:
        results: list[int] = []
        worker = threading.Thread(target=lambda: results.append(self.parse("slow")[0]))
        worker.start()
        self.wait_until_a_slow_page_runs()
        unloads: list[tuple[int, Any]] = []
        unloader = threading.Thread(target=lambda: unloads.append(self.call("POST", "/v1/unload")))
        unloader.start()
        unloader.join(0.3)
        self.assertTrue(unloader.is_alive(), "unload returned while a page was still in the engine")
        self.signals.release_pages.set()
        unloader.join()
        worker.join()
        self.assertEqual(unloads, [(200, {"state": "idle"})])
        self.assertEqual(results, [200])
        self.assertEqual(self.events, ["start", "parse:slow", "stop"])


class StartFailureTest(SupervisorTest):
    start_error = "vllm exited with code 1: CUDA out of memory"

    def test_every_waiting_page_gets_503_and_the_error_is_reported(self) -> None:
        self.signals.allow_start.clear()
        results: list[tuple[int, Any]] = []
        threads = [threading.Thread(target=lambda t=t: results.append(self.parse(t))) for t in ("a", "b")]
        threads[0].start()
        self.wait_for(lambda health: health["engine"]["state"] == "starting", "the engine start")
        threads[1].start()
        self.wait_for(lambda health: health["queue"] == 1, "the second page waiting for the start")
        self.signals.allow_start.set()
        for thread in threads:
            thread.join()
        self.assertEqual([status for status, _ in results], [503, 503])
        self.assertTrue(all(body["error"] == "engine_unavailable" for _, body in results))
        self.assertIn("CUDA out of memory", results[0][1]["detail"])
        self.assertEqual(self.events, ["start"])  # one attempt for both pages
        health = self.health()
        self.assertEqual(health["engine"]["state"], "error")
        self.assertIn("CUDA out of memory", health["engine"]["last_error"])


class IdleUnloadTest(SupervisorTest):
    idle_unload_s = 0.5

    def test_engine_is_stopped_after_the_idle_delay(self) -> None:
        self.assertEqual(self.parse("p")[0], 200)
        self.assertEqual(self.health()["engine"]["state"], "ready")
        self.wait_for_state("idle", timeout=3)
        self.assertEqual(self.events, ["start", "parse:p", "stop"])


class SocketTest(unittest.TestCase):
    def test_socket_is_group_writable_only_and_cannot_be_hijacked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ocr.sock")
            with open(os.path.join(tmp, "MANIFEST.json"), "w") as manifest:
                json.dump(MANIFEST, manifest)
            settings = replace(Settings.from_env({}), socket_path=path, work_dir=tmp, sandbox_dir=tmp)
            spec = get_spec(settings.engine)
            supervisor = Supervisor(settings, spec, EngineManager(settings, spec), GpuMonitor())
            server = UnixHTTPServer(path, supervisor)
            try:
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o660)
                with self.assertRaises(RuntimeError):
                    UnixHTTPServer(path, supervisor)
                self.assertTrue(os.path.exists(path))  # the failed second server left it alone
            finally:
                server.server_close()
            self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
