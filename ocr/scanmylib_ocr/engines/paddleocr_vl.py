"""PaddleOCR-VL 1.6: PP-DocLayoutV3 layout analysis + PaddleOCR-VL-1.6 (0.9B) recognition.

The layout model finds the blocks of a page and their reading order; each text,
table or formula block is then read by the vision-language model, served by
vLLM inside the sandbox (``OCR_BACKEND=vllm``) or run by Paddle directly in the
worker (``OCR_BACKEND=native``, slower). Optional pre-processing: page
orientation (PP-LCNet_x1_0_doc_ori) and unwarping of curved pages (UVDoc).

Only ``PaddleOCRVLEngine`` touches PaddleOCR, and only inside its methods:
this module is also imported by the stdlib-only supervisor for ``SPEC``.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .base import EngineSpec, PageBlock, PageEngine, PageOptions, PageResult

if TYPE_CHECKING:
    from ..config import Settings

PIPELINE_VERSION = "v1.6"
SERVED_MODEL_NAME = "PaddleOCR-VL-1.6"
PADDLEX_MODEL_NAME = "PaddleOCR-VL-1.6-0.9B"
LAYOUT_MODEL = "PP-DocLayoutV3"
ORIENTATION_MODEL = "PP-LCNet_x1_0_doc_ori"
UNWARPING_MODEL = "UVDoc"
MAX_MODEL_LEN = 16384
"""Longest sequence vLLM must hold: a block image (<= ~2k tokens) plus up to 4096
generated tokens fits easily. The model's default (131072) would force vLLM to
reserve far more GPU memory for its KV cache than OCR ever uses."""
MARKDOWN_IGNORE_LABELS = ["number", "header", "header_image", "footer", "footer_image"]
"""Page furniture left out of the Markdown (still reported in ``blocks``, where
``number`` drives page ordering). PaddleOCR's default also drops ``footnote``
and ``aside_text``; footnotes and sidebars carry real content in technical
books, so they are kept."""

_BLANK_LINES = re.compile(r"\n[ \t]*(?:\n[ \t]*){2,}")

log = logging.getLogger(__name__)


def _model_dir(settings: Settings) -> str:
    return f"{settings.sandbox_dir}/models/{SERVED_MODEL_NAME}"


def _paddlex_model_dir(settings: Settings, name: str) -> str:
    return f"{settings.sandbox_dir}/paddlex/official_models/{name}"


class PaddleOCRVLSpec(EngineSpec):
    name = "paddleocr-vl"
    model = SERVED_MODEL_NAME
    backends = ("vllm", "native")

    def worker_command(self, settings: Settings) -> list[str]:
        return [f"{settings.sandbox_dir}/venv-paddle/bin/python", "-m", "scanmylib_ocr.worker"]

    def vllm_serve_args(self, settings: Settings) -> list[str] | None:
        if settings.backend != "vllm":
            return None
        # Flags of the official recipe (recipes.vllm.ai/PaddlePaddle/PaddleOCR-VL-1.6), plus:
        # - --trust-request-mm-kwargs: PaddleOCR sends per-block min/max pixel bounds,
        #   which vLLM refuses unless told to trust its clients. The only client is
        #   the worker, over the sandbox's private loopback interface.
        # - --max-model-len: see MAX_MODEL_LEN.
        return [
            _model_dir(settings),
            "--served-model-name", SERVED_MODEL_NAME,
            "--trust-remote-code",
            "--max-num-batched-tokens", "16384",
            "--no-enable-prefix-caching",
            "--mm-processor-cache-gb", "0",
            "--trust-request-mm-kwargs",
            "--max-model-len", str(MAX_MODEL_LEN),
        ]  # fmt: skip

    def vllm_env(self, settings: Settings) -> dict[str, str]:
        # FlashInfer's sampler is compiled just-in-time with nvcc, which the
        # sandbox does not ship; PyTorch's sampler is as fast for greedy OCR.
        return {"VLLM_USE_FLASHINFER_SAMPLER": "0"}

    def describe(self, settings: Settings) -> dict[str, Any]:
        return {
            "name": self.name,
            "pipeline_version": PIPELINE_VERSION,
            "model": SERVED_MODEL_NAME,
            "backend": settings.backend,
        }

    def create_engine(self, settings: Settings) -> PageEngine:
        return PaddleOCRVLEngine(settings)


class PaddleOCRVLEngine(PageEngine):
    """Worker-side wrapper around ``paddleocr.PaddleOCRVL``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pipeline: Any = None

    def load(self) -> None:
        from paddleocr import PaddleOCRVL

        settings = self._settings
        options: dict[str, Any] = {
            "pipeline_version": PIPELINE_VERSION,
            "layout_detection_model_name": LAYOUT_MODEL,
            "layout_detection_model_dir": _paddlex_model_dir(settings, LAYOUT_MODEL),
            "doc_orientation_classify_model_name": ORIENTATION_MODEL,
            "doc_orientation_classify_model_dir": _paddlex_model_dir(settings, ORIENTATION_MODEL),
            "doc_unwarping_model_name": UNWARPING_MODEL,
            "doc_unwarping_model_dir": _paddlex_model_dir(settings, UNWARPING_MODEL),
            # Load both pre-processing models; each page turns them on or off.
            "use_doc_orientation_classify": True,
            "use_doc_unwarping": True,
            "markdown_ignore_labels": MARKDOWN_IGNORE_LABELS,
            "device": "gpu:0",
        }
        if settings.backend == "vllm":
            options.update(
                vl_rec_backend="vllm-server",
                vl_rec_server_url=f"http://127.0.0.1:{settings.vllm_port}/v1",
                vl_rec_api_model_name=SERVED_MODEL_NAME,
                vl_rec_max_concurrency=settings.max_concurrency,
            )
        else:
            options.update(
                vl_rec_backend="native",
                vl_rec_model_name=PADDLEX_MODEL_NAME,
                vl_rec_model_dir=_model_dir(settings),
            )
        self._pipeline = PaddleOCRVL(**options)
        self._warm_up()

    def _warm_up(self) -> None:
        """Run the CNN models once on a blank page.

        The first inference pays for CUDA/cuDNN initialization (several
        seconds); doing it here, while vLLM is still starting, takes that off
        the first real page. A blank page has no blocks, so the vision-language
        model is not called.
        """
        import numpy as np

        blank = np.full((1400, 1000, 3), 255, dtype=np.uint8)
        try:
            self._pipeline.predict(blank, use_doc_orientation_classify=True, use_doc_unwarping=True)
        except Exception:
            log.warning("warm-up failed (the first page will be slower)", exc_info=True)

    def parse(self, image_path: str, options: PageOptions) -> PageResult:
        import numpy as np

        from .images import collect_markdown_images, load_page_image

        image = load_page_image(image_path)
        bgr = np.ascontiguousarray(np.asarray(image)[:, :, ::-1])
        (result,) = self._pipeline.predict(
            bgr,
            use_doc_orientation_classify=options.orientation,
            use_doc_unwarping=options.unwarp,
            use_chart_recognition=options.charts,
        )
        data = result.json["res"]
        rendered = result.markdown
        markdown, images = collect_markdown_images(rendered["markdown_texts"], rendered["markdown_images"])
        # Blocks merged into the previous one (a paragraph continued in the next
        # column) leave empty entries behind, rendered as runs of blank lines.
        markdown = _BLANK_LINES.sub("\n\n", markdown).strip()
        markdown = markdown + "\n" if markdown else ""

        blocks: list[PageBlock] = [
            {
                "label": str(block["block_label"]),
                "content": str(block["block_content"] or ""),
                "bbox": [int(v) for v in block["block_bbox"]],
                "order": None if block.get("block_order") is None else int(block["block_order"]),
            }
            for block in data["parsing_res_list"]
        ]
        preprocess = data.get("doc_preprocessor_res") or {}
        angle = preprocess.get("angle")
        return {
            "width": int(data["width"]),
            "height": int(data["height"]),
            "markdown": markdown,
            "images": images,
            "blocks": blocks,
            "page_numbers": [b["content"].strip() for b in blocks if b["label"] == "number" and b["content"].strip()],
            # PaddleOCR-VL does not tell whether a paragraph runs over a page break.
            "page_continuation": None,
            "preprocess": {
                "angle": int(angle) if angle in (90, 180, 270) else 0,
                "unwarped": bool(preprocess.get("model_settings", {}).get("use_doc_unwarping", False)),
            },
        }

    def close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.close()
            self._pipeline = None


SPEC = PaddleOCRVLSpec()
