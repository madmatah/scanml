"""Sanitization of the Markdown returned by the OCR sandbox (untrusted data).

The sandbox output is Markdown with embedded HTML (tables, centered figures).
`sanitize_markdown` turns it into Markdown that is safe to store and to open
in any Markdown viewer (docs/SECURITY.md):

* Every ``<`` that a browser could read as the start of markup is either part
  of a tag re-serialized from scratch here, or followed by an inserted space
  (``<`` + space is always text for an HTML tokenizer, and unlike ``&lt;`` it
  keeps formulas such as ``$x<y$`` readable). Tags are never copied verbatim,
  so parser differentials cannot smuggle markup.
* Only an allowlist of formatting tags survives, with an allowlist of
  attributes: no ``on*`` handlers, no URLs except the page's own images,
  ``style`` reduced to ``text-align``. Script-like elements (``script``,
  ``style``, ``iframe``, ``svg``…) are dropped with their content; other
  unknown tags are dropped but their text is kept. HTML comments are dropped
  (they could also fake the page markers of document.md).
* Markdown links, images and reference definitions may only target the page's
  own images; any other destination is neutralized (the text stays visible).
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable

from markdown_it import MarkdownIt

MAX_MARKDOWN_BYTES = 2 * 1024 * 1024

#: Maps an image reference written by the sandbox ("imgs/<name>") to the path
#: to store instead, or None when it does not designate one of the page images.
ImageResolver = Callable[[str], str | None]

_IMAGE_NAME = re.compile(r"[A-Za-z0-9._-]{1,128}")

_ALLOWED_TAGS = frozenset({
    "p", "br", "hr", "div", "span", "center",
    "b", "strong", "i", "em", "u", "s", "strike", "del", "ins",
    "sub", "sup", "small", "mark", "code", "pre", "kbd", "samp", "var",
    "blockquote", "q", "cite", "abbr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "img", "figure", "figcaption",
})
_VOID_TAGS = frozenset({"br", "hr", "img", "col"})
# Elements removed together with everything up to their closing tag: their
# content is code, raw text or foreign markup, never readable page text.
_DROP_WITH_CONTENT = frozenset({
    "script", "style", "template", "iframe", "object", "applet", "noscript",
    "noembed", "noframes", "xmp", "plaintext", "textarea", "title", "select",
    "svg", "math", "head", "audio", "video", "canvas", "frameset",
})
_ALIGN_VALUES = frozenset({"left", "right", "center", "justify"})
_VALIGN_VALUES = frozenset({"top", "middle", "bottom", "baseline"})
_DIGITS = re.compile(r"[0-9]{1,4}")
_DIMENSION = re.compile(r"[0-9]{1,5}(?:\.[0-9]+)?%?")
_TEXT_ALIGN = re.compile(r"text-align\s*:\s*(left|right|center|justify)\s*(?:;|$)", re.IGNORECASE)

_SPACE = "[ \t\n]"
_ATTRIBUTE_NAME = r"[^ \t\n\"'<>/=]+"
_ATTRIBUTE_VALUE = r"\"[^\"]*\"|'[^']*'|[^ \t\n\"'=<>`]+"
_TAG = re.compile(
    rf"<(?P<closing>/?)(?P<name>[A-Za-z][A-Za-z0-9-]*)"
    rf"(?P<attrs>(?:{_SPACE}+{_ATTRIBUTE_NAME}(?:{_SPACE}*={_SPACE}*(?:{_ATTRIBUTE_VALUE}))?)*)"
    rf"{_SPACE}*/?>"
)
_ATTRIBUTE = re.compile(
    rf"({_ATTRIBUTE_NAME})(?:{_SPACE}*={_SPACE}*(?:\"([^\"]*)\"|'([^']*)'|([^ \t\n\"'=<>`]+)))?"
)
# A tag longer than this is not something an OCR engine writes: treat as text.
_MAX_TAG_LENGTH = 16 * 1024

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029]")
# Destination of a Markdown link/image that designates a page image. (The
# "<imgs/…>" form never gets here: the HTML pass has already broken it.)
_IMAGE_DESTINATION = re.compile(r"[ \t]*(imgs/[A-Za-z0-9._-]{1,128})(?=[ \t\n)])")

# Parser used only to find reference definitions, whatever their URL
# (markdown-it ignores definitions with "unsafe" URLs, other renderers may not).
# Definitions are blocks: inline parsing, superlinear on some hostile input
# (2 MiB of "[" took a minute), is not needed to find them.
_reference_parser = MarkdownIt("commonmark")
_reference_parser.validateLink = lambda url: True  # type: ignore[method-assign]
_reference_parser.disable("inline")


class MarkdownTooLarge(ValueError):
    """The sandbox returned more Markdown than a page can plausibly contain."""


def is_safe_image_name(name: str) -> bool:
    """Image names accepted from the sandbox: ``[A-Za-z0-9._-]{1,128}`` without ``..``."""
    return bool(_IMAGE_NAME.fullmatch(name)) and ".." not in name


def sanitize_markdown(text: str, resolve_image: ImageResolver) -> str:
    """Return a safe version of untrusted Markdown, with image references resolved."""
    if len(text.encode("utf-8", "replace")) > MAX_MARKDOWN_BYTES:
        raise MarkdownTooLarge(f"markdown larger than {MAX_MARKDOWN_BYTES} bytes")
    text = _normalize(text)
    text = _sanitize_html(text, resolve_image)
    text = _neutralize_links(text, resolve_image)
    return _neutralize_reference_definitions(text)


def _normalize(text: str) -> str:
    """Valid UTF-8, LF line endings, no control characters (tab and newline kept)."""
    text = text.encode("utf-8", "replace").decode("utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHARACTERS.sub("", text)


def _sanitize_html(text: str, resolve_image: ImageResolver) -> str:
    out: list[str] = []
    pos, end = 0, len(text)
    while pos < end:
        lt = text.find("<", pos)
        if lt < 0:
            out.append(text[pos:])
            break
        out.append(text[pos:lt])
        if text.startswith("<!--", lt):
            close = text.find("-->", lt + 4)
            pos = end if close < 0 else close + 3
            continue
        match = _TAG.match(text, lt, min(end, lt + _MAX_TAG_LENGTH))
        if match is None:
            # A "<" before another "<" is separated too: if what follows is
            # removed (unknown tag, comment...), the "<" would otherwise be
            # joined to the text after it, e.g. "<<x></x>img onerror=...>".
            following = text[lt + 1 : lt + 2]
            opens_markup = following != "" and following.isascii() and (
                following.isalpha() or following in "/!?<"
            )
            out.append("< " if opens_markup else "<")
            pos = lt + 1
            continue
        pos = match.end()
        name = match["name"].lower()
        if match["closing"]:
            if name in _ALLOWED_TAGS and name not in _VOID_TAGS:
                out.append(f"</{name}>")
        elif name in _DROP_WITH_CONTENT:
            pos = _end_of_element(text, pos, name)
        elif name in _ALLOWED_TAGS:
            out.append(_rebuild_start_tag(name, match["attrs"], resolve_image))
    return "".join(out)


_closing_tag_patterns: dict[str, re.Pattern[str]] = {}


def _end_of_element(text: str, pos: int, name: str) -> int:
    """Index just after the closing tag of `name`, or the end of the text."""
    pattern = _closing_tag_patterns.get(name)
    if pattern is None:
        pattern = re.compile(rf"</{name}(?=[ \t\n/>])[^>]*>", re.IGNORECASE)
        _closing_tag_patterns[name] = pattern
    match = pattern.search(text, pos)
    return match.end() if match else len(text)


def _parse_attributes(raw: str) -> dict[str, str]:
    """Attribute names (lowercased) to entity-decoded values; the first occurrence wins."""
    attributes: dict[str, str] = {}
    for match in _ATTRIBUTE.finditer(raw):
        name = match[1].lower()
        if name in attributes:
            continue
        value = next((v for v in match.groups()[1:] if v is not None), "")
        attributes[name] = html.unescape(value)
    return attributes


def _rebuild_start_tag(name: str, raw_attributes: str, resolve_image: ImageResolver) -> str:
    """Serialize an allowed start tag with only the allowed, validated attributes."""
    source = _parse_attributes(raw_attributes)
    kept: list[tuple[str, str]] = []
    if name == "img":
        target = resolve_image(source.get("src", "").strip())
        if not target:
            return ""
        kept.append(("src", target))
        if "alt" in source:
            kept.append(("alt", " ".join(source["alt"].split())[:500]))
        for dimension in ("width", "height"):
            if _DIMENSION.fullmatch(source.get(dimension, "").strip()):
                kept.append((dimension, source[dimension].strip()))
    if name in {"td", "th"}:
        for span in ("colspan", "rowspan"):
            if _DIGITS.fullmatch(source.get(span, "").strip()):
                kept.append((span, source[span].strip()))
        if source.get("valign", "").strip().lower() in _VALIGN_VALUES:
            kept.append(("valign", source["valign"].strip().lower()))
    if name in {"col", "colgroup"} and _DIGITS.fullmatch(source.get("span", "").strip()):
        kept.append(("span", source["span"].strip()))
    if name == "table" and _DIGITS.fullmatch(source.get("border", "").strip()):
        kept.append(("border", source["border"].strip()))
    if name == "ol" and _DIGITS.fullmatch(source.get("start", "").strip()):
        kept.append(("start", source["start"].strip()))
    if source.get("align", "").strip().lower() in _ALIGN_VALUES:
        kept.append(("align", source["align"].strip().lower()))
    if (alignment := _TEXT_ALIGN.search(source.get("style", ""))) is not None:
        kept.append(("style", f"text-align: {alignment[1].lower()};"))

    rendered = "".join(f' {key}="{html.escape(value, quote=True)}"' for key, value in kept)
    return f"<{name}{rendered} />" if name in _VOID_TAGS else f"<{name}{rendered}>"


def _neutralize_links(text: str, resolve_image: ImageResolver) -> str:
    """Rewrite links/images to page images; break every other inline link.

    An inline link needs ``](`` with nothing in between, so escaping that
    parenthesis (``]\\(``) is enough to turn any other link back into text.
    """
    out: list[str] = []
    pos = 0
    while (bracket := text.find("](", pos)) >= 0:
        out.append(text[pos : bracket + 1])
        match = _IMAGE_DESTINATION.match(text, bracket + 2)
        target = resolve_image(match[1]) if match else None
        if match and target:
            out.append(f"({target}")
            pos = match.end()
        else:
            out.append("\\(")
            pos = bracket + 2
    out.append(text[pos:])
    return "".join(out)


def _neutralize_reference_definitions(text: str) -> str:
    """Turn reference definitions (``[label]: url``) into plain text.

    OCR output has no legitimate use for them, so as soon as one exists every
    ``]:`` is escaped, which a definition cannot survive.
    """
    env: dict = {}
    _reference_parser.parse(text, env)
    if not env.get("references"):
        return text
    return text.replace("]:", "]\\:")
