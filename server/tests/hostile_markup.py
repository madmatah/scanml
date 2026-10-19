"""Hostile markup for the tests of the sanitizer and of the previews: random payloads, a page sanitized with its images,
and what a browser reads as markup in it."""

from __future__ import annotations

import random
from collections.abc import Sequence
from html.parser import HTMLParser
from types import MappingProxyType

from scanmylib.sanitize import sanitize_markdown

PAGE_IMAGES = MappingProxyType({"a.jpg": "../images/K_1.jpg", "fig.png": "../images/K_2.jpg"})
HOSTILE_PAYLOAD_COUNT = 3000
_HOSTILE_SEED = 20261012
_HOSTILE_FRAGMENTS = (
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
)


class MarkupCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, list[tuple[str, str | None]]]] = []
        self.non_tag_markup: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, attrs))

    handle_startendtag = handle_starttag

    def handle_comment(self, data: str) -> None:
        self.non_tag_markup.append(f"comment:{data}")

    def handle_decl(self, decl: str) -> None:
        self.non_tag_markup.append(f"decl:{decl}")

    def handle_pi(self, data: str) -> None:
        self.non_tag_markup.append(f"pi:{data}")

    def unknown_decl(self, data: str) -> None:
        self.non_tag_markup.append(f"unknown:{data}")


def _resolve_page_image(reference: str) -> str | None:
    name = reference.removeprefix("imgs/")
    return PAGE_IMAGES.get(name) if reference.startswith("imgs/") else None


def sanitize_page(text: str) -> str:
    return sanitize_markdown(text, _resolve_page_image)


def parse_markup(text: str) -> MarkupCollector:
    parser = MarkupCollector()
    parser.feed(text)
    parser.close()
    return parser


def generate_payloads(fragments: Sequence[str], count: int, seed: int) -> list[str]:
    random_generator = random.Random(seed)
    return [
        "".join(random_generator.choice(fragments) for _ in range(random_generator.randint(1, 30)))
        for _ in range(count)
    ]


def generate_hostile_payloads() -> list[str]:
    return generate_payloads(_HOSTILE_FRAGMENTS, HOSTILE_PAYLOAD_COUNT, _HOSTILE_SEED)
