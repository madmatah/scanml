"""GPU memory readings for ``/health``, taken with nvidia-smi."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

QUERY = ["--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"]


def query_gpu(timeout_s: float = 5.0) -> dict[str, Any] | None:
    """First GPU's name and memory use (whole device, all processes), or ``None``."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        completed = subprocess.run([executable, *QUERY], capture_output=True, text=True, timeout=timeout_s, check=True)
        name, used, total = (field.strip() for field in completed.stdout.splitlines()[0].split(","))
        return {"name": name, "memory_used_mb": int(used), "memory_total_mb": int(total)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        log.debug("nvidia-smi query failed: %s", exc)
        return None


class GpuMonitor:
    """Recent GPU reading for frequent pollers, without making each of them wait for nvidia-smi.

    A reading younger than ``max_age_s`` is returned as is; an older one is
    returned while a background refresh starts; after a long pause
    (``sync_after_s``), or when the reading predates a known change of the GPU
    usage (the engine started or stopped), it is taken on the spot (tens of
    milliseconds).
    """

    def __init__(self, max_age_s: float = 5.0, sync_after_s: float = 30.0) -> None:
        self._max_age_s = max_age_s
        self._sync_after_s = sync_after_s
        self._lock = threading.Lock()
        self._reading: dict[str, Any] | None = None
        self._taken_at = float("-inf")
        self._refreshing = False

    def refresh(self) -> None:
        """Take a reading now (blocking)."""
        reading = query_gpu()
        with self._lock:
            self._reading = reading
            self._taken_at = time.monotonic()
            self._refreshing = False

    def current(self, changed_at: float = float("-inf")) -> dict[str, Any] | None:
        """Return a recent reading; ``changed_at`` (monotonic) is the last known change of GPU usage."""
        with self._lock:
            age = time.monotonic() - self._taken_at
            if self._taken_at >= changed_at:
                if age <= self._max_age_s or self._refreshing:
                    return self._reading
                if age <= self._sync_after_s:
                    self._refreshing = True
                    threading.Thread(target=self.refresh, name="gpu-refresh", daemon=True).start()
                    return self._reading
        self.refresh()
        with self._lock:
            return self._reading
