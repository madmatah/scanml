"""The HTML previews of untrusted OCR Markdown (preview.py)."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from html.parser import HTMLParser
from types import MappingProxyType
from typing import ClassVar, NamedTuple

import pytest

from hostile_markup import (
    HOSTILE_PAYLOAD_COUNT,
    generate_hostile_payloads,
    generate_payloads,
    parse_markup,
    sanitize_page,
)
from scanmylib.assemble import GapSection, PageSection, Section, UnnumberedHeading
from scanmylib.preview import MAX_RENDERED_LENGTH, render_document, render_markdown

FILES_URL = "/api/documents/d0c/files"
TAGS_NO_PREVIEW_HOLDS = frozenset(
    {
        "script",
        "style",
        "iframe",
        "object",
        "embed",
        "svg",
        "math",
        "form",
        "input",
        "link",
        "meta",
        "base",
    }
)
CLASSES_A_PREVIEW_MAY_HOLD = frozenset({("div", "math-display"), ("span", "math-inline")})


class Rendered(NamedTuple):
    html: str
    expected_html: str


class TimedRendering(NamedTuple):
    html: str
    elapsed_seconds: float


class TextPreview(NamedTuple):
    text: str
    html: str


class FormulaPreview(NamedTuple):
    tex: str
    html: str


class PreviewedPayload(NamedTuple):
    payload: str
    html: str


class FuzzedFormulas(NamedTuple):
    markdown: str
    html: str
    inner_tags: list[str]


class FormulaCollector(HTMLParser):
    KINDS: ClassVar[Mapping[tuple[str, str | None], str]] = MappingProxyType(
        {("div", "math-display"): "display", ("span", "math-inline"): "inline"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str]] = []
        self.inner_tags: list[str] = []
        self.current: list[str] | None = None
        self.depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.current is not None:
            self.inner_tags.append(tag)
            self.depth += tag not in {"br", "hr", "img", "col"}
        elif kind := self.KINDS.get((tag, dict(attrs).get("class"))):
            self.current = [kind, ""]

    def handle_endtag(self, tag: str) -> None:
        if self.current is not None and self.depth:
            self.depth -= 1
        elif self.current is not None:
            self.found.append((self.current[0], self.current[1]))
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current[1] += data


def keep_as_written(text: str) -> str:
    return text


def render_preview(markdown: str) -> str:
    return render_markdown(markdown, FILES_URL)


def parse_formulas(html: str) -> FormulaCollector:
    parser = FormulaCollector()
    parser.feed(html)
    parser.close()
    return parser


def list_tag_names(html: str) -> list[str]:
    return [tag for tag, _ in parse_markup(html).tags]


def find_unsafe_html(html: str) -> list[str]:
    collected_markup = parse_markup(html)
    findings = list(collected_markup.non_tag_markup)
    for tag, attributes in collected_markup.tags:
        if tag in TAGS_NO_PREVIEW_HOLDS:
            findings.append(f"tag {tag}")
        for attribute_name, attribute_value in attributes:
            if attribute_name.startswith("on") or attribute_name in {"style", "srcset", "id"}:
                findings.append(f"attribute {attribute_name} of {tag}")
            if attribute_name == "class" and (tag, attribute_value) not in CLASSES_A_PREVIEW_MAY_HOLD:
                findings.append(f"class {attribute_value} of {tag}")
            if attribute_name in ("src", "href") and not (
                attribute_value is not None and attribute_value.startswith(f"{FILES_URL}/images/")
            ):
                findings.append(f"{attribute_name} of {tag}: {attribute_value}")
    return findings


def fuzz_formulas(fragments: Sequence[str], payload_count: int) -> list[FuzzedFormulas]:
    fuzzed = []
    for payload in generate_payloads(fragments, payload_count, seed=20261013):
        for markdown in (payload, sanitize_page(payload)):
            html = render_preview(markdown)
            fuzzed.append(FuzzedFormulas(markdown=markdown, html=html, inner_tags=parse_formulas(html).inner_tags))
    return fuzzed


class TestThePreview:
    class TestTheRenderMarkdownFunction:
        class TestWhenThePageReferencesItsImagesInMarkdownAndInHtml:
            @pytest.fixture
            def html(self) -> str:
                return render_preview('![Figure](../images/K_1.jpg)\n\n<img src="images/K_2.jpg" alt="x" />')

            def test_should_point_the_markdown_image_at_the_files_endpoint(self, html: str) -> None:
                assert f'src="{FILES_URL}/images/K_1.jpg"' in html

            def test_should_point_the_html_image_at_the_files_endpoint(self, html: str) -> None:
                assert f'src="{FILES_URL}/images/K_2.jpg"' in html

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenAPageFileWasEditedByHandWithHostileMarkup:
            @pytest.fixture(
                params=[
                    "<img src=x onerror=alert(1)>",
                    '<a href="javascript:alert(1)">x</a>',
                    "![x](https://evil.example/pixel.png)",
                    "<script>alert(1)</script>",
                    '<p style="background:url(https://evil.example)" class="x">x</p>',
                    "[x](../../../../etc/passwd)",
                ],
                ids=[
                    "an event handler",
                    "a link to a script",
                    "an image of a website",
                    "a script",
                    "a style and a class",
                    "a link out of the library",
                ],
            )
            def html(self, request: pytest.FixtureRequest) -> str:
                return render_preview(request.param)

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenThePageIsLongerThanTheRenderingLimit:
            @pytest.fixture(scope="class")
            @classmethod
            def timed_rendering(cls) -> TimedRendering:
                markdown = "&#x" * (2 * 1024 * 1024 // 3) + "<script>alert(1)</script>"
                started_seconds = time.monotonic()
                html = render_preview(markdown)
                return TimedRendering(html=html, elapsed_seconds=time.monotonic() - started_seconds)

            def test_should_show_it_as_its_escaped_source(self, timed_rendering: TimedRendering) -> None:
                assert timed_rendering.html.startswith('<pre class="markdown-source">&amp;#x&amp;#x')

            def test_should_escape_its_markup(self, timed_rendering: TimedRendering) -> None:
                html = timed_rendering.html
                assert ("<script" in html, html.endswith("&lt;/script&gt;</pre>")) == (False, True)

            def test_should_take_seconds_where_markdown_it_took_over_a_minute_on_a_page_no_ocr_engine_writes(
                self, timed_rendering: TimedRendering
            ) -> None:
                assert timed_rendering.elapsed_seconds < 5

        class TestWhenThePageIsAsLongAsTheRenderingLimit:
            @pytest.fixture
            def html(self) -> str:
                return render_preview("x" * MAX_RENDERED_LENGTH)

            def test_should_render_it_as_markdown(self, html: str) -> None:
                assert html == "<p>" + "x" * MAX_RENDERED_LENGTH + "</p>\n"

        class TestWhenThePageIsMadeOfRandomHostileFragmentsSanitized:
            @pytest.fixture(scope="class")
            @classmethod
            def previewed_payloads(cls) -> list[PreviewedPayload]:
                return [
                    PreviewedPayload(payload=payload, html=render_preview(sanitize_page(payload)))
                    for payload in generate_hostile_payloads()
                ]

            def test_should_render_safe_html_every_time(self, previewed_payloads: list[PreviewedPayload]) -> None:
                assert len(previewed_payloads) == HOSTILE_PAYLOAD_COUNT
                assert [
                    (previewed.payload, finding)
                    for previewed in previewed_payloads
                    for finding in find_unsafe_html(previewed.html)
                ] == []

        class TestWhenThePageHoldsADisplayFormula:
            @pytest.fixture
            def html(self) -> str:
                return render_preview(r"$$\frac{a}{b}=\sqrt{x^2+1}$$")

            def test_should_render_it_as_a_block(self, html: str) -> None:
                assert html == r'<div class="math-display">\frac{a}{b}=\sqrt{x^2+1}</div>'

        class TestWhenADisplayFormulaHasSpacesInsideItsDollarsAsPaddleOcrVlWritesThem:
            @pytest.fixture
            def html(self) -> str:
                return render_preview(
                    r" $$ \begin{array}{c|c}{X=1}&{X=2,5}\\ {Y=7,5&{Y=8} \end{array} $$ " + "\n\nNext."
                )

            def test_should_render_it_as_a_block_with_its_tex_escaped(self, html: str) -> None:
                assert html == (
                    r'<div class="math-display">\begin{array}{c|c}{X=1}&amp;{X=2,5}\\ '
                    r"{Y=7,5&amp;{Y=8} \end{array}</div>"
                    "<p>Next.</p>\n"
                )

        class TestWhenADisplayFormulaStandsInAParagraph:
            @pytest.fixture
            def html(self) -> str:
                return render_preview("before $$x$$ after")

            def test_should_end_the_paragraph_before_it_and_open_another_after_it(self, html: str) -> None:
                assert html == '<p>before </p><div class="math-display">x</div><p> after</p>\n'

        class TestWhenFormulasBetweenBracketsStandInAParagraph:
            @pytest.fixture
            def html(self) -> str:
                return render_preview(r"\( x_1 \) and \[ y^2 \]")

            def test_should_keep_the_inline_one_in_the_paragraph_and_end_it_before_the_display_one(
                self, html: str
            ) -> None:
                assert html == '<p><span class="math-inline">x_1</span> and </p><div class="math-display">y^2</div>'

        class TestWhenADisplayFormulaStandsInAListItem:
            @pytest.fixture
            def html(self) -> str:
                return render_preview("- $$x$$\n- b")

            def test_should_render_it_in_the_item(self, html: str) -> None:
                assert html == '<ul>\n<li><div class="math-display">x</div></li>\n<li>b</li>\n</ul>\n'

        class TestWhenADisplayFormulaStandsInBoldText:
            @pytest.fixture
            def html(self) -> str:
                return render_preview("**bold $$x$$ end**")

            def test_should_render_it_with_the_bold_text_the_html_parser_reopens_inside_it(self, html: str) -> None:
                assert html == (
                    '<p><strong>bold </strong></p><div class="math-display"><strong>x</strong></div>'
                    "<p><strong> end</strong></p>\n"
                )

            def test_should_keep_the_tex_as_the_text_of_the_formula(self, html: str) -> None:
                assert parse_formulas(html).found == [("display", "x")]

        class TestWhenAFormulaSpansSeveralLines:
            tex = "\\begin{aligned}\na &= b * c \\\\\n- d &= e_1 * f_2\n\\end{aligned}"

            @pytest.fixture
            def html(self) -> str:
                return render_preview(f"Let\n$$\n{self.tex}\n$$\nso *done*.")

            def test_should_keep_its_lines_as_the_tex_of_one_display_formula_not_as_markdown(self, html: str) -> None:
                assert parse_formulas(html).found == [("display", self.tex)]

            def test_should_hold_no_markup_inside_the_formula(self, html: str) -> None:
                assert parse_formulas(html).inner_tags == []

            def test_should_end_the_paragraph_before_it(self, html: str) -> None:
                assert html.startswith('<p>Let\n</p><div class="math-display">')

            def test_should_read_the_markdown_after_it(self, html: str) -> None:
                assert html.endswith("</div><p>\nso <em>done</em>.</p>\n")

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenThePageHoldsAnInlineFormula:
            @pytest.fixture(
                params=[
                    ("Résumé: $E=mc^2$.", '<p>Résumé: <span class="math-inline">E=mc^2</span>.</p>\n'),
                    ("## Law $ F = ma $", '<h2>Law <span class="math-inline">F = ma</span></h2>\n'),
                    ("pounds (18 $ ^{th} $, 140)", '<p>pounds (18 <span class="math-inline">^{th}</span>, 140)</p>\n'),
                    (
                        "<table><tr><td>0 $ ^{m} $,385</td><td>$ 0m,385 $</td></tr></table>",
                        '<table><tbody><tr><td>0 <span class="math-inline">^{m}</span>,385</td>'
                        '<td><span class="math-inline">0m,385</span></td></tr></tbody></table>',
                    ),
                ],
                ids=[
                    "in a sentence",
                    "in a heading, with spaces inside its dollars",
                    "as the unit after a number, as PaddleOCR-VL writes the units of old books",
                    "in table cells, after a number and alone",
                ],
            )
            def rendered(self, request: pytest.FixtureRequest) -> Rendered:
                markdown, expected = request.param
                return Rendered(html=render_preview(markdown), expected_html=expected)

            def test_should_render_it_as_an_inline_span(self, rendered: Rendered) -> None:
                assert rendered.html == rendered.expected_html

        class TestWhenFormulasHoldCharactersThatMarkdownOrHtmlReads:
            tex = r"a_1 * b_2 = c_{n}^{*} \\ \{x\} \& \$ x & y \_ < 3"

            @pytest.fixture
            def html(self) -> str:
                return render_preview(f"${self.tex}$ and $${self.tex}$$")

            def test_should_pass_their_tex_to_the_web_ui_unchanged(self, html: str) -> None:
                assert parse_formulas(html).found == [("inline", self.tex), ("display", self.tex)]

            def test_should_hold_no_markup_inside_them(self, html: str) -> None:
                assert parse_formulas(html).inner_tags == []

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenAFormulaInATableCellHoldsCharacterReferences:
            @pytest.fixture
            def html(self) -> str:
                # The text of HTML table cells is escaped, PaddleOCR-VL's too.
                return render_preview("<table><tr><td>$ a &lt; b &amp;&amp; c $</td></tr></table>")

            def test_should_pass_the_tex_that_a_browser_reads(self, html: str) -> None:
                assert parse_formulas(html).found == [("inline", "a < b && c")]

            def test_should_hold_no_markup_inside_it(self, html: str) -> None:
                assert parse_formulas(html).inner_tags == []

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenDollarsAreAmountsOrVariables:
            @pytest.fixture(
                params=[
                    "It costs 5 $.",
                    "5 $ and 10 $",
                    "from 5$ to 10$",
                    "the price (5 $) and the cost (10 $)",
                    "$5",
                    "$5 and $10",
                    "$5, $10 or $20",
                    "$ 5 or $ 10",
                    "US$ 30 and US$ 40",
                    "A book costs 5 $ and a notebook 10 $; in the café, $5 and $10.",
                    r"\$x\$ and \$y\$",
                    "echo $HOME $PATH",
                ],
                ids=[
                    "an amount followed by its dollar",
                    "two amounts followed by their dollars",
                    "two amounts followed by their dollars without a space",
                    "amounts in parentheses",
                    "an amount after its dollar",
                    "two amounts after their dollars",
                    "three amounts after their dollars",
                    "two amounts after their dollars and a space",
                    "an amount after US$",
                    "amounts of both kinds",
                    "escaped dollars",
                    "shell variables",
                ],
            )
            def text_preview(self, request: pytest.FixtureRequest) -> TextPreview:
                return TextPreview(text=request.param, html=render_preview(request.param))

            def test_should_mark_no_formula(self, text_preview: TextPreview) -> None:
                assert parse_formulas(text_preview.html).found == []

            def test_should_keep_every_dollar(self, text_preview: TextPreview) -> None:
                assert text_preview.html.count("$") == text_preview.text.count("$")

            def test_should_render_safe_html(self, text_preview: TextPreview) -> None:
                assert find_unsafe_html(text_preview.html) == []

        class TestWhenDollarsSpanParagraphsOrCellsOrStandInCodeOrAnAttribute:
            @pytest.fixture(
                params=[
                    ("$a\n\nb$", "<p>$a</p>\n<p>b$</p>\n"),
                    (
                        "<table><tr><td>$ a</td><td>b $</td></tr></table>",
                        "<table><tbody><tr><td>$ a</td><td>b $</td></tr></tbody></table>",
                    ),
                    ("`$x$` and `a $b` c$", "<p><code>$x$</code> and <code>a $b</code> c$</p>\n"),
                    ("```\n$x$ and $$y$$\n```", "<pre><code>$x$ and $$y$$\n</code></pre>\n"),
                    (
                        "![figure $x$](../images/K_1.jpg)",
                        f'<p><img src="{FILES_URL}/images/K_1.jpg" alt="figure $x$"></p>\n',
                    ),
                ],
                ids=[
                    "across paragraphs",
                    "across table cells",
                    "in inline code",
                    "in a code block",
                    "in an image text",
                ],
            )
            def rendered(self, request: pytest.FixtureRequest) -> Rendered:
                markdown, expected = request.param
                return Rendered(html=render_preview(markdown), expected_html=expected)

            def test_should_mark_no_formula_there(self, rendered: Rendered) -> None:
                assert rendered.html == rendered.expected_html

        class TestWhenAFormulaHoldsTexCommandsForLinksClassesStylesOrImages:
            @pytest.fixture(
                params=[
                    r"\href{javascript:alert(1)}{click}",
                    r"\url{https://evil.example}",
                    r"\htmlClass{evil}{x}",
                    r"\htmlStyle{background:url(https://evil.example)}{x}",
                    r"\includegraphics{https://evil.example/p.png}",
                ],
                ids=["href", "url", "htmlClass", "htmlStyle", "includegraphics"],
            )
            def formula_preview(self, request: pytest.FixtureRequest) -> FormulaPreview:
                return FormulaPreview(tex=request.param, html=render_preview(f"Formula: ${request.param}$"))

            def test_should_pass_them_as_the_tex_of_the_formula_for_katex_to_typeset_without_trust(
                self, formula_preview: FormulaPreview
            ) -> None:
                assert parse_formulas(formula_preview.html).found == [("inline", formula_preview.tex)]

            def test_should_make_no_other_tag(self, formula_preview: FormulaPreview) -> None:
                assert list_tag_names(formula_preview.html) == ["p", "span"]

            def test_should_render_safe_html(self, formula_preview: FormulaPreview) -> None:
                assert find_unsafe_html(formula_preview.html) == []

        class TestWhenAFormulaHoldsEscapedMarkup:
            payload = "</span><script>alert(1)</script><span>"

            @pytest.fixture
            def html(self) -> str:
                return render_preview("$" + self.payload.replace("<", "&lt;").replace(">", "&gt;") + "$")

            def test_should_pass_it_as_the_text_of_the_formula(self, html: str) -> None:
                assert parse_formulas(html).found == [("inline", self.payload)]

            def test_should_make_no_other_tag(self, html: str) -> None:
                assert list_tag_names(html) == ["p", "span"]

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenAFormulaHoldsMarkup:
            @pytest.fixture(params=[keep_as_written, sanitize_page], ids=["as written", "sanitized first"])
            def html(self, request: pytest.FixtureRequest) -> str:
                prepare: Callable[[str], str] = request.param
                return render_preview(prepare("$x</span><script>alert(1)</script><span>$"))

            def test_should_make_no_formula_since_formulas_hold_no_tag(self, html: str) -> None:
                assert parse_formulas(html).found == []

            def test_should_leave_no_script(self, html: str) -> None:
                assert "script" not in html

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenThePageHoldsThePlaceholderCharactersOfFormulas:
            @pytest.fixture
            def html(self) -> str:
                return render_preview("\ufdd00\ufdd1 and $y$ \ufdd1")

            def test_should_drop_them_so_that_they_cannot_forge_a_formula(self, html: str) -> None:
                assert html == '<p>0 and <span class="math-inline">y</span></p>\n'

        class TestWhenMarkupCarriesAClass:
            @pytest.fixture(
                params=[
                    ('<div class="math-display">x</div>', '<div class="math-display">x</div>'),
                    ('<span class="math-inline">x</span>', '<p><span class="math-inline">x</span></p>\n'),
                    ('<div class="math-inline">x</div>', "<div>x</div>"),
                    ('<span class="math-display">x</span>', "<p><span>x</span></p>\n"),
                    ('<div class="math-display evil">x</div>', "<div>x</div>"),
                    ('<p class="math-inline">x</p>', "<p>x</p>"),
                    ('<span class="katex">x</span>', "<p><span>x</span></p>\n"),
                    (
                        '<table><tr><td class="math-inline">x</td></tr></table>',
                        "<table><tbody><tr><td>x</td></tr></tbody></table>",
                    ),
                ],
                ids=[
                    "the mark of a display formula on a div",
                    "the mark of an inline formula on a span",
                    "the mark of an inline formula on a div",
                    "the mark of a display formula on a span",
                    "the mark of a formula and another class",
                    "the mark of a formula on a paragraph",
                    "a class of katex",
                    "the mark of a formula on a table cell",
                ],
            )
            def rendered(self, request: pytest.FixtureRequest) -> Rendered:
                markdown, expected = request.param
                return Rendered(html=render_preview(markdown), expected_html=expected)

            def test_should_keep_no_class_but_the_mark_of_a_formula_on_its_own_tag(self, rendered: Rendered) -> None:
                assert rendered.html == rendered.expected_html

        class TestWhenASanitizedPageHoldsFormulasAsPaddleOcrVlWritesThem:
            @pytest.fixture
            def html(self) -> str:
                # Synthetic text shaped like a PaddleOCR-VL result on an old printed page: units written as
                # superscripts after numbers, spaces inside the dollars, a table whose cells carry inline styles.
                return render_preview(
                    sanitize_page(
                        "a sample crate of forty pounds (18 $ ^{th} $, 140) placed on the scale of the café\n\n"
                        "<table border=1><tr>"
                        "<td style='text-align: center; word-wrap: break-word;'>Width of the shelf</td>"
                        "<td style='text-align: center; word-wrap: break-word;'>0 $ ^{m} $,385</td></tr>"
                        '<tr><td>Area of the floor</td><td colspan="2">$ 42mq.17 $</td></tr></table>\n'
                    )
                )

            def test_should_mark_each_formula(self, html: str) -> None:
                assert parse_formulas(html).found == [("inline", "^{th}"), ("inline", "^{m}"), ("inline", "42mq.17")]

            def test_should_hold_no_markup_inside_them(self, html: str) -> None:
                assert parse_formulas(html).inner_tags == []

            def test_should_render_safe_html(self, html: str) -> None:
                assert find_unsafe_html(html) == []

        class TestWhenThePageIsMadeOfRandomFragmentsOfFormulas:
            fragments = (
                "$",
                "$$",
                "\\(",
                "\\)",
                "\\[",
                "\\]",
                "\\",
                "5 ",
                " ",
                "x",
                "^{m}",
                "\n",
                "\n\n",
                "`",
                "<b>",
                "</b>",
                "&lt;",
                "&amp;",
                "<table><tr><td>",
                "</td>",
                "<img src=imgs/a.jpg alt='$x$'>",
                "<!--",
                "-->",
                "\ufdd0",
                "\ufdd1",
                "0",
                "<p>",
                "</p>",
                "<code>",
                "</code>",
                "- ",
                "*",
            )
            payload_count = 2000
            # The HTML parser re-opens these tags inside a display formula that interrupts formatted text ("*$$x$$*"),
            # and KaTeX replaces them.
            inline_formatting_tags = frozenset({"a", "b", "code", "em", "i", "s", "small", "strike", "strong", "u"})

            @pytest.fixture(scope="class")
            @classmethod
            def fuzzed_formulas(cls) -> list[FuzzedFormulas]:
                return fuzz_formulas(cls.fragments, cls.payload_count)

            def test_should_render_safe_html_every_time(self, fuzzed_formulas: list[FuzzedFormulas]) -> None:
                assert len(fuzzed_formulas) == 2 * self.payload_count
                assert [
                    (fuzzed.markdown, finding)
                    for fuzzed in fuzzed_formulas
                    for finding in find_unsafe_html(fuzzed.html)
                ] == []

            def test_should_leave_no_placeholder_character_of_formulas(
                self, fuzzed_formulas: list[FuzzedFormulas]
            ) -> None:
                assert len(fuzzed_formulas) == 2 * self.payload_count
                assert [
                    fuzzed.markdown for fuzzed in fuzzed_formulas if "\ufdd0" in fuzzed.html or "\ufdd1" in fuzzed.html
                ] == []

            def test_should_hold_no_markup_inside_formulas_but_the_inline_formatting_that_katex_replaces(
                self, fuzzed_formulas: list[FuzzedFormulas]
            ) -> None:
                assert len(fuzzed_formulas) == 2 * self.payload_count
                assert [
                    fuzzed.html
                    for fuzzed in fuzzed_formulas
                    if not set(fuzzed.inner_tags) <= self.inline_formatting_tags
                ] == []

        class TestWhenThePageRepeatsHostileDollarsUpToTheRenderingLimit:
            @pytest.fixture(
                params=["\\[", "\\(", "$ a ", "5 $ ", "$$ a <b> ", "<code>$x$", "<a", "` $", "$x$ "],
                ids=[
                    "unclosed display brackets",
                    "unclosed inline parentheses",
                    "unclosed dollars",
                    "dollars after amounts",
                    "unclosed double dollars before a tag",
                    "formulas in unclosed code",
                    "unclosed links",
                    "backticks before dollars",
                    "formulas",
                ],
            )
            def timed_rendering(self, request: pytest.FixtureRequest) -> TimedRendering:
                markdown = request.param * (MAX_RENDERED_LENGTH // len(request.param))
                started_seconds = time.monotonic()
                html = render_preview(markdown)
                return TimedRendering(html=html, elapsed_seconds=time.monotonic() - started_seconds)

            def test_should_mark_the_formulas_in_seconds(self, timed_rendering: TimedRendering) -> None:
                assert timed_rendering.elapsed_seconds < 5

    class TestTheRenderDocumentFunction:
        class TestWhenTheDocumentHasGapsASpreadFrontMatterAndAnUnnumberedPage:
            @pytest.fixture
            def html(self) -> str:
                pages = {
                    "k1": "First text",
                    "k2": "Second <b>text</b>",
                    "k3": "No number",
                    "k4": "Spread",
                    "k5": "Preface",
                }
                sections: list[Section] = [
                    PageSection("k1", "1"),
                    GapSection(2, 4),
                    PageSection("k2", "5"),
                    GapSection(6, 6),
                    PageSection("k4", "7–8"),
                    PageSection("k5", "xii"),
                    UnnumberedHeading(),
                    PageSection("k3", None),
                ]
                return render_document("Title <i>", sections, pages.__getitem__, FILES_URL)

            def test_should_open_with_the_title_escaped(self, html: str) -> None:
                assert html.startswith("<h1>Title &lt;i&gt;</h1>")

            def test_should_put_each_page_in_a_section_after_a_marker_with_its_label(self, html: str) -> None:
                page_1 = '<section class="page" data-key="k1"><p class="page-marker" data-label="1">Page 1</p>'
                assert f"{page_1}<p>First text</p>" in html

            def test_should_name_the_missing_pages_of_a_gap(self, html: str) -> None:
                assert '<p class="missing-pages" data-range="2–4">Missing pages: 2–4</p>' in html

            def test_should_name_the_missing_page_of_a_gap_of_one_page(self, html: str) -> None:
                assert '<p class="missing-pages" data-range="6">Missing page: 6</p>' in html

            def test_should_label_a_spread_with_both_its_numbers(self, html: str) -> None:
                assert '<p class="page-marker" data-label="7–8">Page 7–8</p>' in html

            def test_should_label_front_matter_with_its_roman_number(self, html: str) -> None:
                assert '<p class="page-marker" data-label="xii">Page xii</p>' in html

            def test_should_head_the_unnumbered_pages(self, html: str) -> None:
                assert '<h2 class="unnumbered">Unnumbered pages</h2>' in html

            def test_should_mark_an_unnumbered_page_without_a_label(self, html: str) -> None:
                marker = '<p class="page-marker" data-label="">Unnumbered page</p>'
                assert f'<section class="page" data-key="k3">{marker}' in html
