"""Processes of a loaded engine: the vLLM server and the pipeline worker.

Each child runs in its own process group so that stopping it also stops the
processes it spawned (vLLM's engine core), which is what actually releases the
GPU memory. Children's output is relayed line by line to the supervisor's log,
escaped where it enters the supervisor, so that no control sequence of the
sandbox reaches an operator's terminal through the log or the error messages.
"""

from __future__ import annotations

import collections
import logging
import os
import queue
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .config import Settings
from .engines.base import EngineSpec
from .printable_text import cut_escaped, escape_unprintable
from .protocol import PROTOCOL_FDS_ENV, Channel

log = logging.getLogger(__name__)

VLLM_HOST = "127.0.0.1"
WORKER_EXIT_WAIT_S = 5.0
WORKER_SHUTDOWN_GRACE_S = 10.0
VLLM_SHUTDOWN_GRACE_S = 15.0
OUTPUT_TAIL_LINES = 200
MAX_OUTPUT_LINE_BYTES = 64 * 1024
"""Longer output lines are relayed in pieces (never buffered whole)."""
QUOTED_DETAIL_CHARACTERS = 400
_EXCEPTION_LINE = re.compile(
    r"(?:\b|(?<=\\x[0-9a-f]{2})|(?<=\\u[0-9a-f]{4})|(?<=\\U[0-9a-f]{8}))(?<!\\)([A-Z]\w*(?:Error|Exception|Exit): .*)$"
)


class EngineStartError(RuntimeError):
    """The engine could not be started (reported to clients as ``engine_unavailable``)."""


class EngineFailure(RuntimeError):
    """The engine died or stopped answering while processing a page."""


class ChildProcess:
    """A child process leading its own process group, its output relayed to our log."""

    def __init__(self, name: str, argv: list[str], env: dict[str, str], pass_fds: tuple[int, ...] = ()) -> None:
        self.name = name
        self._tail: collections.deque[str] = collections.deque(maxlen=OUTPUT_TAIL_LINES)
        self._process = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            pass_fds=pass_fds,
            start_new_session=True,
        )
        self._relay = threading.Thread(target=self._relay_output, name=f"{name}-output", daemon=True)
        self._relay.start()

    def _relay_output(self) -> None:
        child_log = logging.getLogger(self.name)
        assert self._process.stdout is not None
        with self._process.stdout as output:
            # Bounded reads: a child printing endless data without a newline must
            # not make the supervisor hold all of it in memory.
            for raw in iter(lambda: output.readline(MAX_OUTPUT_LINE_BYTES), b""):
                line = escape_unprintable(raw.decode("utf-8", errors="replace").rstrip())
                if line:
                    self._tail.append(line)
                    child_log.info("%s", line)

    @property
    def returncode(self) -> int | None:
        return self._process.poll()

    def output_tail(self) -> list[str]:
        """The lines as they were relayed, escaped, so that a caller may print them to a terminal."""
        return list(self._tail)

    def describe_exit(self) -> str:
        """Exit status and the exceptions found at the end of the output, for error messages.

        A failed vLLM start ends with a generic "Engine core initialization
        failed. See root cause above": the root cause is an earlier exception
        line of the engine core, hence the search over the recent output.
        """
        lines = self.output_tail()
        exceptions: list[str] = []
        for line in lines:
            match = _EXCEPTION_LINE.search(line)
            if match and match.group(1) not in exceptions:
                exceptions.append(match.group(1))
        details = exceptions[-3:] or [line.strip() for line in lines[-3:]]
        summary = " | ".join(cut_escaped(detail, QUOTED_DETAIL_CHARACTERS) for detail in details)
        status = self._process.poll()
        state = "is still running" if status is None else f"exited with code {status}"
        return f"{self.name} {state}" + (f": {summary}" if summary else "")

    def wait(self, timeout_s: float) -> bool:
        """Wait for the process to exit by itself; return whether it did."""
        try:
            self._process.wait(timeout_s)
        except subprocess.TimeoutExpired:
            return False
        return True

    def signal(self, signum: int) -> None:
        """Send a signal to the whole process group (safe to call from any thread)."""
        try:
            os.killpg(self._process.pid, signum)
        except ProcessLookupError:
            pass

    def stop(self, grace_s: float) -> None:
        """Terminate the process group, killing whatever is left after ``grace_s``."""
        if self._process.poll() is None:
            self.signal(signal.SIGTERM)
            try:
                self._process.wait(grace_s)
            except subprocess.TimeoutExpired:
                log.warning("%s did not stop within %.0f s, killing it", self.name, grace_s)
        # Children of the leader (e.g. vLLM's engine core) may outlive it.
        self.signal(signal.SIGKILL)
        self._process.wait()
        self._relay.join(timeout=5)


class EngineRuntime:
    """One loaded engine: its vLLM server (when the backend uses one) and its pipeline worker."""

    def __init__(self, settings: Settings, spec: EngineSpec) -> None:
        self._settings = settings
        self._spec = spec
        self._vllm: ChildProcess | None = None
        self._worker: ChildProcess | None = None
        self._channel: Channel | None = None
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._protocol_error: str | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Start the processes and wait until both can serve pages."""
        deadline = time.monotonic() + self._settings.start_timeout_s
        try:
            serve_args = self._spec.vllm_serve_args(self._settings)
            if serve_args is not None:
                self._vllm = ChildProcess("vllm", self._vllm_argv(serve_args), self._vllm_env())
            # The worker loads its models while vLLM starts.
            self._start_worker()
            self._wait_until_ready(deadline)
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        """Stop the worker, then vLLM. Returns once their GPU memory is released."""
        if self._worker is not None:
            if self._channel is not None and self._worker.returncode is None:
                try:
                    self._channel.send({"op": "shutdown"})
                    self._worker.wait(WORKER_EXIT_WAIT_S)
                except OSError:
                    pass
            self._worker.stop(WORKER_SHUTDOWN_GRACE_S)
            self._worker = None
        if self._channel is not None:
            self._channel.close()
            self._channel = None
        if self._vllm is not None:
            self._vllm.stop(VLLM_SHUTDOWN_GRACE_S)
            self._vllm = None

    def interrupt(self) -> None:
        """Ask the processes to terminate now, from any thread.

        A ``start()`` or ``parse()`` in progress then fails promptly; the
        thread that owns the runtime still calls ``stop()`` to reap them.
        """
        for child in (self._worker, self._vllm):
            if child is not None:
                child.signal(signal.SIGTERM)

    def alive(self) -> bool:
        children = [child for child in (self._worker, self._vllm) if child is not None]
        return bool(children) and all(child.returncode is None for child in children)

    def describe_failure(self) -> str:
        for child in (self._vllm, self._worker):
            if child is not None and child.returncode is not None:
                return child.describe_exit()
        return "engine processes are not running"

    # -- pages -------------------------------------------------------------

    def parse(self, job_id: str, image_path: str, options: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        """Have the worker parse one page; return its reply message."""
        if self._channel is None:
            raise EngineFailure("engine is not running")
        try:
            self._channel.send({"op": "parse", "id": job_id, "image_path": image_path, "options": options})
        except OSError as exc:
            raise EngineFailure(f"cannot reach the worker ({exc}); {self.describe_failure()}") from exc

        deadline = time.monotonic() + timeout_s
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty:
                break
            if message is None:  # the worker closed its pipe (it is exiting) or broke the protocol
                if self._protocol_error is not None:
                    raise EngineFailure(self._protocol_error)
                if self._worker is not None:
                    self._worker.wait(WORKER_EXIT_WAIT_S)
                raise EngineFailure(f"worker stopped while processing the page; {self.describe_failure()}")
            if message.get("id") == job_id:
                return message
            log.warning("ignoring a worker message for another job: %.200s", message)
        raise EngineFailure(f"no result from the worker after {timeout_s:.0f} s")

    # -- internals -----------------------------------------------------------

    def _child_env(self, extra: dict[str, str]) -> dict[str, str]:
        return {**os.environ, **extra}

    def _vllm_argv(self, serve_args: list[str]) -> list[str]:
        return [
            f"{self._settings.sandbox_dir}/venv-vllm/bin/vllm",
            "serve",
            *serve_args,
            "--host", VLLM_HOST,
            "--port", str(self._settings.vllm_port),
            "--gpu-memory-utilization", f"{self._settings.vllm_gpu_mem:g}",
            "--disable-uvicorn-access-log",
        ]  # fmt: skip

    def _vllm_env(self) -> dict[str, str]:
        return self._child_env(self._spec.vllm_env(self._settings))

    def _start_worker(self) -> None:
        to_worker_read, to_worker_write = os.pipe()
        from_worker_read, from_worker_write = os.pipe()
        try:
            env = self._child_env({PROTOCOL_FDS_ENV: f"{to_worker_read},{from_worker_write}"})
            argv = self._spec.worker_command(self._settings)
            self._worker = ChildProcess("worker", argv, env, pass_fds=(to_worker_read, from_worker_write))
        except BaseException:
            for fd in (to_worker_write, from_worker_read):
                os.close(fd)
            raise
        finally:
            # The worker holds its own copies; ours must go so that EOF reaches us when it dies.
            os.close(to_worker_read)
            os.close(from_worker_write)
        self._channel = Channel(from_worker_read, to_worker_write)
        threading.Thread(target=self._read_messages, args=(self._channel,), name="worker-messages", daemon=True).start()

    def _read_messages(self, channel: Channel) -> None:
        try:
            while (message := channel.receive()) is not None:
                self._messages.put(message)
        except (OSError, ValueError) as exc:
            log.error("invalid message from the worker: %s", exc)
            self._protocol_error = f"invalid message from the worker: {exc}"
        finally:
            self._messages.put(None)

    def _wait_until_ready(self, deadline: float) -> None:
        vllm_ready = self._vllm is None
        worker_ready = False
        while not (vllm_ready and worker_ready):
            if time.monotonic() > deadline:
                pending = [name for name, ready in (("vLLM", vllm_ready), ("worker", worker_ready)) if not ready]
                raise EngineStartError(
                    f"{' and '.join(pending)} not ready after {self._settings.start_timeout_s:.0f} s"
                )
            if not vllm_ready:
                assert self._vllm is not None
                if self._vllm.returncode is not None:
                    raise EngineStartError(self._vllm.describe_exit())
                vllm_ready = self._vllm_healthy()
            if not worker_ready:
                worker_ready = self._poll_worker_ready(wait_s=0.5)
            elif not vllm_ready:
                time.sleep(0.5)

    def _poll_worker_ready(self, wait_s: float) -> bool:
        try:
            message = self._messages.get(timeout=wait_s)
        except queue.Empty:
            return False
        if message is None:  # the worker closed its pipe: it is exiting
            assert self._worker is not None
            self._worker.wait(WORKER_EXIT_WAIT_S)
            raise EngineStartError(self._worker.describe_exit())
        if message.get("event") == "fatal":
            raise EngineStartError(
                f"worker failed to load the engine: {escape_unprintable(str(message.get('detail')))}"
            )
        if message.get("event") == "ready":
            return True
        log.warning("ignoring an unexpected worker message during startup: %.200s", message)
        return False

    def _vllm_healthy(self) -> bool:
        url = f"http://{VLLM_HOST}:{self._settings.vllm_port}/health"
        # No proxy: the server is on the sandbox's own loopback interface.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(url, timeout=2) as response:
                status: int = response.status
                return status == 200
        except (urllib.error.URLError, OSError):
            return False
