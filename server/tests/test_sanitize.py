"""Untrusted OCR Markdown: sanitizer (sanitize.py) and HTML previews (preview.py)."""

from __future__ import annotations

import random
import re
import time
from html.parser import HTMLParser

import pytest
from markdown_it import MarkdownIt

from scanmylib import sanitize
from scanmylib.assemble import GapSection, PageSection, UnnumberedHeading
from scanmylib.preview import MAX_RENDERED_LENGTH, render_document, render_markdown
from scanmylib.sanitize import MarkdownTooLarge, is_safe_image_name, sanitize_markdown

IMAGES = {"a.jpg": "../images/K_1.jpg", "fig.png": "../images/K_2.jpg"}
FILES_URL = "/api/documents/d0c/files"


def resolve(reference: str) -> str | None:
    name = reference.removeprefix("imgs/")
    return IMAGES.get(name) if reference.startswith("imgs/") else None


def clean(text: str) -> str:
    return sanitize_markdown(text, resolve)


class Markup(HTMLParser):
    """Collects what a browser would see as markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, list[tuple[str, str | None]]]] = []
        self.other: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))

    handle_startendtag = handle_starttag

    def handle_comment(self, data):
        self.other.append(f"comment:{data}")

    def handle_decl(self, decl):
        self.other.append(f"decl:{decl}")

    def handle_pi(self, data):
        self.other.append(f"pi:{data}")

    def unknown_decl(self, data):
        self.other.append(f"unknown:{data}")


def markup(text: str) -> Markup:
    parser = Markup()
    parser.feed(text)
    parser.close()
    return parser


_SERIALIZED_TAG = re.compile(r'</?([a-z0-9]+)(?: [a-z]+="[^"<>]*")*(?: /)?>')


def assert_safe_markdown(output: str) -> None:
    """Structural invariants of sanitized Markdown."""
    for match in re.finditer(r"<(?=[A-Za-z/!?])", output):
        tag = _SERIALIZED_TAG.match(output, match.start())
        assert tag, f"unexpected markup at {output[match.start() : match.start() + 40]!r}"
        assert tag[1] in sanitize._ALLOWED_TAGS
    parsed = markup(output)
    assert parsed.other == []
    for tag, attributes in parsed.tags:
        assert tag in sanitize._ALLOWED_TAGS
        for name, value in attributes:
            assert not name.startswith("on")
            assert name in {
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
            if name == "src":
                assert value in IMAGES.values()
            if name == "style":
                assert re.fullmatch(r"text-align: (left|right|center|justify);", value)
    # Markdown links/images only to page images, whatever the renderer's URL policy.
    lenient = MarkdownIt("commonmark")
    lenient.validateLink = lambda url: True
    rendered = markup(lenient.render(output))
    for tag, attributes in rendered.tags:
        for name, value in attributes:
            if name in ("href", "src"):
                assert value in IMAGES.values(), (tag, name, value)


def assert_safe_html(html: str) -> None:
    parsed = markup(html)
    assert parsed.other == []
    for tag, attributes in parsed.tags:
        assert tag not in {
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
        for name, value in attributes:
            assert not name.startswith("on")
            assert name not in {"style", "srcset", "id"}
            if name == "class":  # only the marks of formulas, typeset by the web UI
                assert (tag, value) in {("div", "math-display"), ("span", "math-inline")}, (tag, value)
            if name in ("src", "href"):
                assert value.startswith(f"{FILES_URL}/images/"), value


# -- removal of dangerous markup ------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
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
)
def test_script_like_elements_are_dropped_with_their_content(payload):
    assert clean(payload) == "ab"


def test_unclosed_script_drops_everything_after_it():
    assert clean("before<script>alert(1) and the rest") == "before"


@pytest.mark.parametrize(
    "payload",
    [
        "<embed src='evil.swf'>",
        "<link rel=stylesheet href='https://evil.example/x.css'>",
        "<meta http-equiv=refresh content='0;url=javascript:alert(1)'>",
        "<base href='https://evil.example/'>",
        "<form action='https://evil.example'><input name=q><button>Send</button></form>",
        "<select><option>1</option></select>",
    ],
)
def test_forms_and_document_level_tags_are_removed(payload):
    output = clean(payload)
    assert "<" not in output.replace("< ", "")
    assert_safe_markdown(output)


def test_event_handlers_and_unknown_images_are_removed():
    assert clean('<img src=x onerror="alert(1)">') == ""
    assert clean('<p onclick="alert(1)" id="x" class="y">Text</p>') == "<p>Text</p>"


def test_page_images_are_rewritten_and_cleaned():
    output = clean('<img src="imgs/a.jpg" onerror="alert(1)" alt="Figure" width="61%" srcset="x 2x" />')
    assert output == '<img src="../images/K_1.jpg" alt="Figure" width="61%" />'


def test_image_names_are_compared_after_entity_decoding():
    assert clean('<img src="imgs/a&#46;jpg">') == '<img src="../images/K_1.jpg" />'


@pytest.mark.parametrize(
    "src",
    [
        "imgs/../a.jpg",
        "imgs/a.jpg/../../etc/passwd",
        "../images/K_1.jpg",
        "/etc/passwd",
        "http://evil.example/a.jpg",
        "data:image/png;base64,AAAA",
        "javascript:alert(1)",
        "imgs/unknown.jpg",
    ],
)
def test_images_can_only_target_the_page_images(src):
    assert clean(f'<img src="{src}">') == ""
    output = clean(f"![x]({src})")
    assert output.startswith("![x]\\(")
    assert_safe_markdown(output)


def test_styles_keep_only_text_alignment():
    assert clean('<div style="text-align: center; background: url(javascript:alert(1))">x</div>') == (
        '<div style="text-align: center;">x</div>'
    )
    assert clean('<div style="color: red">x</div>') == "<div>x</div>"
    assert clean('<div style="background:url(x);text-align:right">x</div>') == '<div style="text-align: right;">x</div>'


def test_links_are_unwrapped_and_markdown_links_neutralized():
    assert clean('<a href="javascript:alert(1)">click</a>') == "click"
    output = clean("[click](javascript:alert(1)) [web](https://evil.example)")
    assert "](" not in output
    assert_safe_markdown(output)


def test_markdown_page_images_are_rewritten():
    assert clean("![Figure 1](imgs/a.jpg)") == "![Figure 1](../images/K_1.jpg)"
    assert clean('![Figure](imgs/fig.png "title")') == '![Figure](../images/K_2.jpg "title")'
    assert clean("![Figure](<imgs/fig.png>)") == "![Figure]\\(< imgs/fig.png>)"  # unusual form: text


@pytest.mark.parametrize(
    "payload",
    [
        "<<x></x>img src=x onerror=alert(1)>",
        "<<!-- -->img src=x onerror=alert(1)>",
        "<<script>x</script>img src=x onerror=alert(1)>",
        "<<</b>svg onload=alert(1)>",
    ],
)
def test_removed_markup_cannot_join_a_bare_angle_bracket_to_a_tag(payload):
    output = clean(payload)
    assert "<img" not in output and "<svg" not in output
    assert_safe_markdown(output)


def test_reference_definitions_are_neutralized():
    output = clean("[x][a]\n\n[a]: javascript:alert(1)\n")
    assert "]\\:" in output
    assert_safe_markdown(output)
    assert clean("See [1]: nothing else") == "See [1]: nothing else"  # no definition, untouched


@pytest.mark.parametrize(
    "payload",
    [
        "> [a]: https://evil.example/p.png\n\n![x][a]",
        "- [a]: https://evil.example/p.png\n\n![x][a]",
        "1. > - [a]:\n     https://evil.example/p.png\n\n![x][a]",
        "## Title\n[a]: https://evil.example/p.png 'title'\n![x][a]",
    ],
)
def test_reference_definitions_inside_other_blocks_are_neutralized(payload):
    output = clean(payload)
    assert "]\\:" in output
    assert_safe_markdown(output)


def test_hostile_markdown_is_sanitized_quickly():
    # Finding reference definitions used to parse inline syntax too: a minute for this.
    payload = "[" * (sanitize.MAX_MARKDOWN_BYTES - 1)
    started = time.monotonic()
    assert clean(payload) == payload
    assert time.monotonic() - started < 10


def test_entity_encoded_javascript_links_are_neutralized():
    output = clean("[x](&#106;avascript:alert(1)) [y](jav&#x09;ascript:alert(1))")
    assert_safe_markdown(output)


def test_comments_are_removed_so_page_markers_cannot_be_faked():
    assert clean("a<!-- page 3 · scan 20261012-000000_deadbeef -->b") == "ab"
    assert clean("a<!-- never closed") == "a"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("<scr<script>ipt>alert(1)</script>", "< scr"),
        ("<javascript:alert(1)>", "< javascript:alert(1)>"),
        ("</ script>", "< / script>"),
        ("<!DOCTYPE html>", "< !DOCTYPE html>"),
        ("<?php echo 1; ?>", "< ?php echo 1; ?>"),
        ("<img src=x onerror=alert(1)//", "< img src=x onerror=alert(1)//"),
        ("<svg:script>alert(1)</svg:script>", "< svg:script>alert(1)< /svg:script>"),
    ],
)
def test_broken_or_exotic_markup_becomes_text(payload, expected):
    output = clean(payload)
    assert output == expected
    assert_safe_markdown(output)


def test_plain_text_and_math_keep_their_meaning():
    assert clean("a < b and c > d") == "a < b and c > d"
    assert clean("$x<y$ and $0<\\epsilon$") == "$x< y$ and $0<\\epsilon$"


def test_control_characters_and_line_endings_are_normalized():
    assert clean("a\x00b\x1bc\r\nd\re\u2028f") == "abc\nd\nef"


def test_legitimate_ocr_markup_is_preserved():
    source = (
        "## Chapter 1\n\nAccented text: “a naïve café résumé”, a façade, a phœnix.\n\n"
        '<div style="text-align: center;"><img src="imgs/fig.png" alt="Image" width="40%" /></div>\n\n'
        "<table border=1><tr><td colspan=2>Wood</td></tr><tr><td>Oak</td><td>H<sub>2</sub>O<br>x<sup>2</sup></td></tr></table>\n"
    )
    expected = (
        "## Chapter 1\n\nAccented text: “a naïve café résumé”, a façade, a phœnix.\n\n"
        '<div style="text-align: center;"><img src="../images/K_2.jpg" alt="Image" width="40%" /></div>\n\n'
        '<table border="1"><tr><td colspan="2">Wood</td></tr><tr><td>Oak</td><td>H<sub>2</sub>O<br />x<sup>2</sup></td></tr></table>\n'
    )
    assert clean(source) == expected


def test_oversized_markdown_is_refused():
    with pytest.raises(MarkdownTooLarge):
        clean("x" * (sanitize.MAX_MARKDOWN_BYTES + 1))


def test_very_long_tags_are_treated_as_text():
    output = clean("<div " + "a=b " * 10_000 + ">end")
    assert output.startswith("< div")
    assert_safe_markdown(output)


@pytest.mark.parametrize("name", ["img_in_image_box_93_1129_1104_1716.jpg", "a.png", "A-b_c.9"])
def test_safe_image_names(name):
    assert is_safe_image_name(name)


@pytest.mark.parametrize("name", ["", "..", "../x.jpg", "a/b.jpg", "a\\b.jpg", "x" * 129, "é.jpg", "a b.jpg", "a..jpg"])
def test_unsafe_image_names(name):
    assert not is_safe_image_name(name)


# -- fuzzing: random combinations of hostile fragments -------------------------------

_FRAGMENTS = [
    "<script>",
    "</script>",
    "<img",
    " src=",
    "imgs/a.jpg",
    '"',
    "'",
    " onerror=alert(1)",
    ">",
    "/>",
    "<",
    "<!--",
    "-->",
    "<svg",
    "<iframe",
    "</iframe>",
    "javascript:",
    "&#106;",
    "&lt;",
    "](",
    "![x]",
    "[y]",
    "(",
    ")",
    "]:",
    "\n",
    "\n\n",
    " ",
    "<div",
    ' style="text-align:center"',
    "<a href=",
    "<style>",
    "</style>",
    "<math>",
    "<table>",
    "<td colspan=2>",
    "`",
    "<!DOCTYPE",
    "<?",
    "</",
    "data:",
    "\t",
    "<p",
    "<b>",
    "</b>",
    "<br>",
    "text ",
    "<IMG SRC=",
    "<sCrIpT>",
    "<img/src=x/onerror=alert(1)>",
    "<<",
    "<x>",
    "</x>",
    "<!-- -->",
    "<!-->",
    "--!>",
    "img",
    "svg",
    "<plaintext>",
    "<xmp>",
    "\\",
    "$",
    "$$",
    "5 ",
    "^{m}",
    "<span class=math-inline>",
    "</span>",
]


def test_fuzzed_hostile_markdown_is_always_safe():
    rng = random.Random(20261012)
    for _ in range(3000):
        payload = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(1, 30)))
        output = clean(payload)
        assert_safe_markdown(output)
        assert_safe_html(render_markdown(output, FILES_URL))


# -- previews (preview.py) -----------------------------------------------------------


def test_preview_points_images_to_the_files_endpoint():
    html = render_markdown('![Figure](../images/K_1.jpg)\n\n<img src="images/K_2.jpg" alt="x" />', FILES_URL)
    assert f'src="{FILES_URL}/images/K_1.jpg"' in html
    assert f'src="{FILES_URL}/images/K_2.jpg"' in html
    assert_safe_html(html)


@pytest.mark.parametrize(
    "edited",
    [
        "<img src=x onerror=alert(1)>",
        '<a href="javascript:alert(1)">x</a>',
        "![x](https://evil.example/pixel.png)",
        "<script>alert(1)</script>",
        '<p style="background:url(https://evil.example)" class="x">x</p>',
        "[x](../../../../etc/passwd)",
    ],
)
def test_preview_cleans_hand_edited_page_files(edited):
    assert_safe_html(render_markdown(edited, FILES_URL))


def test_oversized_page_previews_are_plain_text():
    # markdown-it needed over a minute for 2 MiB of this; no OCR page is that long.
    markdown = "&#x" * (2 * 1024 * 1024 // 3) + "<script>alert(1)</script>"
    started = time.monotonic()
    html = render_markdown(markdown, FILES_URL)
    assert time.monotonic() - started < 5
    assert html.startswith('<pre class="markdown-source">&amp;#x&amp;#x')
    assert "<script" not in html and html.endswith("&lt;/script&gt;</pre>")
    assert render_markdown("x" * MAX_RENDERED_LENGTH, FILES_URL) == "<p>" + "x" * MAX_RENDERED_LENGTH + "</p>\n"


def test_document_preview_structure():
    pages = {"k1": "First text", "k2": "Second <b>text</b>", "k3": "No number", "k4": "Spread", "k5": "Preface"}
    sections = [
        PageSection("k1", "1"),
        GapSection(2, 4),
        PageSection("k2", "5"),
        GapSection(6, 6),
        PageSection("k4", "7–8"),
        PageSection("k5", "xii"),
        UnnumberedHeading(),
        PageSection("k3", None),
    ]
    html = render_document("Title <i>", sections, pages.__getitem__, FILES_URL)
    assert html.startswith("<h1>Title &lt;i&gt;</h1>")
    assert (
        '<section class="page" data-key="k1"><p class="page-marker" data-label="1">Page 1</p><p>First text</p>' in html
    )
    assert '<p class="missing-pages" data-range="2–4">Missing pages: 2–4</p>' in html
    assert '<p class="missing-pages" data-range="6">Missing page: 6</p>' in html
    assert '<p class="page-marker" data-label="7–8">Page 7–8</p>' in html
    assert '<p class="page-marker" data-label="xii">Page xii</p>' in html
    assert '<h2 class="unnumbered">Unnumbered pages</h2>' in html
    assert '<section class="page" data-key="k3"><p class="page-marker" data-label="">Unnumbered page</p>' in html


# -- formulas in previews (preview.py) -----------------------------------------------


class Formulas(HTMLParser):
    """Formulas marked in preview HTML, as ("display" or "inline", text), and the tags inside them."""

    KINDS = {("div", "math-display"): "display", ("span", "math-inline"): "inline"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str]] = []
        self.inner_tags: list[str] = []
        self.current: list[str] | None = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if self.current is not None:
            self.inner_tags.append(tag)
            self.depth += tag not in {"br", "hr", "img", "col"}
        elif kind := self.KINDS.get((tag, dict(attrs).get("class"))):
            self.current = [kind, ""]

    def handle_endtag(self, tag):
        if self.current is not None and self.depth:
            self.depth -= 1
        elif self.current is not None:
            self.found.append((self.current[0], self.current[1]))
            self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data


def parse_formulas(html: str) -> Formulas:
    parser = Formulas()
    parser.feed(html)
    parser.close()
    return parser


def formulas(html: str) -> list[tuple[str, str]]:
    parser = parse_formulas(html)
    assert parser.inner_tags == [], "markup inside a formula"
    return parser.found


def preview(markdown: str) -> str:
    html = render_markdown(markdown, FILES_URL)
    assert_safe_html(html)
    formulas(html)
    return html


def test_display_formulas_are_blocks():
    assert preview(r"$$\frac{a}{b}=\sqrt{x^2+1}$$") == r'<div class="math-display">\frac{a}{b}=\sqrt{x^2+1}</div>'
    # As PaddleOCR-VL writes them: spaces inside the dollars.
    html = preview(r" $$ \begin{array}{c|c}{X=1}&{X=2,5}\\ {Y=7,5&{Y=8} \end{array} $$ " + "\n\nNext.")
    assert html == (
        r'<div class="math-display">\begin{array}{c|c}{X=1}&amp;{X=2,5}\\ {Y=7,5&amp;{Y=8} \end{array}</div>'
        "<p>Next.</p>\n"
    )


def test_a_display_formula_ends_the_paragraph_it_is_in():
    assert preview("before $$x$$ after") == '<p>before </p><div class="math-display">x</div><p> after</p>\n'
    assert preview(r"\( x_1 \) and \[ y^2 \]") == (
        '<p><span class="math-inline">x_1</span> and </p><div class="math-display">y^2</div>'
    )
    assert preview("- $$x$$\n- b") == '<ul>\n<li><div class="math-display">x</div></li>\n<li>b</li>\n</ul>\n'
    # In bold text, the HTML parser re-opens <strong> inside the formula: its text is still the TeX.
    html = render_markdown("**bold $$x$$ end**", FILES_URL)
    assert html == (
        '<p><strong>bold </strong></p><div class="math-display"><strong>x</strong></div><p><strong> end</strong></p>\n'
    )
    assert parse_formulas(html).found == [("display", "x")]


def test_multi_line_formulas_are_not_read_as_markdown():
    tex = "\\begin{aligned}\na &= b * c \\\\\n- d &= e_1 * f_2\n\\end{aligned}"
    html = preview(f"Let\n$$\n{tex}\n$$\nso *done*.")
    assert formulas(html) == [("display", tex)]
    assert html.startswith('<p>Let\n</p><div class="math-display">')
    assert html.endswith("</div><p>\nso <em>done</em>.</p>\n")


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("Résumé: $E=mc^2$.", '<p>Résumé: <span class="math-inline">E=mc^2</span>.</p>\n'),
        ("## Law $ F = ma $", '<h2>Law <span class="math-inline">F = ma</span></h2>\n'),
        # PaddleOCR-VL: spaces inside the dollars, units of old books after numbers (18ᵗʰ,140; 0ᵐ,385).
        ("pounds (18 $ ^{th} $, 140)", '<p>pounds (18 <span class="math-inline">^{th}</span>, 140)</p>\n'),
        (
            "<table><tr><td>0 $ ^{m} $,385</td><td>$ 0m,385 $</td></tr></table>",
            '<table><tbody><tr><td>0 <span class="math-inline">^{m}</span>,385</td>'
            '<td><span class="math-inline">0m,385</span></td></tr></tbody></table>',
        ),
    ],
)
def test_inline_formulas(markdown, expected):
    assert preview(markdown) == expected


def test_tex_reaches_the_web_ui_unchanged():
    tex = r"a_1 * b_2 = c_{n}^{*} \\ \{x\} \& \$ x & y \_ < 3"
    assert formulas(preview(f"${tex}$ and $${tex}$$")) == [("inline", tex), ("display", tex)]
    # The text of HTML table cells is escaped (PaddleOCR-VL's too): the TeX is what a browser reads.
    assert formulas(preview("<table><tr><td>$ a &lt; b &amp;&amp; c $</td></tr></table>")) == [("inline", "a < b && c")]


@pytest.mark.parametrize(
    "text",
    [
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
)
def test_dollars_that_are_not_formulas(text):
    html = preview(text)
    assert formulas(html) == [] and html.count("$") == text.count("$")


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("$a\n\nb$", "<p>$a</p>\n<p>b$</p>\n"),
        (
            "<table><tr><td>$ a</td><td>b $</td></tr></table>",
            "<table><tbody><tr><td>$ a</td><td>b $</td></tr></tbody></table>",
        ),
        ("`$x$` and `a $b` c$", "<p><code>$x$</code> and <code>a $b</code> c$</p>\n"),
        ("```\n$x$ and $$y$$\n```", "<pre><code>$x$ and $$y$$\n</code></pre>\n"),
        ("![figure $x$](../images/K_1.jpg)", f'<p><img src="{FILES_URL}/images/K_1.jpg" alt="figure $x$"></p>\n'),
    ],
)
def test_formulas_stay_in_a_paragraph_or_cell_and_out_of_code_and_attributes(markdown, expected):
    assert preview(markdown) == expected


@pytest.mark.parametrize(
    "tex",
    [
        r"\href{javascript:alert(1)}{click}",
        r"\url{https://evil.example}",
        r"\htmlClass{evil}{x}",
        r"\htmlStyle{background:url(https://evil.example)}{x}",
        r"\includegraphics{https://evil.example/p.png}",
    ],
)
def test_hostile_tex_is_text(tex):
    # Typeset by KaTeX with trust: false (web UI): no link, class, style or image comes of it.
    html = preview(f"Formula: ${tex}$")
    assert formulas(html) == [("inline", tex)]
    assert [tag for tag, _ in markup(html).tags] == ["p", "span"]


def test_markup_in_a_formula_stays_text():
    payload = "</span><script>alert(1)</script><span>"
    html = preview("$" + payload.replace("<", "&lt;").replace(">", "&gt;") + "$")
    assert formulas(html) == [("inline", payload)]
    assert [tag for tag, _ in markup(html).tags] == ["p", "span"]
    # As markup, it makes no formula (formulas hold no tag), and the sanitizers remove it.
    for markdown in (f"$x{payload}$", clean(f"$x{payload}$")):
        html = preview(markdown)
        assert formulas(html) == [] and "script" not in html


def test_placeholders_of_formulas_cannot_be_forged():
    assert preview("\ufdd00\ufdd1 and $y$ \ufdd1") == '<p>0 and <span class="math-inline">y</span></p>\n'


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ('<div class="math-display">x</div>', '<div class="math-display">x</div>'),
        ('<span class="math-inline">x</span>', '<p><span class="math-inline">x</span></p>\n'),
        ('<div class="math-inline">x</div>', "<div>x</div>"),
        ('<span class="math-display">x</span>', "<p><span>x</span></p>\n"),
        ('<div class="math-display evil">x</div>', "<div>x</div>"),
        ('<p class="math-inline">x</p>', "<p>x</p>"),
        ('<span class="katex">x</span>', "<p><span>x</span></p>\n"),
        ('<table><tr><td class="math-inline">x</td></tr></table>', "<table><tbody><tr><td>x</td></tr></tbody></table>"),
    ],
)
def test_previews_keep_no_class_but_the_marks_of_formulas(markdown, expected):
    assert preview(markdown) == expected


def test_formulas_of_a_paddleocr_vl_page():
    # Synthetic text shaped like a real PaddleOCR-VL result on an old printed page: units written as
    # superscripts after numbers, spaces inside the dollars, a table whose cells carry inline styles.
    page = (
        "a sample crate of forty pounds (18 $ ^{th} $, 140) placed on the scale of the café\n\n"
        "<table border=1><tr><td style='text-align: center; word-wrap: break-word;'>Width of the shelf</td>"
        "<td style='text-align: center; word-wrap: break-word;'>0 $ ^{m} $,385</td></tr>"
        '<tr><td>Area of the floor</td><td colspan="2">$ 42mq.17 $</td></tr></table>\n'
    )
    assert formulas(preview(clean(page))) == [("inline", "^{th}"), ("inline", "^{m}"), ("inline", "42mq.17")]


def test_fuzzed_formulas_are_well_formed():
    fragments = [
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
    ]
    rng = random.Random(20261013)
    for _ in range(2000):
        payload = "".join(rng.choice(fragments) for _ in range(rng.randint(1, 30)))
        for markdown in (payload, clean(payload)):
            html = render_markdown(markdown, FILES_URL)
            assert_safe_html(html)
            assert "\ufdd0" not in html and "\ufdd1" not in html
            # A display formula interrupting bold or italic text ("*$$x$$*") gets
            # them re-opened inside it by the HTML parser; KaTeX replaces them.
            inner_tags = parse_formulas(html).inner_tags
            assert set(inner_tags) <= {"a", "b", "code", "em", "i", "s", "small", "strike", "strong", "u"}, html


def test_hostile_dollars_are_marked_quickly():
    for payload in ("\\[", "\\(", "$ a ", "5 $ ", "$$ a <b> ", "<code>$x$", "<a", "` $", "$x$ "):
        started = time.monotonic()
        render_markdown(payload * (MAX_RENDERED_LENGTH // len(payload)), FILES_URL)
        assert time.monotonic() - started < 5, payload
