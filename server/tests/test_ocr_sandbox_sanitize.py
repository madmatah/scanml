"""The sanitizer of untrusted OCR Markdown (adapters/ocr_sandbox/sanitize.py)."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import NamedTuple, override

import pytest
from markdown_it import MarkdownIt

from hostile_markup import (
    HOSTILE_PAYLOAD_COUNT,
    PAGE_IMAGES,
    generate_hostile_payloads,
    parse_markup,
    sanitize_page,
)
from scanmylib.adapters.ocr_sandbox import sanitize
from scanmylib.adapters.ocr_sandbox.sanitize import MarkdownTooLarge, is_safe_image_name

TAGS_SANITIZED_MARKDOWN_MAY_HOLD = frozenset(
    {
        "p",
        "br",
        "hr",
        "div",
        "span",
        "center",
        "b",
        "strong",
        "i",
        "em",
        "u",
        "s",
        "strike",
        "del",
        "ins",
        "sub",
        "sup",
        "small",
        "mark",
        "code",
        "pre",
        "kbd",
        "samp",
        "var",
        "blockquote",
        "q",
        "cite",
        "abbr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "colgroup",
        "col",
        "img",
        "figure",
        "figcaption",
    }
)
ATTRIBUTES_SANITIZED_MARKDOWN_MAY_KEEP = frozenset(
    {
        "src",
        "alt",
        "width",
        "height",
        "colspan",
        "rowspan",
        "valign",
        "span",
        "border",
        "start",
        "align",
        "style",
    }
)
SERIALIZED_TAG = re.compile(r'</?([a-z0-9]+)(?: [a-z]+="[^"<>]*")*(?: /)?>')
TEXT_ALIGNMENT = re.compile(r"text-align: (left|right|center|justify);")


class AnyLinkMarkdownIt(MarkdownIt):
    @override
    def validateLink(self, url: str) -> bool:
        return True


def find_markup_that_is_no_serialized_tag(markdown: str) -> list[str]:
    findings = []
    for match in re.finditer(r"<(?=[A-Za-z/!?])", markdown):
        serialized_tag = SERIALIZED_TAG.match(markdown, match.start())
        if not serialized_tag or serialized_tag[1] not in TAGS_SANITIZED_MARKDOWN_MAY_HOLD:
            findings.append(f"unexpected markup at {markdown[match.start() : match.start() + 40]!r}")
    return findings


def find_links_to_anything_but_page_images(markdown: str) -> list[str]:
    rendered_with_every_link = parse_markup(AnyLinkMarkdownIt("commonmark").render(markdown))
    return [
        f"{attribute_name} of {tag}: {attribute_value}"
        for tag, attributes in rendered_with_every_link.tags
        for attribute_name, attribute_value in attributes
        if attribute_name in ("href", "src") and attribute_value not in PAGE_IMAGES.values()
    ]


def find_unsafe_markdown(markdown: str) -> list[str]:
    findings = find_markup_that_is_no_serialized_tag(markdown)
    collected_markup = parse_markup(markdown)
    findings += collected_markup.non_tag_markup
    for tag, attributes in collected_markup.tags:
        if tag not in TAGS_SANITIZED_MARKDOWN_MAY_HOLD:
            findings.append(f"tag {tag}")
        for attribute_name, attribute_value in attributes:
            if attribute_name.startswith("on") or attribute_name not in ATTRIBUTES_SANITIZED_MARKDOWN_MAY_KEEP:
                findings.append(f"attribute {attribute_name} of {tag}")
            if attribute_name == "src" and attribute_value not in PAGE_IMAGES.values():
                findings.append(f"image {attribute_value}")
            if attribute_name == "style" and not (
                attribute_value is not None and TEXT_ALIGNMENT.fullmatch(attribute_value)
            ):
                findings.append(f"style {attribute_value}")
    return findings + find_links_to_anything_but_page_images(markdown)


class Cleaned(NamedTuple):
    markdown: str
    expected_markdown: str


class TimedCleaning(NamedTuple):
    markdown: str
    elapsed_seconds: float


class ImageTargets(NamedTuple):
    html_image: str
    markdown_image: str


class SanitizedPayload(NamedTuple):
    payload: str
    markdown: str


class TestTheOcrSandboxSanitizer:
    class TestTheSanitizeMarkdownFunction:
        class TestWhenTheTextHoldsAScriptLikeElement:
            @pytest.fixture(
                params=[
                    "a<script>alert(1)</script>b",
                    "a<SCRIPT type='text/javascript'>alert(1)</SCRIPT >b",
                    "a<style>body{background:url(javascript:alert(1))}</style>b",
                    "a<iframe src='https://evil.example'>x</iframe>b",
                    "a<svg onload=alert(1)><script>alert(2)</script></svg>b",
                    "a<math><mi xlink:href='javascript:alert(1)'>x</mi></math>b",
                    "a<object data='evil.swf'>x</object>b",
                    "a<template><img src=x onerror=alert(1)></template>b",
                    "a<textarea><img src=x onerror=alert(1)></textarea>b",
                    "a<noscript><img src=x onerror=alert(1)></noscript>b",
                ],
                ids=[
                    "script",
                    "script in capitals",
                    "style",
                    "iframe",
                    "svg",
                    "math",
                    "object",
                    "template",
                    "textarea",
                    "noscript",
                ],
            )
            def markdown(self, request: pytest.FixtureRequest) -> str:
                return sanitize_page(request.param)

            def test_should_drop_it_with_its_content(self, markdown: str) -> None:
                assert markdown == "ab"

        class TestWhenAScriptIsNeverClosed:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("before<script>alert(1) and the rest")

            def test_should_drop_everything_after_it(self, markdown: str) -> None:
                assert markdown == "before"

        class TestWhenTheTextHoldsAFormOrADocumentLevelTag:
            @pytest.fixture(
                params=[
                    "<embed src='evil.swf'>",
                    "<link rel=stylesheet href='https://evil.example/x.css'>",
                    "<meta http-equiv=refresh content='0;url=javascript:alert(1)'>",
                    "<base href='https://evil.example/'>",
                    "<form action='https://evil.example'><input name=q><button>Send</button></form>",
                    "<select><option>1</option></select>",
                ],
                ids=["embed", "link", "meta", "base", "form", "select"],
            )
            def markdown(self, request: pytest.FixtureRequest) -> str:
                return sanitize_page(request.param)

            def test_should_leave_no_tag(self, markdown: str) -> None:
                assert "<" not in markdown.replace("< ", "")

            def test_should_leave_safe_markdown(self, markdown: str) -> None:
                assert find_unsafe_markdown(markdown) == []

        class TestWhenAnImageThatIsNoPageImageHasAnEventHandler:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page('<img src=x onerror="alert(1)">')

            def test_should_drop_the_image(self, markdown: str) -> None:
                assert markdown == ""

        class TestWhenATagHasAnEventHandlerAnIdAndAClass:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page('<p onclick="alert(1)" id="x" class="y">Text</p>')

            def test_should_keep_the_tag_without_them(self, markdown: str) -> None:
                assert markdown == "<p>Text</p>"

        class TestWhenAPageImageHasAnEventHandlerAndASrcset:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page(
                    '<img src="imgs/a.jpg" onerror="alert(1)" alt="Figure" width="61%" srcset="x 2x" />'
                )

            def test_should_point_it_at_the_stored_image_and_keep_only_its_allowed_attributes(
                self, markdown: str
            ) -> None:
                assert markdown == '<img src="../images/K_1.jpg" alt="Figure" width="61%" />'

        class TestWhenTheNameOfAPageImageHoldsACharacterReference:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page('<img src="imgs/a&#46;jpg">')

            def test_should_decode_it_before_comparing_the_name(self, markdown: str) -> None:
                assert markdown == '<img src="../images/K_1.jpg" />'

        class TestWhenAnImageTargetsAnythingButAPageImage:
            @pytest.fixture(
                params=[
                    "imgs/../a.jpg",
                    "imgs/a.jpg/../../etc/passwd",
                    "../images/K_1.jpg",
                    "/etc/passwd",
                    "http://evil.example/a.jpg",
                    "data:image/png;base64,AAAA",
                    "javascript:alert(1)",
                    "imgs/unknown.jpg",
                ],
                ids=[
                    "a path climbing out of the images",
                    "a path climbing out of a page image",
                    "a stored image",
                    "an absolute path",
                    "a website",
                    "a data url",
                    "a script",
                    "an unknown page image",
                ],
            )
            def image_targets(self, request: pytest.FixtureRequest) -> ImageTargets:
                return ImageTargets(
                    html_image=sanitize_page(f'<img src="{request.param}">'),
                    markdown_image=sanitize_page(f"![x]({request.param})"),
                )

            def test_should_drop_an_html_image(self, image_targets: ImageTargets) -> None:
                assert image_targets.html_image == ""

            def test_should_turn_a_markdown_image_into_text(self, image_targets: ImageTargets) -> None:
                assert image_targets.markdown_image.startswith("![x]\\(")

            def test_should_leave_safe_markdown(self, image_targets: ImageTargets) -> None:
                assert find_unsafe_markdown(image_targets.markdown_image) == []

        class TestWhenAStyleSetsMoreThanTheTextAlignment:
            @pytest.fixture(
                params=[
                    (
                        '<div style="text-align: center; background: url(javascript:alert(1))">x</div>',
                        '<div style="text-align: center;">x</div>',
                    ),
                    ('<div style="color: red">x</div>', "<div>x</div>"),
                    (
                        '<div style="background:url(x);text-align:right">x</div>',
                        '<div style="text-align: right;">x</div>',
                    ),
                ],
                ids=["the alignment then a background", "a color only", "a background then the alignment"],
            )
            def cleaned(self, request: pytest.FixtureRequest) -> Cleaned:
                text, expected = request.param
                return Cleaned(markdown=sanitize_page(text), expected_markdown=expected)

            def test_should_keep_only_the_text_alignment(self, cleaned: Cleaned) -> None:
                assert cleaned.markdown == cleaned.expected_markdown

        class TestWhenAnHtmlLinkTargetsAScript:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page('<a href="javascript:alert(1)">click</a>')

            def test_should_keep_only_its_text(self, markdown: str) -> None:
                assert markdown == "click"

        class TestWhenMarkdownLinksTargetAScriptOrAWebsite:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("[click](javascript:alert(1)) [web](https://evil.example)")

            def test_should_turn_them_into_text(self, markdown: str) -> None:
                assert "](" not in markdown

            def test_should_leave_safe_markdown(self, markdown: str) -> None:
                assert find_unsafe_markdown(markdown) == []

        class TestWhenAMarkdownImageTargetsAPageImage:
            @pytest.fixture(
                params=[
                    ("![Figure 1](imgs/a.jpg)", "![Figure 1](../images/K_1.jpg)"),
                    ('![Figure](imgs/fig.png "title")', '![Figure](../images/K_2.jpg "title")'),
                ],
                ids=["alone", "with a title"],
            )
            def cleaned(self, request: pytest.FixtureRequest) -> Cleaned:
                text, expected = request.param
                return Cleaned(markdown=sanitize_page(text), expected_markdown=expected)

            def test_should_point_it_at_the_stored_image(self, cleaned: Cleaned) -> None:
                assert cleaned.markdown == cleaned.expected_markdown

        class TestWhenAMarkdownImageTargetsAPageImageBetweenAngleBrackets:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("![Figure](<imgs/fig.png>)")

            def test_should_turn_this_unusual_form_into_text(self, markdown: str) -> None:
                assert markdown == "![Figure]\\(< imgs/fig.png>)"

        class TestWhenRemovedMarkupStandsBetweenABareAngleBracketAndATagName:
            @pytest.fixture(
                params=[
                    "<<x></x>img src=x onerror=alert(1)>",
                    "<<!-- -->img src=x onerror=alert(1)>",
                    "<<script>x</script>img src=x onerror=alert(1)>",
                    "<<</b>svg onload=alert(1)>",
                ],
                ids=["an unknown element", "a comment", "a script", "a closing tag"],
            )
            def markdown(self, request: pytest.FixtureRequest) -> str:
                return sanitize_page(request.param)

            def test_should_not_join_them_into_a_tag(self, markdown: str) -> None:
                assert ("<img" in markdown, "<svg" in markdown) == (False, False)

            def test_should_leave_safe_markdown(self, markdown: str) -> None:
                assert find_unsafe_markdown(markdown) == []

        class TestWhenAReferenceDefinitionTargetsAScript:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("[x][a]\n\n[a]: javascript:alert(1)\n")

            def test_should_break_the_definition(self, markdown: str) -> None:
                assert "]\\:" in markdown

            def test_should_leave_safe_markdown(self, markdown: str) -> None:
                assert find_unsafe_markdown(markdown) == []

        class TestWhenTextLooksLikeADefinitionInsideAParagraph:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("See [1]: nothing else")

            def test_should_leave_it_as_it_is(self, markdown: str) -> None:
                assert markdown == "See [1]: nothing else"

        class TestWhenAReferenceDefinitionLiesInsideAnotherBlock:
            @pytest.fixture(
                params=[
                    "> [a]: https://evil.example/p.png\n\n![x][a]",
                    "- [a]: https://evil.example/p.png\n\n![x][a]",
                    "1. > - [a]:\n     https://evil.example/p.png\n\n![x][a]",
                    "## Title\n[a]: https://evil.example/p.png 'title'\n![x][a]",
                ],
                ids=["a quote", "a list", "nested blocks", "after a heading"],
            )
            def markdown(self, request: pytest.FixtureRequest) -> str:
                return sanitize_page(request.param)

            def test_should_break_the_definition(self, markdown: str) -> None:
                assert "]\\:" in markdown

            def test_should_leave_safe_markdown(self, markdown: str) -> None:
                assert find_unsafe_markdown(markdown) == []

        class TestWhenTheTextIsAlmostTwoMebibytesOfOpeningBrackets:
            payload = "[" * (sanitize.MAX_MARKDOWN_BYTES - 1)

            @pytest.fixture(scope="class")
            @classmethod
            def timed_cleaning(cls) -> TimedCleaning:
                started_seconds = time.monotonic()
                markdown = sanitize_page(cls.payload)
                return TimedCleaning(markdown=markdown, elapsed_seconds=time.monotonic() - started_seconds)

            def test_should_leave_it_as_it_is(self, timed_cleaning: TimedCleaning) -> None:
                assert timed_cleaning.markdown == self.payload

            def test_should_take_seconds_where_parsing_inline_syntax_to_find_definitions_took_a_minute(
                self, timed_cleaning: TimedCleaning
            ) -> None:
                assert timed_cleaning.elapsed_seconds < 10

        class TestWhenMarkdownLinksTargetAScriptWrittenWithCharacterReferences:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("[x](&#106;avascript:alert(1)) [y](jav&#x09;ascript:alert(1))")

            def test_should_leave_safe_markdown(self, markdown: str) -> None:
                assert find_unsafe_markdown(markdown) == []

        class TestWhenACommentFakesAPageMarker:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("a<!-- page 3 · scan 20261012-000000_deadbeef -->b")

            def test_should_drop_it_so_that_page_markers_cannot_be_faked(self, markdown: str) -> None:
                assert markdown == "ab"

        class TestWhenACommentIsNeverClosed:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("a<!-- never closed")

            def test_should_drop_everything_after_it(self, markdown: str) -> None:
                assert markdown == "a"

        class TestWhenMarkupIsBrokenOrExotic:
            @pytest.fixture(
                params=[
                    ("<scr<script>ipt>alert(1)</script>", "< scr"),
                    ("<javascript:alert(1)>", "< javascript:alert(1)>"),
                    ("</ script>", "< / script>"),
                    ("<!DOCTYPE html>", "< !DOCTYPE html>"),
                    ("<?php echo 1; ?>", "< ?php echo 1; ?>"),
                    ("<img src=x onerror=alert(1)//", "< img src=x onerror=alert(1)//"),
                    ("<svg:script>alert(1)</svg:script>", "< svg:script>alert(1)< /svg:script>"),
                ],
                ids=[
                    "a script split by another",
                    "an autolink to a script",
                    "a closing tag with a space",
                    "a doctype",
                    "a processing instruction",
                    "an unclosed tag",
                    "a namespaced tag",
                ],
            )
            def cleaned(self, request: pytest.FixtureRequest) -> Cleaned:
                text, expected = request.param
                return Cleaned(markdown=sanitize_page(text), expected_markdown=expected)

            def test_should_turn_it_into_text(self, cleaned: Cleaned) -> None:
                assert cleaned.markdown == cleaned.expected_markdown

            def test_should_leave_safe_markdown(self, cleaned: Cleaned) -> None:
                assert find_unsafe_markdown(cleaned.markdown) == []

        class TestWhenTheTextComparesValues:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("a < b and c > d")

            def test_should_leave_it_as_it_is(self, markdown: str) -> None:
                assert markdown == "a < b and c > d"

        class TestWhenFormulasHoldALessThanSign:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("$x<y$ and $0<\\epsilon$")

            def test_should_space_it_only_before_a_letter_so_that_the_formulas_keep_their_meaning(
                self, markdown: str
            ) -> None:
                assert markdown == "$x< y$ and $0<\\epsilon$"

        class TestWhenTheTextHoldsControlCharactersAndOtherLineEnds:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("a\x00b\x1bc\r\nd\re\u2028f")

            def test_should_drop_the_control_characters_and_end_each_line_with_a_line_feed(self, markdown: str) -> None:
                assert markdown == "abc\nd\nef"

        class TestWhenTheTextHoldsTheMarkupOfAnOcrPage:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page(
                    "## Chapter 1\n\nAccented text: “a naïve café résumé”, a façade, a phœnix.\n\n"
                    '<div style="text-align: center;"><img src="imgs/fig.png" alt="Image" width="40%" /></div>\n\n'
                    "<table border=1><tr><td colspan=2>Wood</td></tr>"
                    "<tr><td>Oak</td><td>H<sub>2</sub>O<br>x<sup>2</sup></td></tr></table>\n"
                )

            def test_should_keep_it_with_the_page_images_pointed_at_the_stored_ones_and_its_attributes_quoted(
                self, markdown: str
            ) -> None:
                assert markdown == (
                    "## Chapter 1\n\nAccented text: “a naïve café résumé”, a façade, a phœnix.\n\n"
                    '<div style="text-align: center;"><img src="../images/K_2.jpg" alt="Image" width="40%" /></div>\n\n'
                    '<table border="1"><tr><td colspan="2">Wood</td></tr>'
                    "<tr><td>Oak</td><td>H<sub>2</sub>O<br />x<sup>2</sup></td></tr></table>\n"
                )

        class TestWhenTheTextIsLargerThanTwoMebibytes:
            @pytest.fixture
            def clean_the_text(self) -> Callable[[], object]:
                return lambda: sanitize_page("x" * (sanitize.MAX_MARKDOWN_BYTES + 1))

            def test_should_refuse_it(self, clean_the_text: Callable[[], object]) -> None:
                with pytest.raises(MarkdownTooLarge, match="markdown larger than"):
                    clean_the_text()

        class TestWhenATagIsLongerThanAnOcrEngineWritesOne:
            @pytest.fixture
            def markdown(self) -> str:
                return sanitize_page("<div " + "a=b " * 10_000 + ">end")

            def test_should_turn_it_into_text(self, markdown: str) -> None:
                assert markdown.startswith("< div")

            def test_should_leave_safe_markdown(self, markdown: str) -> None:
                assert find_unsafe_markdown(markdown) == []

        class TestWhenTheTextIsMadeOfRandomHostileFragments:
            @pytest.fixture(scope="class")
            @classmethod
            def sanitized_payloads(cls) -> list[SanitizedPayload]:
                return [
                    SanitizedPayload(payload=payload, markdown=sanitize_page(payload))
                    for payload in generate_hostile_payloads()
                ]

            def test_should_leave_safe_markdown_every_time(self, sanitized_payloads: list[SanitizedPayload]) -> None:
                assert len(sanitized_payloads) == HOSTILE_PAYLOAD_COUNT
                assert [
                    (sanitized.payload, finding)
                    for sanitized in sanitized_payloads
                    for finding in find_unsafe_markdown(sanitized.markdown)
                ] == []

    class TestTheIsSafeImageNameFunction:
        class TestWhenTheNameHoldsOnlyLettersDigitsDotsHyphensAndUnderscores:
            @pytest.fixture(
                params=["img_in_image_box_93_1129_1104_1716.jpg", "a.png", "A-b_c.9"],
                ids=["a name of the engine", "a short name", "capitals hyphens and underscores"],
            )
            def is_safe(self, request: pytest.FixtureRequest) -> bool:
                return is_safe_image_name(request.param)

            def test_should_accept_it(self, is_safe: bool) -> None:
                assert is_safe

        class TestWhenTheNameCouldLeaveTheImageFolderOrHoldsOtherCharacters:
            @pytest.fixture(
                params=["", "..", "../x.jpg", "a/b.jpg", "a\\b.jpg", "x" * 129, "é.jpg", "a b.jpg", "a..jpg"],
                ids=[
                    "an empty name",
                    "the parent folder",
                    "a path out of the folder",
                    "a path",
                    "a windows path",
                    "a name longer than 128 characters",
                    "an accented letter",
                    "a space",
                    "two dots",
                ],
            )
            def is_safe(self, request: pytest.FixtureRequest) -> bool:
                return is_safe_image_name(request.param)

            def test_should_refuse_it(self, is_safe: bool) -> None:
                assert not is_safe
