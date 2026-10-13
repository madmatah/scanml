"""OCR engines, selected by name with ``OCR_ENGINE``.

To add an engine, write a module exposing ``SPEC`` (an ``EngineSpec``) and
register it below; see ``base.py`` for the contract and ``paddleocr_vl.py``
for an example.
"""

from __future__ import annotations

import importlib

from .base import EngineSpec

_ENGINE_MODULES = {
    "paddleocr-vl": "scanmylib_ocr.engines.paddleocr_vl",
}


def get_spec(name: str) -> EngineSpec:
    """Return the spec of the engine called ``name``."""
    try:
        module_name = _ENGINE_MODULES[name]
    except KeyError:
        known = ", ".join(sorted(_ENGINE_MODULES))
        raise ValueError(f"unknown OCR_ENGINE {name!r} (available: {known})") from None
    return importlib.import_module(module_name).SPEC
