"""Image helpers for worker-side engines (they need Pillow: worker process only)."""

from __future__ import annotations

import base64
import io
import re
from collections.abc import Mapping

from PIL import Image, ImageOps

from .base import PageImage, PageInputError

INPUT_FORMATS = ("JPEG", "PNG", "WEBP")
MAX_INPUT_PIXELS = 250_000_000
"""Larger images are refused outright (decompression-bomb guard)."""
MAX_WORK_PIXELS = 40_000_000
"""Larger images are downscaled before OCR; result coordinates refer to the downscaled size."""
JPEG_QUALITY = 90

_IMAGE_NAME = re.compile(r"[A-Za-z0-9._-]{1,128}\.jpg")
_IMAGE_REFERENCE = re.compile(r'<img\b[^>]*\bsrc="imgs/([^"]*)"[^>]*>|!\[[^\]]*\]\(imgs/([^)\s]*)\)')

Image.MAX_IMAGE_PIXELS = MAX_INPUT_PIXELS


def load_page_image(path: str) -> Image.Image:
    """Decode a JPEG/PNG/WebP page into an upright RGB image of a sane size."""
    try:
        with Image.open(path, formats=INPUT_FORMATS) as image:
            width, height = image.size
            if width * height > MAX_INPUT_PIXELS:
                raise PageInputError(f"image too large: {width}x{height} pixels")
            upright = ImageOps.exif_transpose(image)
            rgb = _flatten_to_rgb(upright)
    except PageInputError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise PageInputError(f"not a decodable JPEG, PNG or WebP image ({exc})") from exc

    pixels = rgb.width * rgb.height
    if pixels > MAX_WORK_PIXELS:
        scale = (MAX_WORK_PIXELS / pixels) ** 0.5
        size = (max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale)))
        rgb = rgb.resize(size, Image.Resampling.LANCZOS)
    return rgb


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    """Convert any mode to RGB, compositing transparent areas on white paper."""
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        paper = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(paper, rgba).convert("RGB")
    return image.convert("RGB")


def encode_jpeg_b64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def collect_markdown_images(markdown: str, images: Mapping[str, Image.Image | None]) -> tuple[str, list[PageImage]]:
    """Return the Markdown and the images it references, in reading order.

    ``images`` maps the paths used in the Markdown (``imgs/<name>``) to crops.
    Crops the Markdown does not show (e.g. header ornaments) are dropped, names
    that are not plain ``<name>.jpg`` basenames are replaced, and references to
    missing images are removed, so that every ``imgs/<name>`` in the returned
    Markdown has exactly one entry in the returned list.
    """
    shown = {path: image for path, image in images.items() if image is not None and path in markdown}
    used = {path.removeprefix("imgs/") for path in shown if _is_valid_path(path)}

    by_name: dict[str, Image.Image] = {}
    for path, image in shown.items():
        if _is_valid_path(path):
            name = path.removeprefix("imgs/")
        else:
            name = _fresh_name(used)
            used.add(name)
            markdown = markdown.replace(path, f"imgs/{name}")
        by_name[name] = image

    def keep_known(match: re.Match[str]) -> str:
        return match.group(0) if (match.group(1) or match.group(2)) in by_name else ""

    markdown = _IMAGE_REFERENCE.sub(keep_known, markdown)
    in_reading_order = sorted(by_name, key=lambda name: markdown.find(f"imgs/{name}"))
    return markdown, [
        {"name": name, "mime": "image/jpeg", "data_b64": encode_jpeg_b64(by_name[name])} for name in in_reading_order
    ]


def _is_valid_path(path: str) -> bool:
    return path.startswith("imgs/") and _IMAGE_NAME.fullmatch(path.removeprefix("imgs/")) is not None


def _fresh_name(used: set[str]) -> str:
    number = 1
    while f"image_{number}.jpg" in used:
        number += 1
    return f"image_{number}.jpg"
