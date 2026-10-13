"""Library files for agents (assemble.py): document.md, document.json, INDEX.md, library.json."""

from __future__ import annotations

import json

from scanmylib.assemble import (
    DocumentMeta,
    GapSection,
    IndexEntry,
    PageEntry,
    PageSection,
    UnnumberedHeading,
    document_relative,
    document_sections,
    render_document_markdown,
    render_document_metadata,
    render_index_markdown,
    render_index_metadata,
    source_label,
)
from scanmylib.ordering import Coverage, PageNumber

META = DocumentMeta(
    id="6f1c0000-0000-4000-8000-000000000001",
    slug="sample-cafe-guide",
    title='Sample "Café" Guide',
    author="Jane Doe",
    kind="book",
    notes="Volume 1",
    created_at="2026-10-12T20:00:00+02:00",
    updated_at="2026-10-12T21:00:00+02:00",
)


def entry(
    key: str,
    number: PageNumber | None,
    *,
    status: str = "done",
    in_document: bool = True,
    images: int = 0,
    placement: str | None = None,
    position: float | None = None,
) -> PageEntry:
    if placement is None and in_document:
        placement = "number" if number else "unplaced"
    return PageEntry(
        id=f"id-{key}",
        key=key,
        status=status,
        number=number,
        number_source="detected" if number else None,
        in_document=in_document,
        excluded=False,
        duplicate_of=None,
        position=position,
        placement=placement,
        session_id="s",
        seq=0,
        captured_at="2026-10-12T20:15:30+02:00",
        scan_file=f"scans/{key}.jpg",
        image_count=images,
        engine="PaddleOCR-VL-1.6" if status == "done" else None,
    )


def test_sections_mark_gaps_and_unnumbered_pages():
    reading = [
        entry("r", PageNumber(1, front_matter=True)),
        entry("a", PageNumber(1)),
        entry("b", PageNumber(2, 3)),
        entry("c", PageNumber(7)),
        entry("d", PageNumber(8)),
        entry("u", None),
    ]
    assert document_sections(reading, numbered=True) == [
        PageSection("r", "i"),
        PageSection("a", "1"),
        PageSection("b", "2–3"),
        GapSection(4, 6),
        PageSection("c", "7"),
        PageSection("d", "8"),
        UnnumberedHeading(),
        PageSection("u", None),
    ]
    assert (GapSection(4, 6).label, GapSection(4, 6).description) == ("4–6", "Missing pages: 4–6")
    assert (GapSection(9, 9).label, GapSection(9, 9).description) == ("9", "Missing page: 9")


def test_documents_without_numbers_have_no_unnumbered_heading():
    assert document_sections([entry("a", None), entry("b", None)], numbered=False) == [
        PageSection("a", None),
        PageSection("b", None),
    ]


def test_only_pages_that_could_not_be_placed_go_under_the_unnumbered_heading():
    reading = [
        entry("title", None, placement="session"),  # scanned just before page 1
        entry("a", PageNumber(1)),
        entry("plate", None, placement="session"),
        entry("map", None, placement="manual", position=1.5),
        entry("b", PageNumber(2)),
        entry("loose", None),
    ]
    assert document_sections(reading, numbered=True) == [
        PageSection("title", None),
        PageSection("a", "1"),
        PageSection("plate", None),
        PageSection("map", None),
        PageSection("b", "2"),
        UnnumberedHeading(),
        PageSection("loose", None),
    ]


def test_gaps_are_marked_before_the_page_that_follows_them_in_any_order():
    # Page 7 was moved by hand before page 2: pages 2–6 are not missing, page 5 is.
    reading = [
        entry("p1", PageNumber(1)),
        entry("p7", PageNumber(7), placement="manual", position=1.5),
        entry("p2", PageNumber(2)),
        entry("p3", PageNumber(3, 4)),
        entry("p6", PageNumber(6)),
        entry("pi", PageNumber(1, front_matter=True), placement="manual", position=6.5),
    ]
    assert document_sections(reading, numbered=True) == [
        PageSection("p1", "1"),
        PageSection("p7", "7"),
        PageSection("p2", "2"),
        PageSection("p3", "3–4"),
        GapSection(5, 5),
        PageSection("p6", "6"),
        PageSection("pi", "i"),
    ]


def test_document_markdown_format():
    pages = {
        "k1": 'Text.\n\n<div style="text-align: center;"><img src="../images/k1_1.jpg" alt="Image" /></div>\n',
        "k2": "![Map](../images/k2_1.jpg)\n",
        "k3": "",
    }
    sections = [PageSection("k1", "1"), GapSection(2, 44), PageSection("k2", "45"), UnnumberedHeading(), PageSection("k3", None)]
    coverage = Coverage(ranges=((1, 1), (45, 45)), unnumbered=1)
    markdown = render_document_markdown(
        META, sections, pages.__getitem__, source="ScanMyLib — OCR PaddleOCR-VL-1.6", pages_scanned=3, coverage=coverage
    )
    assert markdown == (
        "---\n"
        'title: "Sample \\"Café\\" Guide"\n'
        'author: "Jane Doe"\n'
        "kind: book\n"
        'source: "ScanMyLib — OCR PaddleOCR-VL-1.6"\n'
        "pages_scanned: 3\n"
        'coverage: "1, 45"\n'
        'missing: "2–44"\n'
        "updated: 2026-10-12T21:00:00+02:00\n"
        "---\n"
        "\n"
        '# Sample "Café" Guide\n'
        "\n"
        "<!-- page 1 · scan k1 -->\n"
        "\n"
        'Text.\n\n<div style="text-align: center;"><img src="images/k1_1.jpg" alt="Image" /></div>\n'
        "\n"
        "<!-- missing pages: 2–44 -->\n"
        "\n"
        "<!-- page 45 · scan k2 -->\n"
        "\n"
        "![Map](images/k2_1.jpg)\n"
        "\n"
        "## Unnumbered pages\n"
        "\n"
        "<!-- scan k3 -->\n"
    )


def test_user_text_cannot_inject_markup_or_break_the_front_matter():
    meta = DocumentMeta(**{**META.__dict__, "title": "<script>x</script>\n---\nkind: evil", "author": 'a"b'})
    markdown = render_document_markdown(meta, [], lambda key: "", source="ScanMyLib", pages_scanned=0,
                                        coverage=Coverage((), 0))
    front_matter = markdown.split("---\n")[1]
    assert 'title: "<script>x</script>\\n---\\nkind: evil"' in front_matter
    assert 'author: "a\\"b"' in front_matter
    assert "# &lt;script>x&lt;/script>" in markdown


def test_document_relative_only_touches_image_references():
    text = 'see ../images/ here ![x](../images/k_1.jpg) <img src="../images/k_2.jpg" />'
    assert document_relative(text) == 'see ../images/ here ![x](images/k_1.jpg) <img src="images/k_2.jpg" />'


def test_document_metadata_lists_pages_and_files():
    pages = [entry("k1", PageNumber(1), images=2), entry("k2", None, status="queued", in_document=False)]
    metadata = render_document_metadata(META, pages, source="S", pages_scanned=1, coverage=Coverage(((1, 1),), 0))
    json.dumps(metadata)  # serializable
    first, second = metadata["pages"]
    assert first["files"] == {
        "scan": "scans/k1.jpg", "markdown": "pages/k1.md", "ocr": "ocr/k1.json",
        "images": ["images/k1_1.jpg", "images/k1_2.jpg"],
    }
    assert first["label"] == "1" and first["in_document"]
    assert (first["position"], first["placement"]) == (None, "number")
    assert second["files"] == {"scan": "scans/k2.jpg", "markdown": None, "ocr": None, "images": []}
    assert (second["position"], second["placement"]) == (None, None)
    moved = render_document_metadata(META, [entry("k3", None, placement="manual", position=0.5)], source="S",
                                     pages_scanned=1, coverage=Coverage((), 1))["pages"][0]
    assert (moved["position"], moved["placement"]) == (0.5, "manual")
    assert metadata["coverage"]["label"] == "1"
    assert metadata["notes"] == "Volume 1"


def test_source_label():
    assert source_label(["PaddleOCR-VL-1.6", "PaddleOCR-VL-1.6"]) == "ScanMyLib — OCR PaddleOCR-VL-1.6"
    assert source_label(["B", "A"]) == "ScanMyLib — OCR A, B"
    assert source_label([]) == "ScanMyLib"


def test_index_is_sorted_and_escaped():
    entries = [
        IndexEntry(META, 3, Coverage(((1, 1), (45, 45)), 1)),
        IndexEntry(
            DocumentMeta(**{**META.__dict__, "slug": "a-b", "title": "Élan | [x] <b>", "author": "", "kind": "document"}),
            1,
            Coverage((), 1),
        ),
    ]
    markdown = render_index_markdown(entries, "2026-10-12T21:00:00+02:00")
    rows = [line for line in markdown.splitlines() if line.startswith("| [")]
    assert rows == [
        "| [Élan \\| \\[x\\] &lt;b>](a-b/document.md) |  | document | 1 |  |  |",
        '| [Sample "Café" Guide](sample-cafe-guide/document.md) | Jane Doe | book | 3 | 1, 45 | 2–44 |',
    ]
    assert "2 documents — index updated 2026-10-12T21:00:00+02:00." in markdown
    assert "1 document — index updated now." in render_index_markdown(entries[:1], "now")
    metadata = render_index_metadata(entries, "2026-10-12T21:00:00+02:00")
    assert [d["slug"] for d in metadata["documents"]] == ["a-b", "sample-cafe-guide"]
    assert metadata["documents"][1]["markdown"] == "sample-cafe-guide/document.md"


def test_empty_index():
    assert "_No documents yet._" in render_index_markdown([], "now")
    assert "0 documents — index updated now." in render_index_markdown([], "now")
    assert render_index_metadata([], "now") == {"generated_at": "now", "documents": []}
