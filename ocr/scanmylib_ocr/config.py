"""Runtime settings of the OCR sandbox, read from environment variables.

The supervisor and the pipeline worker both build their settings from the same
environment (the worker inherits the supervisor's), so this module must stay
importable by the image's stdlib-only interpreter.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

BACKENDS = ("vllm", "native")


def _get_float(env: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")
    return value


def _get_int(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    value = _get_float(env, name, default, low, high)
    if value != int(value):
        raise ValueError(f"{name} must be an integer, got {value}")
    return int(value)


@dataclass(frozen=True)
class Settings:
    """Configuration of the sandbox (see docs/OCR_SANDBOX.md for the env vars)."""

    engine: str
    """Engine module to run (``OCR_ENGINE``), e.g. ``paddleocr-vl``."""
    backend: str
    """How the vision-language model runs: ``vllm`` (server) or ``native`` (in the worker)."""
    socket_path: str
    idle_unload_s: float
    vllm_gpu_mem: float
    """Fraction of the GPU memory the vLLM server may use (``--gpu-memory-utilization``)."""
    vllm_port: int
    max_concurrency: int
    """Number of VLM sub-requests (one per layout block) in flight for a page."""
    start_timeout_s: float
    job_timeout_s: float
    sandbox_dir: str
    """Read-only directory with the venvs and model weights."""
    work_dir: str
    """Writable scratch directory for in-flight images (on the /tmp tmpfs)."""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        backend = env.get("OCR_BACKEND", "vllm").strip() or "vllm"
        if backend not in BACKENDS:
            raise ValueError(f"OCR_BACKEND must be one of {', '.join(BACKENDS)}, got {backend!r}")
        return cls(
            engine=env.get("OCR_ENGINE", "paddleocr-vl").strip() or "paddleocr-vl",
            backend=backend,
            socket_path=env.get("OCR_SOCKET", "/run/scanmylib/ocr.sock"),
            idle_unload_s=_get_float(env, "OCR_IDLE_UNLOAD_S", 300.0, 1.0, 7 * 24 * 3600.0),
            vllm_gpu_mem=_get_float(env, "OCR_VLLM_GPU_MEM", 0.15, 0.05, 0.95),
            vllm_port=_get_int(env, "OCR_VLLM_PORT", 8118, 1024, 65535),
            max_concurrency=_get_int(env, "OCR_MAX_CONCURRENCY", 16, 1, 256),
            start_timeout_s=_get_float(env, "OCR_START_TIMEOUT_S", 600.0, 10.0, 3600.0),
            job_timeout_s=_get_float(env, "OCR_JOB_TIMEOUT_S", 600.0, 10.0, 3600.0),
            sandbox_dir=env.get("OCR_SANDBOX_DIR", "/opt/sandbox"),
            work_dir=env.get("OCR_WORK_DIR", "/tmp/scanmylib-ocr"),
        )
