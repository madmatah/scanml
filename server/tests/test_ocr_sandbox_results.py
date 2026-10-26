"""Validation of sandbox responses (adapters/ocr_sandbox/results.py), using the fake engine's payloads."""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Callable

import pytest
from PIL import Image

from scanmylib.adapters.ocr_sandbox.results import (
    MAX_BLOCK_CONTENT,
    MAX_BLOCKS_TEXT,
    MAX_IMAGES,
    build_page_output,
)
from scanmylib.application.ocr_engine import OcrResultError, PageOcrOutput
from scanmylib.devtools.fake_ocr import ParseResponse, canned_page, evil_page
from support import CORRUPT_PNGS

KEY = "20261012-201530_1a2b3c4d"
ILLUSTRATION_NAME = "img_in_image_box_120_340_980_900.png"
PAGE_WITH_A_NUMBER_BLOCK_WIDTH_PIXELS = 1200


def compute_the_height_pixels_of_page(number: int) -> int:
    return 1000 + number


def make_page_42() -> ParseResponse:
    return canned_page(PAGE_WITH_A_NUMBER_BLOCK_WIDTH_PIXELS, compute_the_height_pixels_of_page(42), None)


def make_page_42_with_an_engine_model(model: str) -> ParseResponse:
    response = make_page_42()
    response["engine"] = {"name": None, "model": model}
    return response


class TestTheOcrSandboxResults:
    class TestTheBuildPageOutputFunction:
        class TestWhenTheResponseIsAPageWithAnIllustration:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                return build_page_output(
                    canned_page(PAGE_WITH_A_NUMBER_BLOCK_WIDTH_PIXELS, compute_the_height_pixels_of_page(42), "req-1"),
                    KEY,
                )

            def test_should_point_the_markdown_at_the_illustration_under_its_new_name(
                self, page_output: PageOcrOutput
            ) -> None:
                assert f'src="../images/{KEY}_1.jpg"' in page_output.markdown

            def test_should_leave_no_reference_to_the_engine_s_own_image_folder(
                self, page_output: PageOcrOutput
            ) -> None:
                assert "imgs/" not in page_output.markdown

            def test_should_name_the_illustration_after_the_page(self, page_output: PageOcrOutput) -> None:
                assert [image.filename for image in page_output.images] == [f"{KEY}_1.jpg"]

            def test_should_reencode_the_illustration_as_a_jpeg(self, page_output: PageOcrOutput) -> None:
                assert [Image.open(io.BytesIO(image.data)).format for image in page_output.images] == ["JPEG"]

            def test_should_report_the_page_number(self, page_output: PageOcrOutput) -> None:
                assert page_output.detected_numbers == ("42",)

            def test_should_report_the_model_as_the_engine(self, page_output: PageOcrOutput) -> None:
                assert page_output.engine == "FakeOCR"

            def test_should_report_the_inference_time_as_the_duration(self, page_output: PageOcrOutput) -> None:
                assert page_output.duration_s == pytest.approx(0.01)

            def test_should_keep_the_request_id_and_the_image_size_in_the_raw_result(
                self, page_output: PageOcrOutput
            ) -> None:
                raw = page_output.raw
                assert (raw["request_id"], raw["width"], raw["height"]) == (
                    "req-1",
                    PAGE_WITH_A_NUMBER_BLOCK_WIDTH_PIXELS,
                    compute_the_height_pixels_of_page(42),
                )

            def test_should_map_the_illustration_s_name_to_its_file_in_the_raw_result(
                self, page_output: PageOcrOutput
            ) -> None:
                assert page_output.raw["images"] == [{"name": ILLUSTRATION_NAME, "file": f"images/{KEY}_1.jpg"}]

            def test_should_keep_the_labels_of_the_blocks_in_the_raw_result(self, page_output: PageOcrOutput) -> None:
                assert {block["label"] for block in page_output.raw["blocks"]} >= {"number", "header", "text"}

            def test_should_keep_no_image_data_in_the_raw_result(self, page_output: PageOcrOutput) -> None:
                assert "data_b64" not in repr(page_output.raw)

        class TestWhenThePageIsASpread:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                spread_width_pixels = 1201
                return build_page_output(
                    canned_page(spread_width_pixels, compute_the_height_pixels_of_page(42), None), KEY
                )

            def test_should_report_both_page_numbers(self, page_output: PageOcrOutput) -> None:
                assert page_output.detected_numbers == ("42", "43")

        class TestWhenThePageIsNumberedInRomanNumerals:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                page_in_roman_numerals_width_pixels = 1202
                return build_page_output(
                    canned_page(page_in_roman_numerals_width_pixels, compute_the_height_pixels_of_page(12), None), KEY
                )

            def test_should_report_the_roman_number(self, page_output: PageOcrOutput) -> None:
                assert page_output.detected_numbers == ("xii",)

        class TestWhenTheNumberIsOnlyInTheRunningHeader:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                page_numbered_in_its_running_header_width_pixels = 1203
                return build_page_output(
                    canned_page(
                        page_numbered_in_its_running_header_width_pixels, compute_the_height_pixels_of_page(57), None
                    ),
                    KEY,
                )

            def test_should_report_the_number_of_the_running_header(self, page_output: PageOcrOutput) -> None:
                assert page_output.detected_numbers == ("57",)

        class TestWhenTheResponseHasNoListOfPageNumbers:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                response = make_page_42()
                del response["page_numbers"]
                return build_page_output(response, KEY)

            def test_should_report_the_numbers_of_the_number_blocks(self, page_output: PageOcrOutput) -> None:
                assert page_output.detected_numbers == ("42",)

        class TestWhenTheResponseIsHostile:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                return build_page_output(
                    evil_page(PAGE_WITH_A_NUMBER_BLOCK_WIDTH_PIXELS, compute_the_height_pixels_of_page(42), None), KEY
                )

            def test_should_keep_no_markup_script_link_or_file_path_in_the_markdown(
                self, page_output: PageOcrOutput
            ) -> None:
                forbidden = [
                    "<script",
                    "onerror",
                    "onload",
                    "<iframe",
                    "<svg",
                    "](javascript",
                    "](http",
                    "<!--",
                    "passwd",
                ]
                assert [fragment for fragment in forbidden if fragment in page_output.markdown] == []

            def test_should_keep_the_text_after_the_traps(self, page_output: PageOcrOutput) -> None:
                assert "Normal text after the traps: café, naïve, résumé." in page_output.markdown

            def test_should_keep_only_the_illustration_with_a_safe_name_and_image_data(
                self, page_output: PageOcrOutput
            ) -> None:
                assert [image.filename for image in page_output.images] == [f"{KEY}_1.jpg"]

            def test_should_record_the_other_illustrations_as_rejected(self, page_output: PageOcrOutput) -> None:
                rejected_names = {entry["name"] for entry in page_output.raw["rejected_images"]}
                assert rejected_names == {"../../evil.png", "notanimage.png"}

            def test_should_keep_no_markup_or_url_in_the_engine_name_since_it_goes_into_document_md(
                self, page_output: PageOcrOutput
            ) -> None:
                assert page_output.engine == "img srchttpsevil.examplep.png"

        class TestWhenTheModelNameIsAnIdentifier:
            @pytest.fixture
            def engine(self) -> str:
                return build_page_output(make_page_42_with_an_engine_model("PaddleOCR-VL-1.6"), KEY).engine

            def test_should_report_it_as_it_is(self, engine: str) -> None:
                assert engine == "PaddleOCR-VL-1.6"

        class TestWhenTheModelNameHoldsMarkup:
            @pytest.fixture
            def engine(self) -> str:
                return build_page_output(
                    make_page_42_with_an_engine_model("<script src=//e.example/x></script>"), KEY
                ).engine

            def test_should_keep_only_the_characters_of_an_identifier(self, engine: str) -> None:
                assert engine == "script srce.examplexscript"

        class TestWhenTheModelNameHoldsQuotesAndLineEnds:
            @pytest.fixture
            def engine(self) -> str:
                return build_page_output(make_page_42_with_an_engine_model('a"b\n---\nc'), KEY).engine

            def test_should_keep_only_the_characters_of_an_identifier(self, engine: str) -> None:
                assert engine == "ab---c"

        class TestWhenNothingIsLeftOfTheModelName:
            @pytest.fixture
            def engine(self) -> str:
                return build_page_output(make_page_42_with_an_engine_model("<>"), KEY).engine

            def test_should_report_the_generic_name(self, engine: str) -> None:
                assert engine == "OCR"

        class TestWhenTwoIllustrationsHaveTheSameName:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                response = make_page_42()
                response["images"].append(dict(response["images"][0]))
                return build_page_output(response, KEY)

            def test_should_keep_the_first_one(self, page_output: PageOcrOutput) -> None:
                assert len(page_output.images) == 1

            def test_should_record_the_second_one_as_rejected(self, page_output: PageOcrOutput) -> None:
                reasons = [entry["reason"] for entry in page_output.raw["rejected_images"]]
                assert reasons == ["invalid or duplicate name"]

        class TestWhenTheResponseIsNotAnObject:
            @pytest.fixture
            def build_the_page_output(self) -> Callable[[], object]:
                return lambda: build_page_output(["markdown"], KEY)

            def test_should_refuse_it(self, build_the_page_output: Callable[[], object]) -> None:
                with pytest.raises(OcrResultError, match="response is not a JSON object"):
                    build_the_page_output()

        class TestWhenTheResponseHasNoMarkdown:
            @pytest.fixture
            def build_the_page_output(self) -> Callable[[], object]:
                return lambda: build_page_output({"markdown": None}, KEY)

            def test_should_refuse_it(self, build_the_page_output: Callable[[], object]) -> None:
                with pytest.raises(OcrResultError, match="markdown missing"):
                    build_the_page_output()

        class TestWhenTheMarkdownIsLargerThanTwoMebibytes:
            @pytest.fixture
            def build_the_page_output(self) -> Callable[[], object]:
                response = make_page_42()
                response["markdown"] = "x" * (2 * 1024 * 1024 + 1)
                return lambda: build_page_output(response, KEY)

            def test_should_refuse_it(self, build_the_page_output: Callable[[], object]) -> None:
                with pytest.raises(OcrResultError, match="markdown larger than"):
                    build_the_page_output()

        class TestWhenTheIllustrationsAreNotAList:
            @pytest.fixture
            def build_the_page_output(self) -> Callable[[], object]:
                response = make_page_42()
                response["images"] = "not a list"
                return lambda: build_page_output(response, KEY)

            def test_should_refuse_it(self, build_the_page_output: Callable[[], object]) -> None:
                with pytest.raises(OcrResultError, match="invalid images"):
                    build_the_page_output()

        class TestWhenThereAreTooManyIllustrations:
            @pytest.fixture
            def build_the_page_output(self) -> Callable[[], object]:
                response = make_page_42()
                response["images"] = response["images"] * (MAX_IMAGES + 1)
                return lambda: build_page_output(response, KEY)

            def test_should_refuse_it(self, build_the_page_output: Callable[[], object]) -> None:
                with pytest.raises(OcrResultError, match=f"more than {MAX_IMAGES} images"):
                    build_the_page_output()

        class TestWhenTheBlocksAreNotAList:
            @pytest.fixture
            def build_the_page_output(self) -> Callable[[], object]:
                response = make_page_42()
                response["blocks"] = {"label": "x"}
                return lambda: build_page_output(response, KEY)

            def test_should_refuse_it(self, build_the_page_output: Callable[[], object]) -> None:
                with pytest.raises(OcrResultError, match="invalid blocks"):
                    build_the_page_output()

        class TestWhenTheBlocksHoldMoreTextThanThePageCanKeep:
            @pytest.fixture
            def build_the_page_output(self) -> Callable[[], object]:
                response = make_page_42()
                count = MAX_BLOCKS_TEXT // MAX_BLOCK_CONTENT + 1
                response["blocks"] = [{"label": "text", "content": "Z" * MAX_BLOCK_CONTENT}] * count
                return lambda: build_page_output(response, KEY)

            def test_should_refuse_it(self, build_the_page_output: Callable[[], object]) -> None:
                with pytest.raises(OcrResultError, match="blocks too large"):
                    build_the_page_output()

        class TestWhenAnIllustrationIsNotBase64:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                response = make_page_42()
                response["images"][0]["data_b64"] = "@@not base64@@"
                return build_page_output(response, KEY)

            def test_should_drop_that_illustration(self, page_output: PageOcrOutput) -> None:
                assert page_output.images == ()

            def test_should_drop_its_reference_too(self, page_output: PageOcrOutput) -> None:
                assert "<img" not in page_output.markdown

        class TestWhenAnIllustrationIsACorruptPng:
            text_of_the_page = "The carpenter measures twice"

            @pytest.fixture(params=list(CORRUPT_PNGS.values()), ids=list(CORRUPT_PNGS))
            def page_output(self, request: pytest.FixtureRequest) -> PageOcrOutput:
                response = make_page_42()
                response["images"][0]["data_b64"] = base64.b64encode(request.param).decode()
                return build_page_output(response, KEY)

            def test_should_drop_that_illustration_rather_than_fail_the_whole_page_and_ocr_it_again(
                self, page_output: PageOcrOutput
            ) -> None:
                assert page_output.images == ()

            def test_should_drop_its_reference_too(self, page_output: PageOcrOutput) -> None:
                assert "<img" not in page_output.markdown

            def test_should_keep_the_text(self, page_output: PageOcrOutput) -> None:
                assert self.text_of_the_page in page_output.markdown

            def test_should_record_it_as_rejected(self, page_output: PageOcrOutput) -> None:
                assert [entry["name"] for entry in page_output.raw["rejected_images"]] == [ILLUSTRATION_NAME]

        class TestWhenScalarFieldsHaveTheWrongTypeOrSize:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                response = make_page_42()
                response.update(
                    {
                        "request_id": "<script>" * 100,
                        "width": "1200",
                        "engine": {"name": "x" * 500, "model": 42, "backend": "vllm\u202e"},
                        "timings": {"infer_s": float("nan"), "load_s": True},
                        "blocks": [
                            {"label": "text", "content": "y" * 200_000, "bbox": [1, 2, "3", 4], "order": "1"},
                            "not a block",
                        ],
                        "page_numbers": ["  42  ", 7, None, "x" * 100],
                    }
                )
                return build_page_output(response, KEY)

            def test_should_drop_a_size_that_is_not_an_integer(self, page_output: PageOcrOutput) -> None:
                assert page_output.raw["width"] is None

            def test_should_cut_the_engine_name_to_64_characters(self, page_output: PageOcrOutput) -> None:
                assert page_output.raw["engine"]["name"] == "x" * 64

            def test_should_drop_a_model_name_that_is_not_text(self, page_output: PageOcrOutput) -> None:
                assert page_output.raw["engine"]["model"] is None

            def test_should_strip_invisible_characters_from_the_backend(self, page_output: PageOcrOutput) -> None:
                assert page_output.raw["engine"]["backend"] == "vllm"

            def test_should_report_the_engine_name_when_no_model_name_is_left(self, page_output: PageOcrOutput) -> None:
                assert page_output.engine == "x" * 64

            def test_should_drop_timings_that_are_not_finite_numbers(self, page_output: PageOcrOutput) -> None:
                assert page_output.raw["timings"] == {"queue_s": None, "load_s": None, "infer_s": None}

            def test_should_report_no_duration(self, page_output: PageOcrOutput) -> None:
                assert page_output.duration_s is None

            def test_should_keep_only_the_blocks_with_their_text_cut_and_their_malformed_fields_dropped(
                self, page_output: PageOcrOutput
            ) -> None:
                assert page_output.raw["blocks"] == [
                    {"label": "text", "content": "y" * 65536, "bbox": None, "order": None}
                ]

            def test_should_keep_only_the_page_numbers_that_are_text_trimmed_and_cut_to_32_characters(
                self, page_output: PageOcrOutput
            ) -> None:
                assert page_output.detected_numbers == ("42", "x" * 32)

        class TestWhenTheTextHoldsLoneSurrogates:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                response = make_page_42()
                response["blocks"][2]["content"] = "text \ud800 read"
                response["page_numbers"] = ["4\udc002"]
                return build_page_output(response, KEY)

            def test_should_replace_them_in_the_raw_result_so_that_it_can_be_encoded_in_the_8_bit_unicode_format(
                self, page_output: PageOcrOutput
            ) -> None:
                assert b"text ? read" in json.dumps(page_output.raw, ensure_ascii=False).encode("utf-8")

            def test_should_replace_them_in_the_page_numbers(self, page_output: PageOcrOutput) -> None:
                assert page_output.detected_numbers == ("4?2",)

        class TestWhenTheDataOfAnIllustrationIsOversized:
            @pytest.fixture
            def page_output(self) -> PageOcrOutput:
                response = make_page_42()
                response["images"][0]["data_b64"] = base64.b64encode(b"\x00" * 10).decode() * 3_000_000
                return build_page_output(response, KEY)

            def test_should_drop_that_illustration(self, page_output: PageOcrOutput) -> None:
                assert page_output.images == ()

            def test_should_reject_it_before_decoding_it(self, page_output: PageOcrOutput) -> None:
                reasons = [entry["reason"] for entry in page_output.raw["rejected_images"]]
                assert reasons == ["missing or oversized data"]
