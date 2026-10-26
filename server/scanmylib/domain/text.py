"""Small text helpers: user-entered strings, slugs, collation."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_SLUG_MAX_LENGTH = 60


def single_line(value: str) -> str:
    """Trimmed text on one line: control characters removed, whitespace collapsed."""
    return " ".join(_CONTROL.sub(" ", value).split())


def multi_line(value: str) -> str:
    """Trimmed multi-line text: LF line endings, other control characters removed."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]", "", value).strip()


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def slugify(title: str) -> str:
    """Folder name for a title: lowercase ASCII words joined by dashes."""
    ascii_title = _strip_accents(title).lower()
    for letter, replacement in (("œ", "oe"), ("æ", "ae"), ("ß", "ss")):
        ascii_title = ascii_title.replace(letter, replacement)
    slug = _NON_SLUG.sub("-", ascii_title).strip("-")
    if len(slug) > _SLUG_MAX_LENGTH:
        slug = slug[:_SLUG_MAX_LENGTH].rsplit("-", 1)[0] or slug[:_SLUG_MAX_LENGTH]
    return slug or "document"


def collation_key(value: str) -> str:
    """Case- and accent-insensitive sort key (good enough for French titles)."""
    return _strip_accents(value).casefold()
