"""Image handling (images.py): uploads, thumbnails, OCR input, sandbox illustrations."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, cast

import pytest
from PIL import Image

from scanmylib import images
from scanmylib.images import ImageRejected, ImageTooLarge, ScanInfo
from support import BROKEN_EXIF, CORRUPT_PNGS, encoded, jpeg, mpo, png

NOT_A_JPEG_PNG_OR_WEBP_IMAGE = "not a JPEG, PNG or WebP image"
CORRUPT_IMAGE = "(unreadable|corrupt) image"


class IngestedScan(NamedTuple):
    scan_info: ScanInfo
    thumbnail: Image.Image


class ScanFile(NamedTuple):
    image_bytes: bytes
    extension: str


SCANS_WITH_AN_UNREADABLE_EXIF_BLOCK = {
    # JFIF density in dpi: Pillow does not read the EXIF block when opening the file.
    "jpeg": ScanFile(encoded(Image.new("RGB", (300, 200), "white"), "JPEG", dpi=(300, 300), exif=BROKEN_EXIF), "jpg"),
    "webp": ScanFile(encoded(Image.new("RGB", (300, 200), "white"), "WEBP", exif=BROKEN_EXIF), "webp"),
    "png": ScanFile(encoded(Image.new("RGB", (300, 200), "white"), "PNG", exif=BROKEN_EXIF), "png"),
}


def open_image(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes))


def truncate(image_bytes: bytes) -> bytes:
    return image_bytes[: len(image_bytes) // 2]


def ingest(image_bytes: bytes) -> IngestedScan:
    scan_info, thumbnail = images.ingest_scan(image_bytes)
    return IngestedScan(scan_info=scan_info, thumbnail=open_image(thumbnail))


def write_scan(folder: Path, scan: ScanFile) -> Path:
    path = folder / f"scan.{scan.extension}"
    path.write_bytes(scan.image_bytes)
    return path


class TestTheImages:
    class TestTheIngestScanFunction:
        class TestWhenTheScanIsALargeJpeg:
            @pytest.fixture
            def ingested_scan(self) -> IngestedScan:
                return ingest(jpeg(2000, 1500))

            def test_should_report_its_format_and_its_size(self, ingested_scan: IngestedScan) -> None:
                scan_info = ingested_scan.scan_info
                assert (scan_info.ext, scan_info.width, scan_info.height) == ("jpg", 2000, 1500)

            def test_should_make_a_jpeg_thumbnail(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.thumbnail.format == "JPEG"

            def test_should_bring_the_longest_side_of_the_thumbnail_down_to_its_limit(
                self, ingested_scan: IngestedScan
            ) -> None:
                assert max(ingested_scan.thumbnail.size) == images.THUMB_MAX_SIDE

        class TestWhenTheExifOrientationOfTheScanTurnsItAQuarterTurn:
            @pytest.fixture
            def ingested_scan(self) -> IngestedScan:
                rotate_90_degrees_clockwise = 6
                return ingest(jpeg(1600, 1200, orientation=rotate_90_degrees_clockwise))

            def test_should_report_the_size_it_is_shown_at(self, ingested_scan: IngestedScan) -> None:
                assert (ingested_scan.scan_info.width, ingested_scan.scan_info.height) == (1200, 1600)

            def test_should_make_a_portrait_thumbnail(self, ingested_scan: IngestedScan) -> None:
                width, height = ingested_scan.thumbnail.size
                assert height > width

        class TestWhenTheScanIsAPng:
            @pytest.fixture(
                params=[
                    png(300, 200),
                    encoded(Image.new("RGBA", (300, 200), (0, 0, 0, 0)), "PNG"),
                    png(300, 200, mode="I;16"),
                ],
                ids=["red green blue", "transparent", "16-bit grayscale"],
            )
            def ingested_scan(self, request: pytest.FixtureRequest) -> IngestedScan:
                return ingest(request.param)

            def test_should_report_the_png_extension(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.scan_info.ext == "png"

            def test_should_make_a_red_green_blue_thumbnail(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.thumbnail.mode == "RGB"

        class TestWhenTheScanIsAWebp:
            @pytest.fixture
            def ingested_scan(self) -> IngestedScan:
                return ingest(encoded(Image.new("RGB", (300, 200)), "WEBP"))

            def test_should_report_the_webp_extension(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.scan_info.ext == "webp"

            def test_should_make_a_red_green_blue_thumbnail(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.thumbnail.mode == "RGB"

        class TestWhenTheScanIsAJpegInAnotherColorMode:
            @pytest.fixture(
                params=[encoded(Image.new("L", (300, 200)), "JPEG"), encoded(Image.new("CMYK", (300, 200)), "JPEG")],
                ids=["grayscale", "cyan magenta yellow black"],
            )
            def ingested_scan(self, request: pytest.FixtureRequest) -> IngestedScan:
                return ingest(request.param)

            def test_should_report_the_jpeg_extension(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.scan_info.ext == "jpg"

            def test_should_make_a_red_green_blue_thumbnail(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.thumbnail.mode == "RGB"

        class TestWhenTheScanIsAMultiPictureJpeg:
            @pytest.fixture
            def ingested_scan(self) -> IngestedScan:
                phone_photo_with_a_depth_map = mpo(640, 480)
                return ingest(phone_photo_with_a_depth_map)

            def test_should_report_a_jpeg_of_the_size_of_its_first_picture(self, ingested_scan: IngestedScan) -> None:
                scan_info = ingested_scan.scan_info
                assert (scan_info.ext, scan_info.width, scan_info.height) == ("jpg", 640, 480)

            def test_should_be_served_as_a_jpeg(self, ingested_scan: IngestedScan) -> None:
                assert images.SCAN_MEDIA_TYPES[ingested_scan.scan_info.ext] == "image/jpeg"

            def test_should_make_a_thumbnail_of_its_first_picture(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.thumbnail.size == (480, 360)

        class TestWhenTheExifBlockOfTheScanIsUnreadable:
            @pytest.fixture(
                params=list(SCANS_WITH_AN_UNREADABLE_EXIF_BLOCK.values()), ids=list(SCANS_WITH_AN_UNREADABLE_EXIF_BLOCK)
            )
            def ingested_scan(self, request: pytest.FixtureRequest) -> IngestedScan:
                scan: ScanFile = request.param
                return ingest(scan.image_bytes)

            def test_should_report_the_size_of_its_pixels(self, ingested_scan: IngestedScan) -> None:
                assert (ingested_scan.scan_info.width, ingested_scan.scan_info.height) == (300, 200)

            def test_should_make_a_thumbnail_of_its_pixels_as_they_are(self, ingested_scan: IngestedScan) -> None:
                assert ingested_scan.thumbnail.size == (300, 200)

        class TestWhenTheFileIsNotAJpegPngOrWebpImage:
            @pytest.fixture(
                params=[
                    b"",
                    b"not an image at all",
                    encoded(Image.new("RGB", (50, 50)), "GIF"),
                    encoded(Image.new("RGB", (50, 50)), "BMP"),
                    encoded(Image.new("RGB", (50, 50)), "TIFF"),
                    b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
                ],
                ids=[
                    "an empty file",
                    "text",
                    "a graphics interchange format image",
                    "a bitmap image",
                    "a tagged image file format image",
                    "a scalable vector graphics image with a script",
                ],
            )
            def ingest_the_file(self, request: pytest.FixtureRequest) -> Callable[[], object]:
                image_bytes: bytes = request.param
                return lambda: images.ingest_scan(image_bytes)

            def test_should_reject_it(self, ingest_the_file: Callable[[], object]) -> None:
                with pytest.raises(ImageRejected, match=NOT_A_JPEG_PNG_OR_WEBP_IMAGE):
                    ingest_the_file()

        class TestWhenTheImageIsCorrupt:
            @pytest.fixture(
                params=[truncate(jpeg(800, 600)), *CORRUPT_PNGS.values()],
                ids=["a truncated jpeg", *(f"a png with {name}" for name in CORRUPT_PNGS)],
            )
            def ingest_the_file(self, request: pytest.FixtureRequest) -> Callable[[], object]:
                image_bytes: bytes = request.param
                return lambda: images.ingest_scan(image_bytes)

            def test_should_reject_it(self, ingest_the_file: Callable[[], object]) -> None:
                with pytest.raises(ImageRejected, match=CORRUPT_IMAGE):
                    ingest_the_file()

        class TestWhenTheImageIsADecompressionBomb:
            @pytest.fixture
            def ingest_the_file(self) -> Callable[[], object]:
                bomb_of_121_million_pixels_in_a_few_kilobytes = png(11_000, 11_000, mode="1")
                return lambda: images.ingest_scan(bomb_of_121_million_pixels_in_a_few_kilobytes)

            def test_should_reject_it_before_decoding_it(self, ingest_the_file: Callable[[], object]) -> None:
                with pytest.raises(ImageTooLarge, match="image too large"):
                    ingest_the_file()

    class TestTheMakeThumbnailFunction:
        class TestWhenTheUserTurnedTheScanThreeQuarterTurns:
            @pytest.fixture
            def thumbnail(self, tmp_path: Path) -> Image.Image:
                scan = write_scan(tmp_path, ScanFile(jpeg(1000, 500), "jpg"))
                return open_image(images.make_thumbnail(scan, 270))

            def test_should_turn_the_thumbnail_too(self, thumbnail: Image.Image) -> None:
                assert thumbnail.size == (240, 480)

        class TestWhenTheExifBlockOfTheScanIsUnreadable:
            @pytest.fixture(
                params=list(SCANS_WITH_AN_UNREADABLE_EXIF_BLOCK.values()), ids=list(SCANS_WITH_AN_UNREADABLE_EXIF_BLOCK)
            )
            def thumbnail(self, request: pytest.FixtureRequest, tmp_path: Path) -> Image.Image:
                return open_image(images.make_thumbnail(write_scan(tmp_path, request.param), 90))

            def test_should_turn_its_pixels_as_the_user_asked(self, thumbnail: Image.Image) -> None:
                assert thumbnail.size == (200, 300)

    class TestThePrepareForOcrFunction:
        class TestWhenTheUserTurnedAScanWithMetadataAQuarterTurnClockwise:
            @pytest.fixture
            def prepared_image(self, tmp_path: Path) -> Image.Image:
                source = Image.new("RGB", (300, 200), "white")
                red = (255, 0, 0)
                square_in_the_top_left_corner = (0, 0, 20, 20)
                source.paste(red, square_in_the_top_left_corner)
                exif = Image.Exif()
                exif[0x010F] = "PhoneMaker"
                with_metadata = encoded(
                    source, "JPEG", quality=100, exif=exif.tobytes(), comment=b"secret", icc_profile=b"x" * 64
                )
                scan = write_scan(tmp_path, ScanFile(with_metadata, "jpg"))
                return open_image(images.prepare_for_ocr(scan, 90, max_side=4096))

            def test_should_turn_its_size(self, prepared_image: Image.Image) -> None:
                assert prepared_image.size == (200, 300)

            def test_should_turn_its_top_left_corner_to_the_top_right(self, prepared_image: Image.Image) -> None:
                red, green, _ = cast(tuple[int, int, int], prepared_image.getpixel((190, 10)))
                assert red > 200 and green < 80

            def test_should_strip_its_exif_block(self, prepared_image: Image.Image) -> None:
                assert dict(prepared_image.getexif()) == {}

            def test_should_strip_its_color_profile_and_its_comment(self, prepared_image: Image.Image) -> None:
                assert not {"icc_profile", "comment", "exif"} & set(prepared_image.info)

        class TestWhenTheScanIsLargerThanTheLimit:
            @pytest.fixture
            def prepared_image(self, tmp_path: Path) -> Image.Image:
                scan = write_scan(tmp_path, ScanFile(jpeg(5000, 3000), "jpg"))
                return open_image(images.prepare_for_ocr(scan, 0, max_side=1000))

            def test_should_scale_it_down_to_the_limit(self, prepared_image: Image.Image) -> None:
                assert prepared_image.size == (1000, 600)

        class TestWhenTheScanIsAMultiPictureJpeg:
            @pytest.fixture
            def prepared_image(self, tmp_path: Path) -> Image.Image:
                scan = write_scan(tmp_path, ScanFile(mpo(640, 480), "jpg"))
                return open_image(images.prepare_for_ocr(scan, 0, max_side=4096))

            def test_should_send_its_first_picture(self, prepared_image: Image.Image) -> None:
                assert prepared_image.size == (640, 480)

        class TestWhenTheExifBlockOfTheScanIsUnreadable:
            @pytest.fixture(
                params=list(SCANS_WITH_AN_UNREADABLE_EXIF_BLOCK.values()), ids=list(SCANS_WITH_AN_UNREADABLE_EXIF_BLOCK)
            )
            def prepared_image(self, request: pytest.FixtureRequest, tmp_path: Path) -> Image.Image:
                return open_image(images.prepare_for_ocr(write_scan(tmp_path, request.param), 0, max_side=4096))

            def test_should_send_its_pixels_as_they_are(self, prepared_image: Image.Image) -> None:
                assert prepared_image.size == (300, 200)

    class TestTheReencodeOcrImageFunction:
        class TestWhenTheIllustrationIsATransparentPng:
            @pytest.fixture
            def illustration(self) -> Image.Image:
                return open_image(
                    images.reencode_ocr_image(encoded(Image.new("RGBA", (64, 48), (10, 20, 30, 128)), "PNG"))
                )

            def test_should_reencode_it_as_a_plain_red_green_blue_jpeg(self, illustration: Image.Image) -> None:
                assert (illustration.format, illustration.mode) == ("JPEG", "RGB")

            def test_should_keep_its_size(self, illustration: Image.Image) -> None:
                assert illustration.size == (64, 48)

        class TestWhenTheIllustrationExceedsTheSizeLimits:
            @pytest.fixture(
                params=[png(12_001, 10), png(7000, 7000, mode="1")],
                ids=["wider than 12000 pixels", "of 49 million pixels, over 40"],
            )
            def reencode_the_illustration(self, request: pytest.FixtureRequest) -> Callable[[], object]:
                image_bytes: bytes = request.param
                return lambda: images.reencode_ocr_image(image_bytes)

            def test_should_reject_it(self, reencode_the_illustration: Callable[[], object]) -> None:
                with pytest.raises(ImageTooLarge, match="image too large"):
                    reencode_the_illustration()

        class TestWhenTheIllustrationIsLargerThanTwentyMebibytes:
            @pytest.fixture
            def reencode_the_illustration(self) -> Callable[[], object]:
                oversized = b"x" * (images.MAX_OCR_IMAGE_BYTES + 1)
                return lambda: images.reencode_ocr_image(oversized)

            def test_should_reject_it_before_reading_it(self, reencode_the_illustration: Callable[[], object]) -> None:
                with pytest.raises(ImageTooLarge, match="illustration larger than 20 MiB"):
                    reencode_the_illustration()

        class TestWhenTheIllustrationIsNotAJpegPngOrWebpImage:
            @pytest.fixture(
                params=[b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, b"<html><script>alert(1)</script></html>"],
                ids=["a png signature alone", "html"],
            )
            def reencode_the_illustration(self, request: pytest.FixtureRequest) -> Callable[[], object]:
                image_bytes: bytes = request.param
                return lambda: images.reencode_ocr_image(image_bytes)

            def test_should_reject_it(self, reencode_the_illustration: Callable[[], object]) -> None:
                with pytest.raises(ImageRejected, match=NOT_A_JPEG_PNG_OR_WEBP_IMAGE):
                    reencode_the_illustration()

        class TestWhenTheIllustrationIsCorrupt:
            @pytest.fixture(params=list(CORRUPT_PNGS.values()), ids=[f"a png with {name}" for name in CORRUPT_PNGS])
            def reencode_the_illustration(self, request: pytest.FixtureRequest) -> Callable[[], object]:
                image_bytes: bytes = request.param
                return lambda: images.reencode_ocr_image(image_bytes)

            def test_should_reject_it(self, reencode_the_illustration: Callable[[], object]) -> None:
                with pytest.raises(ImageRejected, match=CORRUPT_IMAGE):
                    reencode_the_illustration()
