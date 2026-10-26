"""Image handling with Pillow: uploaded scans, thumbnails, OCR input and output.

Only JPEG, PNG and WebP decoders are ever used, with explicit size limits.
Every image this module writes is re-encoded from pixels: no metadata (EXIF,
ICC, comments) and nothing but pixels reaches the disk or the sandbox.
"""

from __future__ import annotations

import io
import warnings
from pathlib import PurePath

from PIL import Image, UnidentifiedImageError

from .application.scan_images import ImageRejected, ImageTooLarge, ScanInfo

MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_UPLOAD_PIXELS = 120_000_000
THUMB_MAX_SIDE = 480

# Limits for images produced by the sandbox (docs/SECURITY.md).
MAX_OCR_IMAGE_BYTES = 20 * 1024 * 1024
MAX_OCR_IMAGE_SIDE = 12_000
MAX_OCR_IMAGE_PIXELS = 40_000_000

_EXIF_ORIENTATION = 0x0112
# EXIF orientation value → transposition that shows the image upright.
_EXIF_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}

_FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
# Pillow reports multi-picture JPEGs (phone photos carrying a depth map or an
# HDR gain map) as "MPO": the file is a JPEG, decoded as its first picture.
_FORMAT_ALIASES = {"MPO": "JPEG"}
SCAN_MEDIA_TYPES = {ext: mime for ext, mime in _FORMATS.values()}

# Pillow's own decompression-bomb guard, as a second line behind the checks below.
Image.MAX_IMAGE_PIXELS = MAX_UPLOAD_PIXELS

# Clockwise rotations requested by the user, as Pillow transpositions.
_TRANSPOSE = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


def _open(source: bytes | PurePath, max_pixels: int, max_side: int | None = None) -> Image.Image:
    """Open an image with the allowed decoders, checking its size before decoding."""
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(stream, formats=list(_FORMATS))
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ImageTooLarge("image too large") from exc
    except UnidentifiedImageError as exc:
        raise ImageRejected("not a JPEG, PNG or WebP image") from exc
    except Exception as exc:  # corrupt files: OSError, SyntaxError, ValueError...
        raise ImageRejected(f"unreadable image: {exc}") from exc
    width, height = image.size
    if width < 1 or height < 1:
        raise ImageRejected("empty image")
    if width * height > max_pixels or (max_side is not None and max(width, height) > max_side):
        raise ImageTooLarge(f"image too large ({width}×{height})")
    return image


def _decode(image: Image.Image) -> None:
    try:
        image.load()
    except Exception as exc:  # Pillow reports corrupt data with assorted exception types
        raise ImageRejected(f"corrupt image: {exc}") from exc


def _exif_orientation(image: Image.Image) -> int | None:
    """EXIF orientation of a decoded image; an unreadable EXIF block counts as none."""
    try:
        orientation = image.getexif().get(_EXIF_ORIENTATION)
    except Exception:  # noqa: BLE001 (broken metadata raises assorted types: the pixels are still good)
        return None
    return orientation if isinstance(orientation, int) else None


def _oriented(image: Image.Image, rotation: int) -> Image.Image:
    """Apply the EXIF orientation, then the user's clockwise rotation."""
    orientation = _exif_orientation(image)
    if orientation is not None and (upright := _EXIF_TRANSPOSE.get(orientation)) is not None:
        image = image.transpose(upright)
    if rotation in _TRANSPOSE:
        image = image.transpose(_TRANSPOSE[rotation])
    return image


def _rgb(image: Image.Image) -> Image.Image:
    """RGB pixels; transparency is flattened on white."""
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode == "I;16":
        image = image.point(lambda value: value / 256).convert("L")
    return image.convert("RGB") if image.mode != "RGB" else image


def _jpeg(image: Image.Image, quality: int) -> bytes:
    image.info = {}  # never carry metadata over
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality, exif=b"")
    return buffer.getvalue()


def _thumbnail(image: Image.Image, rotation: int) -> bytes:
    image.draft("RGB", (THUMB_MAX_SIDE * 2, THUMB_MAX_SIDE * 2))  # fast JPEG downscale
    _decode(image)
    thumb = _rgb(_oriented(image, rotation))
    thumb.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE), Image.Resampling.LANCZOS)
    return _jpeg(thumb, quality=80)


def ingest_scan(data: bytes) -> tuple[ScanInfo, bytes]:
    """Validate an uploaded scan; return its info and its thumbnail (JPEG)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageTooLarge("file larger than 40 MiB")
    with _open(data, MAX_UPLOAD_PIXELS) as image:
        kind = image.format or ""
        ext = _FORMATS[_FORMAT_ALIASES.get(kind, kind)][0]
        width, height = image.size
        # Decodes the image (corrupt files are rejected here) before its EXIF
        # block is read: for PNG, reading EXIF would decode the image unchecked.
        thumbnail = _thumbnail(image, rotation=0)
        if _exif_orientation(image) in (5, 6, 7, 8):  # turned by 90° or 270°
            width, height = height, width
    return ScanInfo(ext=ext, width=width, height=height), thumbnail


def make_thumbnail(scan: PurePath, rotation: int) -> bytes:
    with _open(scan, MAX_UPLOAD_PIXELS) as image:
        return _thumbnail(image, rotation)


def prepare_for_ocr(scan: PurePath, rotation: int, max_side: int) -> bytes:
    """The image sent to the sandbox: oriented, rotated, downscaled, metadata-free JPEG."""
    with _open(scan, MAX_UPLOAD_PIXELS) as image:
        _decode(image)
        prepared = _rgb(_oriented(image, rotation))
        if max(prepared.size) > max_side:
            prepared.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return _jpeg(prepared, quality=92)


def reencode_ocr_image(data: bytes) -> bytes:
    """Re-encode an illustration returned by the sandbox (untrusted) as a clean JPEG."""
    if len(data) > MAX_OCR_IMAGE_BYTES:
        raise ImageTooLarge("illustration larger than 20 MiB")
    with _open(data, MAX_OCR_IMAGE_PIXELS, MAX_OCR_IMAGE_SIDE) as image:
        _decode(image)
        return _jpeg(_rgb(image), quality=90)


class PillowImages:
    def ingest_scan(self, encoded_scan: bytes) -> tuple[ScanInfo, bytes]:
        return ingest_scan(encoded_scan)

    def make_thumbnail(self, scan: PurePath, rotation_degrees: int) -> bytes:
        return make_thumbnail(scan, rotation_degrees)

    def prepare_for_ocr(self, scan: PurePath, rotation_degrees: int, max_side_pixels: int) -> bytes:
        return prepare_for_ocr(scan, rotation_degrees, max_side_pixels)
