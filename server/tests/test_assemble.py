"""Library files for agents (assemble.py): document.md, document.json, INDEX.md, library.json."""

from __future__ import annotations

import json

import pytest

from scanmylib.assemble import (
    DocumentMeta,
    DocumentMetadata,
    GapSection,
    IndexEntry,
    IndexMetadata,
    PageEntry,
    PageMetadata,
    PageSection,
    Section,
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
GENERATED_AT = "2026-10-12T21:00:00+02:00"
INDEX_ENTRIES = [
    IndexEntry(META, 3, Coverage(((1, 1), (45, 45)), 1)),
    IndexEntry(
        DocumentMeta(**{**META.__dict__, "slug": "a-b", "title": "Élan | [x] <b>", "author": "", "kind": "document"}),
        1,
        Coverage((), 1),
    ),
]


def make_entry(
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


def find_index_rows(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("| [")]


class TestTheAssembly:
    class TestTheDocumentSectionsFunction:
        class TestWhenTheDocumentIsNumbered:
            @pytest.fixture
            def sections(self) -> list[Section]:
                reading_order = [
                    make_entry("r", PageNumber(1, front_matter=True)),
                    make_entry("a", PageNumber(1)),
                    make_entry("b", PageNumber(2, 3)),
                    make_entry("c", PageNumber(7)),
                    make_entry("d", PageNumber(8)),
                    make_entry("u", None),
                ]
                return document_sections(reading_order, numbered=True)

            def test_should_label_each_page_mark_the_gaps_and_put_the_unplaced_pages_under_their_heading(
                self, sections: list[Section]
            ) -> None:
                assert sections == [
                    PageSection("r", "i"),
                    PageSection("a", "1"),
                    PageSection("b", "2–3"),
                    GapSection(4, 6),
                    PageSection("c", "7"),
                    PageSection("d", "8"),
                    UnnumberedHeading(),
                    PageSection("u", None),
                ]

        class TestWhenTheDocumentIsNotNumbered:
            @pytest.fixture
            def sections(self) -> list[Section]:
                return document_sections([make_entry("a", None), make_entry("b", None)], numbered=False)

            def test_should_list_the_pages_without_an_unnumbered_heading(self, sections: list[Section]) -> None:
                assert sections == [PageSection("a", None), PageSection("b", None)]

        class TestWhenUnnumberedPagesArePlacedByTheirSessionOrByHand:
            @pytest.fixture
            def sections(self) -> list[Section]:
                reading_order = [
                    make_entry("scanned_just_before_page_1", None, placement="session"),
                    make_entry("a", PageNumber(1)),
                    make_entry("plate", None, placement="session"),
                    make_entry("map", None, placement="manual", position=1.5),
                    make_entry("b", PageNumber(2)),
                    make_entry("loose", None),
                ]
                return document_sections(reading_order, numbered=True)

            def test_should_put_only_the_pages_that_could_not_be_placed_under_the_unnumbered_heading(
                self, sections: list[Section]
            ) -> None:
                assert sections == [
                    PageSection("scanned_just_before_page_1", None),
                    PageSection("a", "1"),
                    PageSection("plate", None),
                    PageSection("map", None),
                    PageSection("b", "2"),
                    UnnumberedHeading(),
                    PageSection("loose", None),
                ]

        class TestWhenPagesWereMovedByHandOutOfTheOrderOfTheirNumbers:
            @pytest.fixture
            def sections(self) -> list[Section]:
                reading_order = [
                    make_entry("p1", PageNumber(1)),
                    make_entry("p7", PageNumber(7), placement="manual", position=1.5),
                    make_entry("p2", PageNumber(2)),
                    make_entry("p3", PageNumber(3, 4)),
                    make_entry("p6", PageNumber(6)),
                    make_entry("pi", PageNumber(1, front_matter=True), placement="manual", position=6.5),
                ]
                return document_sections(reading_order, numbered=True)

            def test_should_mark_only_the_numbers_no_page_holds_before_the_page_that_follows_them(
                self, sections: list[Section]
            ) -> None:
                assert sections == [
                    PageSection("p1", "1"),
                    PageSection("p7", "7"),
                    PageSection("p2", "2"),
                    PageSection("p3", "3–4"),
                    GapSection(5, 5),
                    PageSection("p6", "6"),
                    PageSection("pi", "i"),
                ]

    class TestTheGapSectionLabelProperty:
        class TestWhenTheGapSpansSeveralPages:
            @pytest.fixture
            def label(self) -> str:
                return GapSection(4, 6).label

            def test_should_give_the_range_of_the_missing_numbers(self, label: str) -> None:
                assert label == "4–6"

        class TestWhenTheGapIsASinglePage:
            @pytest.fixture
            def label(self) -> str:
                return GapSection(9, 9).label

            def test_should_give_the_missing_number(self, label: str) -> None:
                assert label == "9"

    class TestTheGapSectionDescriptionProperty:
        class TestWhenTheGapSpansSeveralPages:
            @pytest.fixture
            def description(self) -> str:
                return GapSection(4, 6).description

            def test_should_name_the_missing_pages(self, description: str) -> None:
                assert description == "Missing pages: 4–6"

        class TestWhenTheGapIsASinglePage:
            @pytest.fixture
            def description(self) -> str:
                return GapSection(9, 9).description

            def test_should_name_the_missing_page_in_the_singular(self, description: str) -> None:
                assert description == "Missing page: 9"

    class TestTheRenderDocumentMarkdownFunction:
        class TestWhenTheDocumentHasAGapAndAnUnnumberedPage:
            @pytest.fixture
            def markdown(self) -> str:
                pages = {
                    "k1": 'Text.\n\n<div style="text-align: center;"><img src="../images/k1_1.jpg" alt="Image" /></div>'
                    "\n",
                    "k2": "![Map](../images/k2_1.jpg)\n",
                    "k3": "",
                }
                sections: list[Section] = [
                    PageSection("k1", "1"),
                    GapSection(2, 44),
                    PageSection("k2", "45"),
                    UnnumberedHeading(),
                    PageSection("k3", None),
                ]
                return render_document_markdown(
                    META,
                    sections,
                    pages.__getitem__,
                    source="ScanMyLib — OCR PaddleOCR-VL-1.6",
                    pages_scanned=3,
                    coverage=Coverage(ranges=((1, 1), (45, 45)), unnumbered=1),
                )

            def test_should_write_the_front_matter_the_title_then_each_page_after_its_marker(
                self, markdown: str
            ) -> None:
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

        class TestWhenTheTitleAndTheAuthorHoldMarkupQuotesAndLineEnds:
            @pytest.fixture
            def markdown(self) -> str:
                meta = DocumentMeta(
                    **{**META.__dict__, "title": "<script>x</script>\n---\nkind: evil", "author": 'a"b'}
                )
                return render_document_markdown(
                    meta, [], lambda key: "", source="ScanMyLib", pages_scanned=0, coverage=Coverage((), 0)
                )

            def test_should_escape_the_title_in_the_front_matter_so_that_it_cannot_end_it(self, markdown: str) -> None:
                front_matter = markdown.split("---\n")[1]
                assert 'title: "<script>x</script>\\n---\\nkind: evil"' in front_matter

            def test_should_escape_the_author_in_the_front_matter(self, markdown: str) -> None:
                front_matter = markdown.split("---\n")[1]
                assert 'author: "a\\"b"' in front_matter

            def test_should_keep_markup_from_starting_in_the_title_heading(self, markdown: str) -> None:
                assert "# &lt;script>x&lt;/script>" in markdown

    class TestTheDocumentRelativeFunction:
        class TestWhenThePageMentionsTheImageFolderInItsText:
            @pytest.fixture
            def page_markdown(self) -> str:
                return document_relative('see ../images/ here ![x](../images/k_1.jpg) <img src="../images/k_2.jpg" />')

            def test_should_rewrite_only_the_image_references(self, page_markdown: str) -> None:
                assert page_markdown == 'see ../images/ here ![x](images/k_1.jpg) <img src="images/k_2.jpg" />'

    class TestTheRenderDocumentMetadataFunction:
        class TestWhenOnePageIsDoneAndAnotherWaitsForOcr:
            @pytest.fixture
            def metadata(self) -> DocumentMetadata:
                pages = [
                    make_entry("k1", PageNumber(1), images=2),
                    make_entry("k2", None, status="queued", in_document=False),
                ]
                return render_document_metadata(
                    META, pages, source="S", pages_scanned=1, coverage=Coverage(((1, 1),), 0)
                )

            def test_should_survive_a_round_trip_through_json(self, metadata: DocumentMetadata) -> None:
                assert json.loads(json.dumps(metadata)) == metadata

            def test_should_list_every_page(self, metadata: DocumentMetadata) -> None:
                assert [page["key"] for page in metadata["pages"]] == ["k1", "k2"]

            def test_should_list_the_files_of_the_page_that_is_done(self, metadata: DocumentMetadata) -> None:
                assert metadata["pages"][0]["files"] == {
                    "scan": "scans/k1.jpg",
                    "markdown": "pages/k1.md",
                    "ocr": "ocr/k1.json",
                    "images": ["images/k1_1.jpg", "images/k1_2.jpg"],
                }

            def test_should_label_the_page_in_the_document(self, metadata: DocumentMetadata) -> None:
                done_page = metadata["pages"][0]
                assert (done_page["label"], done_page["in_document"]) == ("1", True)

            def test_should_place_the_page_that_is_done_by_its_number(self, metadata: DocumentMetadata) -> None:
                done_page = metadata["pages"][0]
                assert (done_page["position"], done_page["placement"]) == (None, "number")

            def test_should_list_only_the_scan_of_the_page_waiting_for_ocr(self, metadata: DocumentMetadata) -> None:
                assert metadata["pages"][1]["files"] == {
                    "scan": "scans/k2.jpg",
                    "markdown": None,
                    "ocr": None,
                    "images": [],
                }

            def test_should_place_nowhere_the_page_outside_the_document(self, metadata: DocumentMetadata) -> None:
                waiting_page = metadata["pages"][1]
                assert (waiting_page["position"], waiting_page["placement"]) == (None, None)

            def test_should_give_the_label_of_the_coverage(self, metadata: DocumentMetadata) -> None:
                assert metadata["coverage"]["label"] == "1"

            def test_should_keep_the_notes(self, metadata: DocumentMetadata) -> None:
                assert metadata["notes"] == "Volume 1"

        class TestWhenAPageWasMovedByHand:
            @pytest.fixture
            def moved_page(self) -> PageMetadata:
                pages = [make_entry("k3", None, placement="manual", position=0.5)]
                metadata = render_document_metadata(META, pages, source="S", pages_scanned=1, coverage=Coverage((), 1))
                return metadata["pages"][0]

            def test_should_give_its_position_and_its_manual_placement(self, moved_page: PageMetadata) -> None:
                assert (moved_page["position"], moved_page["placement"]) == (0.5, "manual")

    class TestTheSourceLabelFunction:
        class TestWhenEveryPageWasReadByTheSameEngine:
            @pytest.fixture
            def label(self) -> str:
                return source_label(["PaddleOCR-VL-1.6", "PaddleOCR-VL-1.6"])

            def test_should_name_the_engine_once(self, label: str) -> None:
                assert label == "ScanMyLib — OCR PaddleOCR-VL-1.6"

        class TestWhenThePagesWereReadBySeveralEngines:
            @pytest.fixture
            def label(self) -> str:
                return source_label(["B", "A"])

            def test_should_name_each_engine_in_alphabetical_order(self, label: str) -> None:
                assert label == "ScanMyLib — OCR A, B"

        class TestWhenNoPageWasRead:
            @pytest.fixture
            def label(self) -> str:
                return source_label([])

            def test_should_name_only_scanmylib(self, label: str) -> None:
                assert label == "ScanMyLib"

    class TestTheRenderIndexMarkdownFunction:
        class TestWhenTheLibraryHoldsTwoDocuments:
            @pytest.fixture
            def markdown(self) -> str:
                return render_index_markdown(INDEX_ENTRIES, GENERATED_AT)

            def test_should_list_the_documents_by_title_with_markup_and_table_syntax_escaped(
                self, markdown: str
            ) -> None:
                assert find_index_rows(markdown) == [
                    "| [Élan \\| \\[x\\] &lt;b>](a-b/document.md) |  | document | 1 |  |  |",
                    '| [Sample "Café" Guide](sample-cafe-guide/document.md) | Jane Doe | book | 3 | 1, 45 | 2–44 |',
                ]

            def test_should_count_the_documents_and_give_the_time_of_the_index(self, markdown: str) -> None:
                assert f"2 documents — index updated {GENERATED_AT}." in markdown

        class TestWhenTheLibraryHoldsOneDocument:
            @pytest.fixture
            def markdown(self) -> str:
                return render_index_markdown(INDEX_ENTRIES[:1], "now")

            def test_should_count_it_in_the_singular(self, markdown: str) -> None:
                assert "1 document — index updated now." in markdown

        class TestWhenTheLibraryIsEmpty:
            @pytest.fixture
            def markdown(self) -> str:
                return render_index_markdown([], "now")

            def test_should_say_that_there_is_no_document_yet(self, markdown: str) -> None:
                assert "_No documents yet._" in markdown

            def test_should_count_no_document(self, markdown: str) -> None:
                assert "0 documents — index updated now." in markdown

    class TestTheRenderIndexMetadataFunction:
        class TestWhenTheLibraryHoldsTwoDocuments:
            @pytest.fixture
            def metadata(self) -> IndexMetadata:
                return render_index_metadata(INDEX_ENTRIES, GENERATED_AT)

            def test_should_survive_a_round_trip_through_json(self, metadata: IndexMetadata) -> None:
                assert json.loads(json.dumps(metadata)) == metadata

            def test_should_list_the_documents_by_title(self, metadata: IndexMetadata) -> None:
                assert [document["slug"] for document in metadata["documents"]] == ["a-b", "sample-cafe-guide"]

            def test_should_give_the_path_of_each_document_s_markdown(self, metadata: IndexMetadata) -> None:
                assert metadata["documents"][1]["markdown"] == "sample-cafe-guide/document.md"

        class TestWhenTheLibraryIsEmpty:
            @pytest.fixture
            def metadata(self) -> IndexMetadata:
                return render_index_metadata([], "now")

            def test_should_list_no_document(self, metadata: IndexMetadata) -> None:
                empty: IndexMetadata = {"generated_at": "now", "documents": []}
                assert metadata == empty
