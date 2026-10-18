"""Engine lifecycle and the FIFO page queue.

A single dispatcher thread owns the engine: it starts it lazily for the first
page (or on ``/v1/load``), feeds it one page at a time in arrival order, and
stops it after ``OCR_IDLE_UNLOAD_S`` without work so that no VRAM is held
while idle. HTTP threads only enqueue work and read a snapshot of the state,
so ``/health`` never waits for a page.
"""

from __future__ import annotations

import collections
import enum
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, assert_never

from .config import Settings
from .engines.base import EngineSpec
from .protocol import BAD_IMAGE, ENGINE_UNAVAILABLE, PROCESSING_FAILED
from .runtime import EngineFailure, EngineRuntime

log = logging.getLogger(__name__)

LIVENESS_CHECK_INTERVAL_S = 5.0


class State(enum.Enum):
    IDLE = "idle"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    ERROR = "error"


class Runtime(Protocol):
    """What the manager needs from a loaded engine (``EngineRuntime`` in production)."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def interrupt(self) -> None: ...
    def alive(self) -> bool: ...
    def describe_failure(self) -> str: ...
    def parse(self, job_id: str, image_path: str, options: dict[str, Any], timeout_s: float) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Reply:
    status: int
    body: dict[str, Any]


def error_reply(status: int, code: str, detail: str) -> Reply:
    return Reply(status, {"error": code, "detail": detail})


class ParseJob:
    """One page waiting for (or going through) the engine."""

    def __init__(self, request_id: str, image: bytes, extension: str, options: dict[str, Any]) -> None:
        self.request_id = request_id
        self.image = image
        self.extension = extension
        self.options = options
        self.job_id = uuid.uuid4().hex
        self.enqueued_at = time.monotonic()
        self._done = threading.Event()
        self._reply: Reply | None = None

    def finish(self, reply: Reply) -> None:
        """Deliver the reply to the waiting HTTP thread; later calls are ignored."""
        if self._done.is_set():
            return
        self._reply = reply
        self.image = b""
        self._done.set()

    def wait(self) -> Reply:
        self._done.wait()
        assert self._reply is not None
        return self._reply


@dataclass(frozen=True)
class _Unloading:
    waiters: list[threading.Event]


@dataclass(frozen=True)
class _Parsing:
    job: ParseJob


@dataclass(frozen=True)
class _Loading:
    pass


@dataclass(frozen=True)
class _IdleTimeout:
    pass


@dataclass(frozen=True)
class _EngineLoss:
    pass


@dataclass(frozen=True)
class _Closing:
    pass


_Action = _Unloading | _Parsing | _Loading | _IdleTimeout | _EngineLoss


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class EngineManager:
    def __init__(
        self,
        settings: Settings,
        spec: EngineSpec,
        runtime_factory: Callable[[], Runtime] | None = None,
    ) -> None:
        self._settings = settings
        self._spec = spec
        self._runtime_factory = runtime_factory or (lambda: EngineRuntime(settings, spec))
        self._cond = threading.Condition()
        # Everything below is guarded by self._cond.
        self._jobs: collections.deque[ParseJob] = collections.deque()
        self._load_requested = False
        self._unload_waiters: list[threading.Event] = []
        self._closing = False
        self._runtime: Runtime | None = None
        self._state = State.IDLE
        self._since = _utc_now()
        self._state_changed_at = time.monotonic()
        self._last_error: str | None = None
        self._busy = False
        self._processed = 0
        self._last_activity = time.monotonic()
        self._thread = threading.Thread(target=self._dispatch_forever, name="engine-dispatcher", daemon=True)

    # -- called from HTTP threads -----------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def submit(self, job: ParseJob) -> None:
        with self._cond:
            if self._closing:
                job.finish(error_reply(503, ENGINE_UNAVAILABLE, "the OCR sandbox is shutting down"))
                return
            self._jobs.append(job)
            self._cond.notify_all()

    def request_load(self) -> str:
        """Start the engine in the background unless it runs; return the resulting state."""
        with self._cond:
            if self._state is State.READY:
                return State.READY.value
            self._load_requested = True
            self._cond.notify_all()
            return State.STARTING.value

    def request_unload(self) -> None:
        """Stop the engine (after the page in progress, if any) and wait until it is stopped."""
        stopped = threading.Event()
        with self._cond:
            if self._closing:
                return
            self._unload_waiters.append(stopped)
            self._cond.notify_all()
        stopped.wait()

    def snapshot(self) -> dict[str, Any]:
        with self._cond:
            return {
                "state": self._state.value,
                "since": self._since,
                "state_changed_at": self._state_changed_at,  # monotonic clock
                "last_error": self._last_error,
                "busy": self._busy,
                "queue": len(self._jobs),
                "processed": self._processed,
            }

    def shutdown(self, timeout_s: float) -> None:
        """Stop the engine, answer every pending page with 503 and end the dispatcher."""
        with self._cond:
            self._closing = True
            runtime = self._runtime
            self._cond.notify_all()
        if runtime is not None:
            runtime.interrupt()
        self._thread.join(timeout_s)

    # -- dispatcher thread ----------------------------------------------------------

    def _dispatch_forever(self) -> None:
        while True:
            action = self._next_action()
            if isinstance(action, _Closing):
                self._close()
                return
            try:
                self._perform(action)
            except Exception:
                # Never let the only dispatcher thread die: every page would wait forever.
                log.exception("unexpected error in the engine dispatcher (%s)", type(action).__name__)
                if isinstance(action, _Parsing):
                    action.job.finish(error_reply(500, PROCESSING_FAILED, "internal error in the OCR supervisor"))
                time.sleep(1.0)

    def _perform(self, action: _Action) -> None:
        match action:
            case _Unloading(waiters):
                try:
                    self._stop_engine()
                finally:
                    for waiter in waiters:
                        waiter.set()
            case _Parsing(job):
                try:
                    self._process(job)
                finally:
                    with self._cond:
                        self._busy = False
                        self._last_activity = time.monotonic()
            case _Loading():
                self._ensure_engine()
            case _IdleTimeout():
                log.info("no page for %.0f s: unloading the engine", self._settings.idle_unload_s)
                self._stop_engine()
            case _EngineLoss():
                detail = self._runtime.describe_failure() if self._runtime else "engine stopped"
                log.error("engine stopped unexpectedly: %s", detail)
                self._stop_engine(final_state=State.ERROR, error=f"engine stopped unexpectedly: {detail}")
            case _:
                assert_never(action)

    def _next_action(self) -> _Action | _Closing:
        with self._cond:
            while True:
                if self._closing:
                    return _Closing()
                if self._unload_waiters:
                    waiters, self._unload_waiters = self._unload_waiters, []
                    return _Unloading(waiters)
                if self._jobs:
                    self._busy = True
                    return _Parsing(self._jobs.popleft())
                if self._load_requested:
                    self._load_requested = False
                    return _Loading()
                timeout = None
                if self._runtime is not None:
                    if not self._runtime.alive():
                        return _EngineLoss()
                    idle_for = time.monotonic() - self._last_activity
                    if idle_for >= self._settings.idle_unload_s:
                        return _IdleTimeout()
                    timeout = min(self._settings.idle_unload_s - idle_for, LIVENESS_CHECK_INTERVAL_S)
                self._cond.wait(timeout)

    def _set_state(self, state: State, *, error: str | None = None, clear_error: bool = False) -> None:
        with self._cond:
            if state is not self._state:
                log.info("engine state: %s -> %s", self._state.value, state.value)
                self._state = state
                self._since = _utc_now()
                self._state_changed_at = time.monotonic()
            if error is not None:
                self._last_error = error
            elif clear_error:
                self._last_error = None

    def _ensure_engine(self) -> bool:
        """Start the engine unless it is running. On failure, fail every waiting page."""
        if self._runtime is not None and self._runtime.alive():
            return True
        if self._runtime is not None:
            self._stop_engine(error=f"engine stopped unexpectedly: {self._runtime.describe_failure()}")

        self._set_state(State.STARTING)
        started = time.monotonic()
        runtime = self._runtime_factory()
        with self._cond:
            self._runtime = runtime  # visible to shutdown(), which may interrupt the start
        try:
            runtime.start()
        except Exception as exc:  # noqa: BLE001 (any failed start fails the waiting pages, not the dispatcher)
            with self._cond:
                self._runtime = None
                closing = self._closing
                waiting = list(self._jobs)
                self._jobs.clear()
            reason = "the OCR sandbox is shutting down" if closing else f"engine failed to start: {exc}"
            log.error("%s", reason)
            self._set_state(State.ERROR, error=reason)
            for job in waiting:
                job.finish(error_reply(503, ENGINE_UNAVAILABLE, reason))
            return False
        with self._cond:
            self._last_activity = time.monotonic()
        log.info("engine ready in %.1f s", time.monotonic() - started)
        self._set_state(State.READY, clear_error=True)
        return True

    def _stop_engine(self, *, final_state: State = State.IDLE, error: str | None = None) -> None:
        runtime = self._runtime
        if runtime is None:
            if final_state is not State.IDLE or error is not None:
                self._set_state(final_state, error=error)
            return
        self._set_state(State.STOPPING)
        started = time.monotonic()
        try:
            runtime.stop()
        finally:
            with self._cond:
                self._runtime = None
            self._set_state(final_state, error=error)
        log.info("engine stopped in %.1f s", time.monotonic() - started)

    def _process(self, job: ParseJob) -> None:
        dispatched = time.monotonic()
        queue_s = dispatched - job.enqueued_at
        if not self._ensure_engine():
            job.finish(error_reply(503, ENGINE_UNAVAILABLE, self._last_error or "engine failed to start"))
            return
        load_s = time.monotonic() - dispatched
        assert self._runtime is not None

        image_path = os.path.join(self._settings.work_dir, f"{job.job_id}.{job.extension}")
        try:
            with open(image_path, "wb") as image_file:
                image_file.write(job.image)
            message = self._runtime.parse(job.job_id, image_path, job.options, timeout_s=self._settings.job_timeout_s)
        except EngineFailure as exc:
            with self._cond:
                closing = self._closing
            if closing:
                job.finish(error_reply(503, ENGINE_UNAVAILABLE, "the OCR sandbox is shutting down"))
            else:
                log.error("request %s failed: %s", job.request_id, exc)
                job.finish(error_reply(500, PROCESSING_FAILED, str(exc)))
            # A crashed or hung engine is torn down; the next page starts a fresh one.
            self._stop_engine(error=f"engine failed while processing a page: {exc}")
            return
        finally:
            try:
                os.unlink(image_path)
            except FileNotFoundError:
                pass

        if message.get("ok"):
            infer_s = float(message.get("infer_s", 0.0))
            body = {
                "request_id": job.request_id,
                **message["result"],
                "engine": self._spec.describe(self._settings),
                "timings": {"queue_s": round(queue_s, 3), "load_s": round(load_s, 3), "infer_s": round(infer_s, 3)},
            }
            with self._cond:
                self._processed += 1
            log.info(
                "request %s done: %d blocks, %d images, queue %.1f s, load %.1f s, infer %.1f s",
                job.request_id, len(body.get("blocks", [])), len(body.get("images", [])), queue_s, load_s, infer_s,
            )  # fmt: skip
            job.finish(Reply(200, body))
        else:
            code = message.get("error") or PROCESSING_FAILED
            detail = str(message.get("detail") or "")
            log.warning("request %s failed: %s: %s", job.request_id, code, detail)
            job.finish(error_reply(400 if code == BAD_IMAGE else 500, code, detail))

    def _close(self) -> None:
        self._stop_engine()
        with self._cond:
            jobs, self._jobs = list(self._jobs), collections.deque()
            waiters, self._unload_waiters = self._unload_waiters, []
        for job in jobs:
            job.finish(error_reply(503, ENGINE_UNAVAILABLE, "the OCR sandbox is shutting down"))
        for waiter in waiters:
            waiter.set()
