"""Image handling (images.py): uploads, thumbnails, OCR input, sandbox illustrations."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from support import BROKEN_EXIF, CORRUPT_PNGS, encoded, jpeg, mpo, png

from scanmylib import images
from scanmylib.images import ImageRejected, ImageTooLarge


def open_image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def truncated(data: bytes) -> bytes:
    return data[: len(data) // 2]


def test_ingest_scan_reports_format_size_and_thumbnail():
    info, thumbnail = images.ingest_scan(jpeg(2000, 1500))
    assert (info.ext, info.width, info.height) == ("jpg", 2000, 1500)
    thumb = open_image(thumbnail)
    assert thumb.format == "JPEG"
    assert max(thumb.size) == images.THUMB_MAX_SIDE


def test_exif_orientation_is_applied():
    # Stored 1600×1200 with "rotate 90° clockwise" in EXIF: displayed portrait.
    info, thumbnail = images.ingest_scan(jpeg(1600, 1200, orientation=6))
    assert (info.width, info.height) == (1200, 1600)
    width, height = open_image(thumbnail).size
    assert height > width


@pytest.mark.parametrize(
    ("data", "ext"),
    [
        (png(300, 200), "png"),
        (encoded(Image.new("RGBA", (300, 200), (0, 0, 0, 0)), "PNG"), "png"),
        (encoded(Image.new("RGB", (300, 200)), "WEBP"), "webp"),
        (encoded(Image.new("L", (300, 200)), "JPEG"), "jpg"),
        (encoded(Image.new("CMYK", (300, 200)), "JPEG"), "jpg"),
        (png(300, 200, mode="I;16"), "png"),
    ],
)
def test_supported_formats_and_modes(data, ext):
    info, thumbnail = images.ingest_scan(data)
    assert info.ext == ext
    assert open_image(thumbnail).mode == "RGB"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image at all",
        encoded(Image.new("RGB", (50, 50)), "GIF"),
        encoded(Image.new("RGB", (50, 50)), "BMP"),
        encoded(Image.new("RGB", (50, 50)), "TIFF"),
        b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
        truncated(jpeg(800, 600)),
        *(pytest.param(data, id=name) for name, data in CORRUPT_PNGS.items()),
    ],
)
def test_other_files_are_rejected(data):
    with pytest.raises(ImageRejected):
        images.ingest_scan(data)


def test_multi_picture_jpegs_are_accepted_as_jpeg(tmp_path):
    # Phone photos carrying a depth map or an HDR gain map: Pillow names them "MPO".
    data = mpo(640, 480)
    assert open_image(data).format == "MPO"
    info, thumbnail = images.ingest_scan(data)
    assert (info.ext, info.width, info.height) == ("jpg", 640, 480)
    assert images.SCAN_MEDIA_TYPES[info.ext] == "image/jpeg"
    assert open_image(thumbnail).size == (480, 360)
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(data)
    assert open_image(images.prepare_for_ocr(scan, 0, max_side=4096)).size == (640, 480)


@pytest.mark.parametrize(
    "data",
    [
        # JFIF density in dpi: Pillow does not read the EXIF block when opening the file.
        encoded(Image.new("RGB", (300, 200), "white"), "JPEG", dpi=(300, 300), exif=BROKEN_EXIF),
        encoded(Image.new("RGB", (300, 200), "white"), "WEBP", exif=BROKEN_EXIF),
        encoded(Image.new("RGB", (300, 200), "white"), "PNG", exif=BROKEN_EXIF),
    ],
    ids=["jpeg", "webp", "png"],
)
def test_unreadable_exif_is_ignored(data, tmp_path):
    info, thumbnail = images.ingest_scan(data)
    assert (info.width, info.height) == (300, 200)
    assert open_image(thumbnail).size == (300, 200)
    scan = tmp_path / f"scan.{info.ext}"
    scan.write_bytes(data)
    assert open_image(images.make_thumbnail(scan, 90)).size == (200, 300)
    assert open_image(images.prepare_for_ocr(scan, 0, max_side=4096)).size == (300, 200)


def test_decompression_bombs_are_rejected_before_decoding():
    bomb = png(11_000, 11_000, mode="1")  # a few KB on disk, 121 million pixels
    assert len(bomb) < 100_000
    with pytest.raises(ImageTooLarge):
        images.ingest_scan(bomb)


def test_prepare_for_ocr_rotates_clockwise_and_strips_metadata(tmp_path):
    source = Image.new("RGB", (300, 200), "white")
    source.paste((255, 0, 0), (0, 0, 20, 20))  # red square in the top-left corner
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(encoded(source, "JPEG", quality=100, exif=exif.tobytes(), comment=b"secret", icc_profile=b"x" * 64))

    prepared = open_image(images.prepare_for_ocr(scan, 90, max_side=4096))
    assert prepared.size == (200, 300)
    red, green, _ = prepared.getpixel((190, 10))  # top-left went to the top-right corner
    assert red > 200 and green < 80
    assert dict(prepared.getexif()) == {}
    assert not {"icc_profile", "comment", "exif"} & set(prepared.info)


def test_prepare_for_ocr_downscales_large_scans(tmp_path):
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(jpeg(5000, 3000))
    assert open_image(images.prepare_for_ocr(scan, 0, max_side=1000)).size == (1000, 600)


def test_thumbnail_follows_the_rotation(tmp_path):
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(jpeg(1000, 500))
    assert open_image(images.make_thumbnail(scan, 270)).size == (240, 480)


def test_sandbox_illustrations_are_reencoded_as_plain_jpeg():
    data = encoded(Image.new("RGBA", (64, 48), (10, 20, 30, 128)), "PNG")
    output = open_image(images.reencode_ocr_image(data))
    assert output.format == "JPEG" and output.mode == "RGB" and output.size == (64, 48)


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (png(12_001, 10), ImageTooLarge),
        (png(7000, 7000, mode="1"), ImageTooLarge),  # 49 Mpx > 40 Mpx
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, ImageRejected),
        (b"<html><script>alert(1)</script></html>", ImageRejected),
        (b"x" * (images.MAX_OCR_IMAGE_BYTES + 1), ImageTooLarge),
        *(pytest.param(data, ImageRejected, id=name) for name, data in CORRUPT_PNGS.items()),
    ],
)
def test_bad_sandbox_illustrations_are_rejected(data, error):
    with pytest.raises(error):
        images.reencode_ocr_image(data)
