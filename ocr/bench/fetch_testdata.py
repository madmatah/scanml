"""Download the OCR test pages and their ground-truth transcriptions.

Pages come from public-domain books digitized on Wikimedia Commons (page
images rendered from the DjVu scans); the reference text is the proofread
transcription of the same page on Wikisource. Which books and pages make up
the test set is not part of the repository: ``<testdata>/sources.json`` lists
them, in this format::

    {
      "user_agent": "<User-Agent of the requests, with a contact address (Wikimedia policy)>",
      "wikisources": {
        "<language code>": {
          "file_namespaces": ["<local names of the File namespace, besides File and Image>"],
          "templates": {"<template name, lowercase>": <rule>}
        }
      },
      "books": {
        "<book id>": {
          "title": "<citation of the book, shown in SOURCES.md>",
          "commons_file": "<name of the book's DjVu file on Wikimedia Commons>",
          "wikisource": "<language code of the Wikisource that transcribes it>",
          "printed_page_offset": <page number in the DjVu file minus printed page number>
        }
      },
      "pages": [
        {
          "id": "<page id: name of its files, e.g. originals/<id>.jpg>",
          "book": "<book id>",
          "djvu_page": <page number in the DjVu file>,
          "content": "<what the page holds, shown in SOURCES.md>",
          "spine": "<left or right>", "variants": ["<photo variant>"]  (see make_photo_variants.py)
        }
      ]
    }

``user_agent``, ``wikisources``, ``content``, ``spine`` and ``variants`` are
optional. A template rule tells how wikitext_to_text reads the templates of a
Wikisource: ``"drop"`` (no text), ``"first"`` (its first positional argument,
the rule of the templates not listed), ``"space"`` (its first argument, else a
space), ``"word_start"`` (a word cut at the end of the page: the first
argument and a hyphen), ``"word_end"`` (a word started on the previous page:
the second argument), or ``{"row": ["<argument name>", ...]}`` (one row of a
table: these named arguments, then a line break).

Writes, under the test-data directory:

    originals/<page>.jpg     page image, 3840 px wide
    groundtruth/<page>.wiki  Wikisource wikitext of the page (as fetched)
    groundtruth/<page>.txt   plain reading text derived from it (see wikitext_to_text)
    pages.json               metadata: source, printed page number, URLs, license
    SOURCES.md               human-readable provenance and licenses

Run on the host with the system interpreter (stdlib only, network needed):

    python3 -I ocr/bench/fetch_testdata.py "$DATA_DIR/testdata"   # DATA_DIR: the stack's data directory (.env)
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_USER_AGENT = "ScanMyLib-testdata/0.1 (OCR evaluation)"
IMAGE_WIDTH = 3840  # one of the thumbnail sizes Wikimedia serves
SOURCES_FILE = "sources.json"
TEMPLATE_RULES = {"drop", "first", "space", "word_start", "word_end"}
_LANGUAGE_CODE = re.compile(r"[a-z]{2,3}(?:-[a-z]+)*")


def load_sources(testdata: Path) -> dict[str, Any]:
    """The test set described by ``<testdata>/sources.json`` (format: see the module docstring)."""
    path = testdata / SOURCES_FILE
    if not path.is_file():
        sys.exit(f"{path} not found: it lists the books and pages of the test set (see {Path(__file__).name})")
    sources: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    for language, rules in sources.get("wikisources", {}).items():
        for name, rule in rules.get("templates", {}).items():
            if isinstance(rule, dict) and isinstance(rule.get("row"), list):
                continue
            if not isinstance(rule, str) or rule not in TEMPLATE_RULES:
                raise ValueError(f"wikisources.{language}: unknown rule for template {name!r}: {rule!r}")
    for book_id, book in sources["books"].items():
        if not _LANGUAGE_CODE.fullmatch(book["wikisource"]):
            raise ValueError(f"books.{book_id}: invalid Wikisource language code {book['wikisource']!r}")
    for page in sources["pages"]:
        if page["book"] not in sources["books"]:
            raise ValueError(f"page {page['id']}: unknown book {page['book']!r}")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", page["id"]):
            raise ValueError(f"invalid page id {page['id']!r}: letters, digits, '_' and '-' only")
    return sources


def http_get(url: str, params: dict[str, str] | None = None, *, user_agent: str) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        body: bytes = response.read()
        return body


def _strip_html(value: str | None) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value or "").split())


def commons_file_info(file_name: str, page: int, *, user_agent: str) -> dict[str, str]:
    data = json.loads(http_get("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "format": "json", "titles": f"File:{file_name}",
        "prop": "imageinfo", "iiprop": "url|extmetadata",
    }, user_agent=user_agent))  # fmt: skip
    info = next(iter(data["query"]["pages"].values()))["imageinfo"][0]
    meta = info.get("extmetadata", {})
    # https://upload.wikimedia.org/wikipedia/commons/a/ab/<name>
    #   -> .../commons/thumb/a/ab/<name>/page<N>-<W>px-<name>.jpg
    original = info["url"].split("?")[0]
    name = original.rsplit("/", 1)[1]
    thumb = original.replace("/commons/", "/commons/thumb/", 1) + f"/page{page}-{IMAGE_WIDTH}px-{name}.jpg"
    return {
        "thumb_url": thumb,
        "file_page": info["descriptionurl"],
        "license": _strip_html(meta.get("LicenseShortName", {}).get("value")),
        "artist": _strip_html(meta.get("Artist", {}).get("value")),
        "credit": _strip_html(meta.get("Credit", {}).get("value")),
    }


def wikisource_page(language: str, title: str, *, user_agent: str) -> tuple[str, str]:
    data = json.loads(http_get(f"https://{language}.wikisource.org/w/api.php", {
        "action": "query", "format": "json", "formatversion": "2", "titles": title,
        "prop": "revisions|proofread", "rvprop": "content", "rvslots": "main",
    }, user_agent=user_agent))  # fmt: skip
    page = data["query"]["pages"][0]
    return page["revisions"][0]["slots"]["main"]["content"], page.get("proofread", {}).get("quality_text", "")


_TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")


def _render_template(match: re.Match[str], templates: dict[str, str | dict[str, list[str]]]) -> str:
    name, *args = [part.strip() for part in match.group(1).split("|")]
    positional = [arg for arg in args if "=" not in arg]
    named = dict(arg.split("=", 1) for arg in args if "=" in arg)
    rule = templates.get(name.lower(), "first")
    if isinstance(rule, dict):  # one row of a table, e.g. a label and a page number joined by dots
        return " ".join(named.get(argument, "") for argument in rule["row"]) + "\n"
    if rule == "drop":
        return ""
    if rule == "space":
        return " " if not positional else positional[0]
    if rule == "word_start":  # first half of a word cut at the end of this page
        return f"{positional[0]}-" if positional else ""
    if rule == "word_end":  # second half of a word started on the previous page
        return positional[1] if len(positional) > 1 else ""
    # "first": e.g. a correction template {{name|as printed|corrected}}: OCR should read the print.
    return positional[0] if positional else ""


def _table_cell_text(line: str) -> str:
    """Content of a wiki-table line (``| attrs | content``); structure lines give nothing."""
    if line.startswith(("{|", "|-", "|}", "|+")):
        return ""
    cell = line[1:]
    attributes, separator, content = cell.partition("|")
    return content if separator and "=" in attributes else cell


def wikitext_to_text(wikitext: str, rules: dict[str, Any] | None = None) -> str:
    """Reading text of a Wikisource page: body and tables; no running header, notes or images.

    `rules`: the ``wikisources`` entry of sources.json for the page's Wikisource.
    """
    rules = rules or {}
    templates = rules.get("templates", {})
    names = dict.fromkeys(["File", *rules.get("file_namespaces", []), "Image"])
    namespaces = "|".join(re.escape(name) for name in names)
    text = re.sub(r"<noinclude>.*?</noinclude>", " ", wikitext, flags=re.S)
    text = re.sub(r"<includeonly>.*?</includeonly>", " ", text, flags=re.S)
    text = re.sub(r"<ref[^>/]*>.*?</ref>|<ref[^>]*/>", " ", text, flags=re.S)
    text = re.sub(rf"\[\[(?:{namespaces}):(?:[^\[\]]|\[\[[^\]]*\]\])*\]\]", " ", text, flags=re.I)
    for _ in range(5):  # nested templates, innermost first
        text, count = _TEMPLATE.subn(lambda match: _render_template(match, templates), text)
        if not count:
            break
    text = "\n".join(_table_cell_text(line) if line.startswith(("{|", "|", "!")) else line for line in text.split("\n"))
    text = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"^=+\s*(.*?)\s*=+\s*$", r"\1", text, flags=re.M)
    text = text.replace("&nbsp;", " ").replace("__NOEDITSECTION__", "")
    paragraphs = [" ".join(chunk.split()) for chunk in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paragraphs if p) + "\n"


def main(testdata: Path) -> None:
    sources = load_sources(testdata)
    user_agent = sources.get("user_agent") or DEFAULT_USER_AGENT
    for sub in ("originals", "groundtruth"):
        (testdata / sub).mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for page in sources["pages"]:
        page_id, djvu_page = page["id"], page["djvu_page"]
        book = sources["books"][page["book"]]
        language = book["wikisource"]
        info = commons_file_info(book["commons_file"], djvu_page, user_agent=user_agent)
        image_path = testdata / "originals" / f"{page_id}.jpg"
        if not image_path.exists():
            image_path.write_bytes(http_get(info["thumb_url"], user_agent=user_agent))
            time.sleep(1)
        wiki_title = f"Page:{book['commons_file']}/{djvu_page}"
        wiki_url = f"https://{language}.wikisource.org/wiki/" + urllib.parse.quote(wiki_title.replace(" ", "_"))
        wikitext, quality = wikisource_page(language, wiki_title, user_agent=user_agent)
        text = wikitext_to_text(wikitext, sources.get("wikisources", {}).get(language))
        (testdata / "groundtruth" / f"{page_id}.wiki").write_text(wikitext, encoding="utf-8")
        (testdata / "groundtruth" / f"{page_id}.txt").write_text(text, encoding="utf-8")
        records.append({
            "page": page_id,
            "book": book["title"],
            "djvu_page": djvu_page,
            "printed_page": str(djvu_page - book["printed_page_offset"]),
            "content": page.get("content", ""),
            "image_url": info["thumb_url"],
            "commons_file": info["file_page"],
            "license": info["license"],
            "author": info["artist"],
            "digitization": info["credit"],
            "groundtruth_url": wiki_url,
            "groundtruth_quality": quality,
        })  # fmt: skip
        print(f"{page_id}: printed page {records[-1]['printed_page']}, {info['license']}, Wikisource: {quality}")
        time.sleep(1)
    (testdata / "pages.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_sources(testdata, records)


def write_sources(testdata: Path, records: list[dict[str, object]]) -> None:
    lines = [
        "# OCR test set — sources and licenses",
        "",
        "Pages of public-domain books, digitized and published on Wikimedia Commons (DjVu scans).",
        f"The images are the {IMAGE_WIDTH} px renderings of the DjVu pages served by Wikimedia. The",
        "reference text (`groundtruth/*.wiki`, `*.txt`) is the proofread transcription of the page on",
        "Wikisource (CC BY-SA 4.0, Wikisource contributors).",
        "",
        "Derived files (made by `ocr/bench/make_photo_variants.py`, see `variants.json`): `pages/` =",
        'clean "scanner" version (2480 px wide), `photos/` = simulated phone photos (perspective,',
        "binding curvature, uneven lighting, 90° rotation).",
        "",
        "| Page | Book | Printed page | Content | Image | License | Reference |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in records:
        lines.append(
            f"| `{record['page']}` | {record['book']} | {record['printed_page']} | {record['content']} "
            f"| [image]({record['image_url']}) ([Commons file]({record['commons_file']})) "
            f"| {record['license']} | [Wikisource]({record['groundtruth_url']}) ({record['groundtruth_quality']}) |"
        )
    digitization_credits = sorted({f"- {r['book']}: {r['digitization']}" for r in records})
    lines += ["", "Original digitization (according to Commons):", "", *digitization_credits, ""]
    (testdata / "SOURCES.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
