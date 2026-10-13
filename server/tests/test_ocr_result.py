"""Validation of sandbox responses (ocr_result.py), using the fake engine's payloads."""

from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image
from support import CORRUPT_PNGS

from scanmylib.devtools.fake_ocr import canned_page, evil_page
from scanmylib.ocr_result import MAX_BLOCK_CONTENT, MAX_BLOCKS_TEXT, MAX_IMAGES, OcrResultError, build_page_output

KEY = "20261012-201530_1a2b3c4d"


def test_canned_page_is_stored_with_renamed_reencoded_images():
    output = build_page_output(canned_page(1200, 1042, "req-1"), KEY)
    assert f'src="../images/{KEY}_1.jpg"' in output.markdown
    assert "imgs/" not in output.markdown
    assert [image.filename for image in output.images] == [f"{KEY}_1.jpg"]
    assert Image.open(io.BytesIO(output.images[0].data)).format == "JPEG"
    assert output.detected_numbers == ("42",)
    assert output.engine == "FakeOCR"
    assert output.duration_s == pytest.approx(0.01)
    raw = output.raw
    assert raw["request_id"] == "req-1" and raw["width"] == 1200 and raw["height"] == 1042
    assert raw["images"] == [{"name": "img_in_image_box_120_340_980_900.png", "file": f"images/{KEY}_1.jpg"}]
    assert {block["label"] for block in raw["blocks"]} >= {"number", "header", "text"}
    assert "data_b64" not in repr(raw)


def test_spread_and_roman_numbers_are_reported():
    assert build_page_output(canned_page(1201, 1042, None), KEY).detected_numbers == ("42", "43")
    assert build_page_output(canned_page(1202, 1012, None), KEY).detected_numbers == ("xii",)


def test_number_in_running_header_is_used_as_fallback():
    assert build_page_output(canned_page(1203, 1057, None), KEY).detected_numbers == ("57",)


def test_numbers_come_from_number_blocks_when_page_numbers_is_absent():
    response = canned_page(1200, 1042, None)
    del response["page_numbers"]
    assert build_page_output(response, KEY).detected_numbers == ("42",)


def test_hostile_response_is_neutralized():
    output = build_page_output(evil_page(1200, 1042, None), KEY)
    markdown = output.markdown
    for forbidden in ("<script", "onerror", "onload", "<iframe", "<svg", "](javascript", "](http", "<!--", "passwd"):
        assert forbidden not in markdown
    assert "Normal text after the traps: café, naïve, résumé." in markdown
    assert [image.filename for image in output.images] == [f"{KEY}_1.jpg"]
    rejected = {entry["name"]: entry["reason"] for entry in output.raw["rejected_images"]}
    assert set(rejected) == {"../../evil.png", "notanimage.png"}
    assert output.engine == "img srchttpsevil.examplep.png"  # no markup, no URL: it goes into document.md


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("PaddleOCR-VL-1.6", "PaddleOCR-VL-1.6"),
        ("<script src=//e.example/x></script>", "script srce.examplexscript"),
        ('a"b\n---\nc', "ab---c"),
        ("<>", "OCR"),  # nothing left: the generic name
    ],
)
def test_engine_names_are_reduced_to_identifiers(model, expected):
    response = canned_page(1200, 1042, None)
    response["engine"] = {"name": None, "model": model}
    assert build_page_output(response, KEY).engine == expected


def test_duplicate_image_names_keep_the_first():
    response = canned_page(1200, 1042, None)
    response["images"].append(dict(response["images"][0]))
    output = build_page_output(response, KEY)
    assert len(output.images) == 1
    assert output.raw["rejected_images"][0]["reason"] == "invalid or duplicate name"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.clear() or r.update({"markdown": None}),
        lambda r: r.update({"images": "not a list"}),
        lambda r: r.update({"blocks": {"label": "x"}}),
        lambda r: r.update({"markdown": "x" * (2 * 1024 * 1024 + 1)}),
        lambda r: r.update({"images": r["images"] * (MAX_IMAGES + 1)}),
    ],
)
def test_malformed_responses_are_refused(mutate):
    response = canned_page(1200, 1042, None)
    mutate(response)
    with pytest.raises(OcrResultError):
        build_page_output(response, KEY)


def test_oversized_block_text_is_refused():
    response = canned_page(1200, 1042, None)
    count = MAX_BLOCKS_TEXT // MAX_BLOCK_CONTENT + 1
    response["blocks"] = [{"label": "text", "content": "Z" * MAX_BLOCK_CONTENT}] * count
    with pytest.raises(OcrResultError):
        build_page_output(response, KEY)


def test_non_object_response_is_refused():
    with pytest.raises(OcrResultError):
        build_page_output(["markdown"], KEY)


def test_invalid_base64_drops_only_that_image():
    response = canned_page(1200, 1042, None)
    response["images"][0]["data_b64"] = "@@not base64@@"
    output = build_page_output(response, KEY)
    assert output.images == ()
    assert "<img" not in output.markdown  # its reference is gone too


@pytest.mark.parametrize("corrupt", CORRUPT_PNGS.values(), ids=CORRUPT_PNGS.keys())
def test_corrupt_illustration_drops_only_that_image(corrupt):
    # Formerly a SyntaxError/ValueError escaped and the whole page failed (and was re-OCRed).
    response = canned_page(1200, 1042, None)
    response["images"][0]["data_b64"] = base64.b64encode(corrupt).decode()
    output = build_page_output(response, KEY)
    assert output.images == () and "<img" not in output.markdown
    assert "The carpenter measures twice" in output.markdown
    assert output.raw["rejected_images"][0]["name"] == response["images"][0]["name"]


def test_untrusted_scalar_fields_are_typed_and_bounded():
    response = canned_page(1200, 1042, None)
    response.update({
        "request_id": "<script>" * 100,
        "width": "1200",
        "engine": {"name": "x" * 500, "model": 42, "backend": "vllm\u202e"},
        "timings": {"infer_s": float("nan"), "load_s": True},
        "blocks": [
            {"label": "text", "content": "y" * 200_000, "bbox": [1, 2, "3", 4], "order": "1"},
            "not a block",
        ],
        "page_numbers": ["  42  ", 7, None, "x" * 100],
    })
    output = build_page_output(response, KEY)
    raw = output.raw
    assert raw["width"] is None
    assert len(raw["engine"]["name"]) == 64 and raw["engine"]["model"] is None
    assert raw["engine"]["backend"] == "vllm"
    assert output.engine == "x" * 64
    assert raw["timings"] == {"queue_s": None, "load_s": None, "infer_s": None}
    assert output.duration_s is None
    assert raw["blocks"] == [{"label": "text", "content": "y" * 65536, "bbox": None, "order": None}]
    assert output.detected_numbers == ("42", "x" * 32)


def test_lone_surrogates_do_not_reach_the_files():
    # Valid in JSON, not in the UTF-8 files: writing ocr/<key>.json used to fail
    # and the page was OCRed four times, then marked as failed.
    response = canned_page(1200, 1042, None)
    response["blocks"][2]["content"] = "text \ud800 read"
    response["page_numbers"] = ["4\udc002"]
    output = build_page_output(response, KEY)
    encoded = json.dumps(output.raw, ensure_ascii=False).encode("utf-8")
    assert "text ? read".encode() in encoded
    assert output.detected_numbers == ("4?2",)


def test_image_payload_size_is_checked_before_decoding():
    response = canned_page(1200, 1042, None)
    response["images"][0]["data_b64"] = base64.b64encode(b"\x00" * 10).decode() * 3_000_000
    output = build_page_output(response, KEY)
    assert output.images == ()
    assert output.raw["rejected_images"][0]["reason"] == "missing or oversized data"
