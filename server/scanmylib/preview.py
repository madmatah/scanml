r"""HTML previews of page and document Markdown for the web UI.

The Markdown on disk is already sanitized (see sanitize.py); it is rendered
with markdown-it and filtered again through an allowlist sanitizer (nh3), so
that a hand-edited page file cannot inject markup either. Image references
(``images/…`` or ``../images/…``) are rewritten to the document's file
endpoint; every other URL is dropped.

LaTeX formulas are marked for the web UI, which typesets them with KaTeX:
``<div class="math-display">`` for ``$$…$$`` and ``\[…\]``,
``<span class="math-inline">`` for ``$…$`` and ``\(…\)``, with the TeX as
text. They are set aside before markdown-it reads the page, so that ``_``,
``*`` or ``\\`` in TeX are not taken for Markdown. A formula stays within a
paragraph and holds no HTML tag and no backtick (nor, for ``$…$``, another
unescaped ``$``); in code and in attribute values it is shown as written.

PaddleOCR-VL puts spaces inside the dollars of inline formulas, which often
follow a number (``18 $ ^{th} $, 140``). So that amounts stay text, a pair of
dollars is not a formula when the inside of only one of them is blank
(``$5 and $10``), when the second one precedes a number (``$ 5 or $ 10``,
``10 $ or $5``), or when both follow one (``5 $ and 10 $``).
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import nh3
from markdown_it import MarkdownIt

from .assemble import GapSection, PageSection, Section, UnnumberedHeading

_markdown = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])

_TAGS = {
    "p", "br", "hr", "div", "span", "center",
    "b", "strong", "i", "em", "u", "s", "strike", "del", "ins",
    "sub", "sup", "small", "mark", "code", "pre", "kbd", "samp", "var",
    "blockquote", "q", "cite", "abbr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "img", "figure", "figcaption", "a",
}
_ATTRIBUTES = {
    "*": {"align"},
    "div": {"class"},
    "span": {"class"},
    "img": {"src", "alt", "width", "height"},
    "a": {"href", "title"},
    "td": {"colspan", "rowspan", "valign"},
    "th": {"colspan", "rowspan", "valign"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start"},
}
#: The only class kept on each tag: the mark of a formula (see _Formula).
_FORMULA_CLASSES = {"div": "math-display", "span": "math-inline"}
_IMAGE_REFERENCE = re.compile(r"(?:\.\./)?images/([A-Za-z0-9_-][A-Za-z0-9._-]*\.jpg)")

#: Longer page Markdown is shown as plain text: markdown-it is superlinear on
#: some hostile input (a minute for 2 MiB), while a dense OCR page is ~10 KB.
MAX_RENDERED_LENGTH = 128 * 1024

# One character of a formula: not an unescaped "$", a backtick, a tag or a blank line.
_FORMULA_CHARACTER = r"(?:[^$\\`<\n]|\\[^\n]|<(?![A-Za-z/!?])|\n(?![ \t]*\n))"
# "\[" and "\(" do not occur inside their own formulas: a search for the end
# of one stops at the next, so that unclosed ones cost linear time.
_FORMULA = re.compile(
    r"<[A-Za-z/!?][^<>]*>"  # a tag: a "$" in an attribute value is not math
    rf"|\$\$(?P<display>(?:{_FORMULA_CHARACTER}|\$(?!\$))+?)\$\$"
    rf"|\\\[(?P<display_brackets>(?:(?!\\\[){_FORMULA_CHARACTER}|\$)+?)\\\]"
    rf"|\\\((?P<inline_parentheses>(?:(?!\\\(){_FORMULA_CHARACTER}|\$)+?)\\\)"
    r"|\\[^\n]|\$\$"  # an escaped character, a "$$" that opens no formula: text
    rf"|\$(?P<inline>{_FORMULA_CHARACTER}+?)\$"
)
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")
_BLANKS = " \t\u00a0\u202f"
# While markdown-it renders a page, formula n is replaced by "\ufdd0n\ufdd1":
# Unicode noncharacters, deleted from the page beforehand.
_NONCHARACTERS = {0xFDD0: None, 0xFDD1: None}
_PLACEHOLDER = re.compile("\ufdd0([0-9]+)\ufdd1")
_RENDERED = re.compile("<(/?)([A-Za-z0-9]+)[^>]*>|\ufdd0([0-9]+)\ufdd1")
_EMPTY_PARAGRAPH = re.compile(r"<p>\s*</p>\n?")


@dataclass(frozen=True)
class _Formula:
    source: str  # as written in the Markdown, delimiters included
    tex: str
    display: bool

    def element(self) -> str:
        tag = "div" if self.display else "span"
        return f'<{tag} class="{_FORMULA_CLASSES[tag]}">{html.escape(self.tex)}</{tag}>'


def render_markdown(markdown: str, files_url: str) -> str:
    """Safe HTML for sanitized Markdown of one document.

    `files_url` is the URL of the document's files endpoint
    (``/api/documents/<id>/files``).
    """
    if len(markdown) > MAX_RENDERED_LENGTH:
        return f'<pre class="markdown-source">{html.escape(markdown)}</pre>'

    def keep_attribute(tag: str, attribute: str, value: str) -> str | None:
        if (tag, attribute) in {("img", "src"), ("a", "href")}:
            match = _IMAGE_REFERENCE.fullmatch(value)
            return f"{files_url}/images/{match[1]}" if match else None
        if attribute == "class":
            return value if value == _FORMULA_CLASSES.get(tag) else None
        return value

    text, formulas = _set_formulas_aside(markdown)
    return nh3.clean(
        _insert_formulas(_markdown.render(text), formulas),
        tags=_TAGS,
        attributes=_ATTRIBUTES,
        attribute_filter=keep_attribute,
        url_schemes=set(),
        strip_comments=True,
        link_rel="noopener noreferrer",
    )


def _set_formulas_aside(markdown: str) -> tuple[str, list[_Formula]]:
    """Replace the formulas of `markdown` with placeholders (rules: see the module docstring)."""
    text = markdown.replace("\r\n", "\n").replace("\r", "\n").translate(_NONCHARACTERS)
    parts: list[str] = []
    formulas: list[_Formula] = []
    pos = 0
    while (match := _FORMULA.search(text, pos)) is not None:
        kind = match.lastgroup
        if kind is None:  # a tag, an escaped character, a lone "$$"
            parts.append(text[pos : match.end()])
            pos = match.end()
            continue
        tex = _ENTITY.sub(lambda entity: html.unescape(entity[0]), match[kind]).strip()
        if not tex or (kind == "inline" and not _is_inline_formula(text, match)):
            parts.append(text[pos : match.start() + 1])  # the opening "$" or "\" is text
            pos = match.start() + 1
            continue
        parts += [text[pos : match.start()], f"\ufdd0{len(formulas)}\ufdd1"]
        formulas.append(_Formula(match[0], tex, display=kind.startswith("display")))
        pos = match.end()
    parts.append(text[pos:])
    return "".join(parts), formulas


def _is_inline_formula(text: str, match: re.Match[str]) -> bool:
    """Whether a "$…$" match is a formula rather than text with amounts in dollars."""
    inside = match["inline"]
    opening, closing = match.start(), match.end() - 1
    return (
        inside[0].isspace() == inside[-1].isspace()
        and not _number_after(text, closing + 1)
        and not (_number_before(text, opening) and _number_before(text, closing))
    )


def _number_before(text: str, index: int) -> bool:
    """Whether `text` has a digit just before `index`, spaces aside."""
    while index > 0 and text[index - 1] in _BLANKS:
        index -= 1
    return index > 0 and "0" <= text[index - 1] <= "9"


def _number_after(text: str, index: int) -> bool:
    """Whether `text` has a digit from `index` on, spaces aside."""
    while index < len(text) and text[index] in _BLANKS:
        index += 1
    return index < len(text) and "0" <= text[index] <= "9"


def _insert_formulas(rendered: str, formulas: list[_Formula]) -> str:
    """Put the formulas set aside back into the HTML rendered by markdown-it.

    In code and in tags (attribute values), a formula is shown as written. A
    display formula is a block: the paragraph it is in ends before it and
    goes on after it.
    """
    inside = {"p": False, "code": False}

    def source(slot: re.Match[str]) -> str:
        return html.escape(formulas[int(slot[1])].source)

    def replace(match: re.Match[str]) -> str:
        closing, tag, index = match.groups()
        if index is None:
            if tag in inside:
                inside[tag] = not closing
            return _PLACEHOLDER.sub(source, match[0])
        formula = formulas[int(index)]
        if inside["code"]:
            return html.escape(formula.source)
        if formula.display and inside["p"]:
            return f"</p>{formula.element()}<p>"
        return formula.element()

    return _EMPTY_PARAGRAPH.sub("", _RENDERED.sub(replace, rendered))


def render_document(
    title: str,
    sections: Sequence[Section],
    page_markdown: Callable[[str], str],
    files_url: str,
) -> str:
    """Safe HTML of a whole document, page by page.

    Structure (for styling by the web UI): ``<h1>`` title, then for each page
    ``<section class="page" data-key="…"><p class="page-marker" data-label="42">Page 42</p>…</section>``
    (``data-label=""`` and "Unnumbered page" for a page without number); gaps in
    the numbering appear as ``<p class="missing-pages" data-range="13–44">Missing pages: 13–44</p>``
    and unnumbered pages follow an ``<h2 class="unnumbered">Unnumbered pages</h2>`` heading.
    These texts are English: the data attributes let the web UI show them in the user's language.
    """
    parts = [f"<h1>{html.escape(title)}</h1>"]
    for section in sections:
        if isinstance(section, PageSection):
            label = section.label or ""
            marker = f"Page {label}" if label else "Unnumbered page"
            body = render_markdown(page_markdown(section.key), files_url)
            parts.append(
                f'<section class="page" data-key="{html.escape(section.key)}">'
                f'<p class="page-marker" data-label="{html.escape(label)}">{html.escape(marker)}</p>{body}</section>'
            )
        elif isinstance(section, GapSection):
            parts.append(
                f'<p class="missing-pages" data-range="{html.escape(section.label)}">'
                f"{html.escape(section.description)}</p>"
            )
        elif isinstance(section, UnnumberedHeading):
            parts.append(f'<h2 class="unnumbered">{html.escape(section.text)}</h2>')
    return "\n".join(parts)
