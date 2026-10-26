"""A rotation turns the scan clockwise, in degrees. Every image the ports return is a JPEG. A scan they cannot take
raises ImageRejected, or ImageTooLarge past a size limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import Protocol


class ImageRejected(ValueError):
    """The bytes are not an acceptable image."""


class ImageTooLarge(ImageRejected):
    """The image is acceptable in kind but exceeds a size limit."""


@dataclass(frozen=True)
class ScanInfo:
    """An accepted upload: file extension and displayed size (EXIF orientation applied)."""

    ext: str
    width: int
    height: int


class ScanImages(Protocol):
    def ingest_scan(self, encoded_scan: bytes) -> tuple[ScanInfo, bytes]: ...

    def make_thumbnail(self, scan: PurePath, rotation_degrees: int) -> bytes: ...


class OcrImages(Protocol):
    def prepare_for_ocr(self, scan: PurePath, rotation_degrees: int, max_side_pixels: int) -> bytes: ...
