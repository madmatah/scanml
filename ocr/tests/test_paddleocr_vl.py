"""The PaddleOCR-VL engine (ocr/scanmylib_ocr/engines/paddleocr_vl.py): what its check of the engine's environment
imports, against stand-ins for the engine's libraries.

Standard library only, in the sandbox's image: `scripts/check.sh ocr`.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

from scanmylib_ocr.config import Settings
from scanmylib_ocr.engines.paddleocr_vl import PaddleOCRVLEngine

OCR_EXTRA = "ocr"


class DependencyError(Exception):
    pass


def build_module(name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attribute_name, attribute in attributes.items():
        setattr(module, attribute_name, attribute)
    return module


def build_libraries(required_extras: list[str], refused_extra: str | None = None) -> dict[str, object]:
    def require_extra(extra: str) -> None:
        required_extras.append(extra)
        if extra == refused_extra:
            raise DependencyError(f"`{extra}` is not installed")

    deps = build_module("paddlex.utils.deps", require_extra=require_extra)
    utils = build_module("paddlex.utils", deps=deps)
    return {
        "paddleocr": build_module("paddleocr", PaddleOCRVL=object),
        "paddle": build_module("paddle"),
        "numpy": build_module("numpy"),
        "cv2": build_module("cv2"),
        "PIL": build_module("PIL", Image=build_module("PIL.Image"), ImageOps=build_module("PIL.ImageOps")),
        "paddlex": build_module("paddlex", utils=utils),
        "paddlex.utils": utils,
        "paddlex.utils.deps": deps,
    }


class TheImportLibrariesMethodWhenEveryLibraryImports(unittest.TestCase):
    def setUp(self) -> None:
        self.required_extras: list[str] = []
        self.enterContext(mock.patch.dict(sys.modules, build_libraries(self.required_extras)))
        PaddleOCRVLEngine(Settings.from_env({})).import_libraries()

    def test_should_ask_paddlex_for_its_ocr_extra_as_building_the_pipeline_does(self) -> None:
        self.assertEqual(self.required_extras, [OCR_EXTRA])


class TheImportLibrariesMethodWhenOpenCvDoesNotImport(unittest.TestCase):
    def setUp(self) -> None:
        libraries = {**build_libraries([]), "cv2": None}
        self.enterContext(mock.patch.dict(sys.modules, libraries))
        self.import_libraries = PaddleOCRVLEngine(Settings.from_env({})).import_libraries

    def test_should_fail_since_paddlex_needs_opencv_for_every_page(self) -> None:
        self.assertRaisesRegex(ImportError, "cv2", self.import_libraries)


class TheImportLibrariesMethodWhenPaddlexRefusesItsOcrExtra(unittest.TestCase):
    def setUp(self) -> None:
        libraries = build_libraries([], refused_extra=OCR_EXTRA)
        self.enterContext(mock.patch.dict(sys.modules, libraries))
        self.import_libraries = PaddleOCRVLEngine(Settings.from_env({})).import_libraries

    def test_should_fail_since_building_the_pipeline_would_fail_at_the_first_page(self) -> None:
        self.assertRaisesRegex(DependencyError, "`ocr` is not installed", self.import_libraries)


if __name__ == "__main__":
    unittest.main()
