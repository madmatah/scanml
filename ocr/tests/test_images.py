"""Tests of the worker-side image helpers. They need Pillow, i.e. the worker's venv:

    docker run --rm --network none -v "$PWD/ocr:/app:ro" -v "$SANDBOX_DIR:/opt/sandbox:ro" \
        scanmylib-ocr:latest /opt/sandbox/venv-paddle/bin/python -m unittest discover -s /app/tests
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from unittest import mock

HAS_PILLOW = importlib.util.find_spec("PIL") is not None

if HAS_PILLOW:
    from PIL import Image

    from scanmylib_ocr.engines import images
    from scanmylib_ocr.engines.base import PageInputError


@unittest.skipUnless(HAS_PILLOW, "needs Pillow (run with the worker's venv)")
class CollectMarkdownImagesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.crop = Image.new("RGB", (8, 8), "white")

    def test_keeps_the_images_shown_in_reading_order(self) -> None:
        markdown = 'intro <img src="imgs/b.jpg" alt="Image" /> then ![fig](imgs/a.jpg)'
        crops = {"imgs/a.jpg": self.crop, "imgs/b.jpg": self.crop, "imgs/header_ornament.jpg": self.crop}
        result, found = images.collect_markdown_images(markdown, crops)
        self.assertEqual(result, markdown)
        self.assertEqual([image["name"] for image in found], ["b.jpg", "a.jpg"])
        self.assertTrue(all(image["mime"] == "image/jpeg" and image["data_b64"] for image in found))

    def test_unsafe_names_are_replaced_everywhere(self) -> None:
        markdown = '<img src="imgs/../x y.png" /> and again <img src="imgs/../x y.png" />'
        result, found = images.collect_markdown_images(markdown, {"imgs/../x y.png": self.crop})
        self.assertEqual([image["name"] for image in found], ["image_1.jpg"])
        self.assertEqual(result.count('src="imgs/image_1.jpg"'), 2)
        self.assertNotIn("x y", result)

    def test_references_to_missing_images_are_removed(self) -> None:
        markdown = 'text <img src="imgs/gone.jpg" alt="Image" /> and ![x](imgs/gone2.jpg) end'
        result, found = images.collect_markdown_images(markdown, {})
        self.assertEqual(found, [])
        self.assertEqual(result, "text  and  end")


@unittest.skipUnless(HAS_PILLOW, "needs Pillow (run with the worker's venv)")
class LoadPageImageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def path(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def test_garbage_and_unsupported_formats_are_refused(self) -> None:
        with open(self.path("garbage.jpg"), "wb") as garbage:
            garbage.write(b"\xff\xd8\xff not really a jpeg")
        Image.new("RGB", (4, 4)).save(self.path("page.gif"))
        for name in ("garbage.jpg", "page.gif"):
            with self.assertRaises(PageInputError):
                images.load_page_image(self.path(name))

    def test_transparency_is_composited_on_white_paper(self) -> None:
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(self.path("transparent.png"))
        page = images.load_page_image(self.path("transparent.png"))
        self.assertEqual(page.mode, "RGB")
        self.assertEqual(page.getpixel((0, 0)), (255, 255, 255))

    def test_huge_pages_are_downscaled(self) -> None:
        Image.new("L", (400, 300), 128).save(self.path("big.jpg"))
        with mock.patch.object(images, "MAX_WORK_PIXELS", 30_000):
            page = images.load_page_image(self.path("big.jpg"))
        self.assertEqual(page.size, (200, 150))

    def test_absurd_sizes_are_refused_before_decoding(self) -> None:
        Image.new("L", (400, 300)).save(self.path("bomb.png"))
        with mock.patch.object(images, "MAX_INPUT_PIXELS", 100_000), self.assertRaisesRegex(PageInputError, "too large"):
            images.load_page_image(self.path("bomb.png"))


if __name__ == "__main__":
    unittest.main()
