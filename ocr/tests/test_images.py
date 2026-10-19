"""The image helpers of the worker's engines (ocr/scanmylib_ocr/engines/images.py).

They need Pillow, which only the worker's environment holds: the gate skips them, and `CLAUDE.md` > Commands runs them
with the engine's environment.
"""

from __future__ import annotations

import functools
import importlib.util
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest import mock

HAS_PILLOW = importlib.util.find_spec("PIL") is not None
MISSING_PILLOW_REASON = "needs Pillow (run with the worker's environment)"

if HAS_PILLOW:
    from PIL import Image

    from scanmylib_ocr.engines import images
    from scanmylib_ocr.engines.base import PageInputError

CROP_SIZE_PIXELS = (8, 8)
SMALL_PAGE_SIZE_PIXELS = (4, 4)
LARGE_PAGE_SIZE_PIXELS = (400, 300)
JPEG_SIGNATURE = b"\xff\xd8\xff"
WHITE = (255, 255, 255)


def make_page_directory(test: unittest.TestCase) -> Path:
    directory = tempfile.TemporaryDirectory(prefix="scanmylib-pages-")
    test.addCleanup(directory.cleanup)
    return Path(directory.name)


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheCollectMarkdownImagesFunctionWhenTheMarkdownShowsSomeOfTheCrops(unittest.TestCase):
    source_markdown: ClassVar[str] = 'intro <img src="imgs/b.jpg" alt="Image" /> then ![fig](imgs/a.jpg)'
    ornament_name: ClassVar[str] = "header_ornament.jpg"

    def setUp(self) -> None:
        crop = Image.new("RGB", CROP_SIZE_PIXELS, "white")
        crops = {"imgs/a.jpg": crop, "imgs/b.jpg": crop, f"imgs/{self.ornament_name}": crop}
        self.markdown, self.page_images = images.collect_markdown_images(self.source_markdown, crops)

    def test_should_leave_the_markdown_as_it_is(self) -> None:
        self.assertEqual(self.markdown, self.source_markdown)

    def test_should_return_the_images_it_shows_in_reading_order(self) -> None:
        self.assertEqual([page_image["name"] for page_image in self.page_images], ["b.jpg", "a.jpg"])

    def test_should_drop_the_crops_it_does_not_show_such_as_header_ornaments(self) -> None:
        self.assertNotIn(self.ornament_name, [page_image["name"] for page_image in self.page_images])

    def test_should_give_every_image_the_jpeg_media_type(self) -> None:
        images_of_another_type = [
            page_image["name"] for page_image in self.page_images if page_image["mime"] != "image/jpeg"
        ]
        self.assertEqual(len(self.page_images), 2)
        self.assertEqual(images_of_another_type, [])

    def test_should_carry_the_data_of_every_image(self) -> None:
        without_data = [page_image["name"] for page_image in self.page_images if not page_image["data_b64"]]
        self.assertEqual(len(self.page_images), 2)
        self.assertEqual(without_data, [])


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheCollectMarkdownImagesFunctionWhenAnImageNameIsUnsafe(unittest.TestCase):
    unsafe_path: ClassVar[str] = "imgs/../x y.png"

    def setUp(self) -> None:
        crop = Image.new("RGB", CROP_SIZE_PIXELS, "white")
        source_markdown = f'<img src="{self.unsafe_path}" /> and again <img src="{self.unsafe_path}" />'
        self.markdown, self.page_images = images.collect_markdown_images(source_markdown, {self.unsafe_path: crop})

    def test_should_give_the_image_a_safe_name(self) -> None:
        self.assertEqual([page_image["name"] for page_image in self.page_images], ["image_1.jpg"])

    def test_should_point_every_reference_to_the_safe_name(self) -> None:
        self.assertEqual(self.markdown.count('src="imgs/image_1.jpg"'), 2)

    def test_should_leave_no_trace_of_the_unsafe_name(self) -> None:
        self.assertNotIn("x y", self.markdown)


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheCollectMarkdownImagesFunctionWhenTheReferencedImagesAreMissing(unittest.TestCase):
    def setUp(self) -> None:
        source_markdown = 'text <img src="imgs/gone.jpg" alt="Image" /> and ![x](imgs/gone2.jpg) end'
        self.markdown, self.page_images = images.collect_markdown_images(source_markdown, {})

    def test_should_return_no_image(self) -> None:
        self.assertEqual(self.page_images, [])

    def test_should_remove_their_references_so_that_every_image_the_markdown_shows_comes_with_it(self) -> None:
        self.assertEqual(self.markdown, "text  and  end")


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheLoadPageImageFunctionWhenTheFileIsNotAnImage(unittest.TestCase):
    def setUp(self) -> None:
        path = make_page_directory(self) / "garbage.jpg"
        path.write_bytes(JPEG_SIGNATURE + b" not really a jpeg")
        self.load_page_image = functools.partial(images.load_page_image, str(path))

    def test_should_refuse_it(self) -> None:
        self.assertRaisesRegex(PageInputError, "not a decodable JPEG, PNG or WebP image", self.load_page_image)


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheLoadPageImageFunctionWhenTheImageIsInAnUnsupportedFormat(unittest.TestCase):
    def setUp(self) -> None:
        path = make_page_directory(self) / "page.gif"
        Image.new("RGB", SMALL_PAGE_SIZE_PIXELS).save(path)
        self.load_page_image = functools.partial(images.load_page_image, str(path))

    def test_should_refuse_it(self) -> None:
        self.assertRaisesRegex(PageInputError, "not a decodable JPEG, PNG or WebP image", self.load_page_image)


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheLoadPageImageFunctionWhenThePageIsTransparent(unittest.TestCase):
    def setUp(self) -> None:
        path = make_page_directory(self) / "transparent.png"
        transparent = (0, 0, 0, 0)
        Image.new("RGBA", SMALL_PAGE_SIZE_PIXELS, transparent).save(path)
        self.page = images.load_page_image(str(path))

    def test_should_return_it_in_rgb(self) -> None:
        self.assertEqual(self.page.mode, "RGB")

    def test_should_lay_its_transparent_areas_on_white_paper(self) -> None:
        self.assertEqual(self.page.getpixel((0, 0)), WHITE)


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheLoadPageImageFunctionWhenThePageHasMorePixelsThanTheWorkLimit(unittest.TestCase):
    def setUp(self) -> None:
        path = make_page_directory(self) / "big.jpg"
        gray = 128
        Image.new("L", LARGE_PAGE_SIZE_PIXELS, gray).save(path)
        work_limit_pixels = 30_000
        with mock.patch.object(images, "MAX_WORK_PIXELS", work_limit_pixels):
            self.page = images.load_page_image(str(path))

    def test_should_scale_it_down_to_the_limit_keeping_its_proportions(self) -> None:
        half_size_pixels = (200, 150)
        self.assertEqual(self.page.size, half_size_pixels)


@unittest.skipUnless(HAS_PILLOW, MISSING_PILLOW_REASON)
class TheLoadPageImageFunctionWhenThePageHasMorePixelsThanTheInputLimit(unittest.TestCase):
    def setUp(self) -> None:
        path = make_page_directory(self) / "bomb.png"
        Image.new("L", LARGE_PAGE_SIZE_PIXELS).save(path)
        input_limit_pixels = 100_000
        input_limit_patcher = mock.patch.object(images, "MAX_INPUT_PIXELS", input_limit_pixels)
        input_limit_patcher.start()
        self.addCleanup(input_limit_patcher.stop)
        self.load_page_image = functools.partial(images.load_page_image, str(path))

    def test_should_refuse_it_before_decoding_it_so_that_a_decompression_bomb_never_fills_the_memory(self) -> None:
        self.assertRaisesRegex(PageInputError, "image too large: 400x300 pixels", self.load_page_image)


if __name__ == "__main__":
    unittest.main()
