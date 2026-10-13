"""Interfaces of an OCR engine.

An engine lives in one module of this package and has two halves:

* ``EngineSpec`` (supervisor side, stdlib only): how to start the worker (with
  which venv), how to serve the model with vLLM, and how results are labeled.
* ``PageEngine`` (worker side): loads the pipeline and turns one page image
  into the result fields of ``POST /v1/parse``. Its heavy imports (Paddle,
  numpy, Pillow...) must happen inside its methods, never at module level,
  because the supervisor imports the same module to read the spec.
"""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from ..config import Settings


@dataclass(frozen=True)
class PageOptions:
    """Per-page processing switches (query parameters of ``POST /v1/parse``)."""

    orientation: bool = True
    """Detect pages photographed at 90/180/270 degrees and rotate them upright."""
    unwarp: bool = False
    """Flatten curved or warped pages before layout analysis."""
    charts: bool = False
    """Convert charts to tables instead of keeping them as images."""

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageOptions:
        return cls(**{name: bool(data[name]) for name in ("orientation", "unwarp", "charts") if name in data})


class PageImage(TypedDict):
    name: str
    mime: str
    data_b64: str


class PageBlock(TypedDict):
    label: str
    content: str
    bbox: list[int]
    order: int | None


class PageResult(TypedDict):
    """What a worker-side engine returns for one page (see docs/OCR_SANDBOX.md)."""

    width: int
    height: int
    markdown: str
    images: list[PageImage]
    blocks: list[PageBlock]
    page_numbers: list[str]
    page_continuation: dict[str, bool] | None
    preprocess: dict[str, Any]


class PageInputError(ValueError):
    """The submitted image cannot be decoded or is unreasonable (HTTP 400 ``bad_image``)."""


class PageEngine(abc.ABC):
    """Worker-side engine. One instance per worker process, used for one page at a time."""

    @abc.abstractmethod
    def load(self) -> None:
        """Load models (the vLLM server, if any, may still be starting)."""

    @abc.abstractmethod
    def parse(self, image_path: str, options: PageOptions) -> PageResult:
        """OCR one page. Raise ``PageInputError`` for an undecodable image."""

    def close(self) -> None:
        """Release resources before the worker exits."""


class EngineSpec(abc.ABC):
    """Supervisor-side description of an engine."""

    name: str
    """Value of ``OCR_ENGINE`` selecting this engine."""
    model: str
    """Model name reported in results."""
    backends: tuple[str, ...] = ("vllm",)
    """Values of ``OCR_BACKEND`` this engine supports."""

    @abc.abstractmethod
    def worker_command(self, settings: Settings) -> list[str]:
        """Command starting the worker, normally ``<venv python> -m scanmylib_ocr.worker``."""

    def vllm_serve_args(self, settings: Settings) -> list[str] | None:
        """Model-specific ``vllm serve`` arguments, or ``None`` when no server is needed.

        The runtime adds the listening address and ``--gpu-memory-utilization``.
        """
        return None

    def vllm_env(self, settings: Settings) -> dict[str, str]:
        """Extra environment variables for the vLLM server."""
        return {}

    @abc.abstractmethod
    def describe(self, settings: Settings) -> dict[str, Any]:
        """The ``engine`` object of parse results."""

    @abc.abstractmethod
    def create_engine(self, settings: Settings) -> PageEngine:
        """Build the worker-side engine (called in the worker process only)."""
