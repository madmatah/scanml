"""QR codes as SVG (pairing URI, APK download link)."""

from __future__ import annotations

import io

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.image.svg import SvgPathImage


def qr_svg(data: str) -> bytes:
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=10, border=4, image_factory=SvgPathImage)
    code.add_data(data)
    code.make(fit=True)
    buffer = io.BytesIO()
    code.make_image().save(buffer)
    return buffer.getvalue()
