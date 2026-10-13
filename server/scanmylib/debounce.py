"""Debounced batching: run an action once a burst of changes has settled."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

#: action(keys, index): rewrite the files of `keys`, and the global index if `index`.
BatchAction = Callable[[set[str], bool], Awaitable[None]]

#: Longest wait before work that failed (full disk...) is attempted again.
MAX_RETRY_DELAY_S = 300.0


class DebouncedBatch:
    """Collects keys (document ids) and runs the action after `delay` seconds of calm.

    Under continuous activity the action still runs at least every `max_delay`
    seconds. `flush` runs pending work immediately (e.g. before serving a file).
    The action runs for each key on its own: a key whose action fails stays
    pending and is retried later (with a growing delay), without holding up
    the others.
    """

    def __init__(self, action: BatchAction, delay: float, max_delay: float | None = None) -> None:
        self._action = action
        self._delay = delay
        self._max_delay = max_delay if max_delay is not None else 5 * delay
        self._pending: set[str] = set()
        self._index_pending = False
        self._first_request: float | None = None
        self._deadline = 0.0
        self._failures = 0
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="library-assembly")

    def schedule(self, key: str | None = None) -> None:
        """Mark `key` (and always the index) as needing a rewrite."""
        if key is not None:
            self._pending.add(key)
        self._index_pending = True
        now = asyncio.get_running_loop().time()
        if self._first_request is None:
            self._first_request = now
        self._deadline = min(now + self._delay, self._first_request + self._max_delay)
        self._wake.set()

    async def flush(self, key: str | None = None) -> None:
        """Run pending work now: only `key` (plus the index) if given, else everything."""
        async with self._lock:
            if key is None:
                keys, self._pending = self._pending, set()
                self._first_request = None
            elif key in self._pending:
                self._pending.discard(key)
                keys = {key}
            else:
                keys = set()
            index, self._index_pending = self._index_pending, False
            if not keys and not index:
                return
            failed: set[str] = set()
            for name in sorted(keys):
                if not await self._attempt({name}, False):
                    failed.add(name)
            index_failed = index and not await self._attempt(set(), True)
            if failed or index_failed:
                self._retry_later(failed, index_failed)
            else:
                self._failures = 0

    async def _attempt(self, keys: set[str], index: bool) -> bool:
        try:
            await self._action(keys, index)
        except Exception:
            log.exception("library update failed for %s, will retry", sorted(keys) or "the index")
            return False
        return True

    def _retry_later(self, keys: set[str], index: bool) -> None:
        """Keep failed work pending and run it again after a growing delay (or sooner, with new work)."""
        self._pending |= keys
        self._index_pending = self._index_pending or index
        self._failures += 1
        now = asyncio.get_running_loop().time()
        retry_at = now + min(self._max_delay * 2 ** min(self._failures - 1, 16), MAX_RETRY_DELAY_S)
        # A deadline still ahead belongs to work scheduled meanwhile: keep it if sooner.
        self._deadline = min(self._deadline, retry_at) if self._deadline > now else retry_at
        self._wake.set()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await self._wake.wait()
            while (remaining := self._deadline - loop.time()) > 0:
                await asyncio.sleep(remaining)
            self._wake.clear()
            await self.flush()

    async def aclose(self) -> None:
        """Stop the background task (letting a running batch finish) and flush."""
        if self._task is not None:
            async with self._lock:
                self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush()
