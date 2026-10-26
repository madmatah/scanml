"""A document's rules, on hand-built pages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import islice

import pytest

from scanmylib.domain.documents import (
    LayoutSummary,
    NewDocument,
    check_document_changes,
    prepare_new_document,
    propose_slugs,
    summarize_layout,
)
from scanmylib.domain.ordering import Coverage, PageInput, compute_layout
from scanmylib.domain.records import DocumentChanges, DocumentStats, InvalidRequest

TITLE = "Sample Café Guide"
TRIED_SLUG_COUNT = 3


@dataclass(frozen=True)
class KindAndUnwarping:
    kind: str | None
    unwarp: bool | None
    expected_kind_and_unwarp: tuple[str, bool]


@dataclass(frozen=True)
class PreparedKindAndUnwarping:
    given: KindAndUnwarping
    new_document: NewDocument


@dataclass(frozen=True)
class TitleSlugs:
    title: str
    expected_slugs: list[str]


@dataclass(frozen=True)
class ProposedSlugs:
    given: TitleSlugs
    slugs: list[str]


def make_page(
    page_id: str,
    status: str,
    captured_timestamp_seconds: float,
    *,
    numbers: tuple[str, ...] = (),
    is_excluded: bool = False,
) -> PageInput:
    return PageInput(
        id=page_id,
        session_id=None,
        seq=None,
        captured_ts=captured_timestamp_seconds,
        status=status,
        excluded=is_excluded,
        detected_numbers=numbers,
    )


class TestTheDocuments:
    class TestTheSummarizeLayoutFunction:
        class TestWhenTheDocumentHoldsPagesOfEveryState:
            PAGES = (
                make_page("page-1", "done", 1, numbers=("1",)),
                make_page("page-2", "done", 2, numbers=("2",)),
                make_page("page-2-rescanned", "done", 3, numbers=("2",)),
                make_page("queued", "queued", 4),
                make_page("processing", "processing", 5),
                make_page("error", "error", 6),
                make_page("excluded", "done", 7, numbers=("3",), is_excluded=True),
            )

            @pytest.fixture
            def summary(self) -> LayoutSummary:
                layout = compute_layout(self.PAGES)
                return summarize_layout(self.PAGES, layout)

            def test_should_count_its_pages_by_state(self, summary: LayoutSummary) -> None:
                assert summary.stats == DocumentStats(
                    page_count=7,
                    done_count=4,
                    queued_count=1,
                    processing_count=1,
                    error_count=1,
                    excluded_count=1,
                    duplicate_count=1,
                )

            def test_should_take_the_first_page_of_its_order_as_its_cover(self, summary: LayoutSummary) -> None:
                assert summary.cover_page_id == "page-1"

            def test_should_count_only_the_pages_of_its_reading_order_as_in_the_document(
                self, summary: LayoutSummary
            ) -> None:
                assert summary.pages_in_document == 2

            def test_should_cover_the_numbers_of_its_reading_order(self, summary: LayoutSummary) -> None:
                assert summary.coverage == Coverage(((1, 2),), 0)

        class TestWhenTheDocumentHasNoPage:
            @pytest.fixture
            def summary(self) -> LayoutSummary:
                layout = compute_layout(())
                return summarize_layout((), layout)

            def test_should_count_no_page(self, summary: LayoutSummary) -> None:
                assert summary.stats == DocumentStats(
                    page_count=0,
                    done_count=0,
                    queued_count=0,
                    processing_count=0,
                    error_count=0,
                    excluded_count=0,
                    duplicate_count=0,
                )

            def test_should_have_no_cover(self, summary: LayoutSummary) -> None:
                assert summary.cover_page_id is None

    class TestThePrepareNewDocumentFunction:
        class TestWhenItHasNoTitle:
            @pytest.fixture(params=[None, ""], ids=["no-title", "an-empty-title"])
            def prepare(self, request: pytest.FixtureRequest) -> Callable[[], NewDocument]:
                changes = DocumentChanges(title=request.param)
                return lambda: prepare_new_document(changes)

            def test_should_refuse_it(self, prepare: Callable[[], NewDocument]) -> None:
                with pytest.raises(InvalidRequest, match=r"^title is required to create a document$"):
                    prepare()

        class TestWhenOnlyATitleIsGiven:
            @pytest.fixture
            def new_document(self) -> NewDocument:
                return prepare_new_document(DocumentChanges(title=TITLE))

            def test_should_give_it_no_author_and_no_notes(self, new_document: NewDocument) -> None:
                assert (new_document.author, new_document.notes) == ("", "")

        class TestWhenItsKindAndUnwarpingAreGivenOrNot:
            @pytest.fixture(
                params=[
                    KindAndUnwarping(None, None, ("document", False)),
                    KindAndUnwarping("book", None, ("book", True)),
                    KindAndUnwarping("book", False, ("book", False)),
                    KindAndUnwarping("document", True, ("document", True)),
                ],
                ids=[
                    "a-document-of-no-kind-is-a-flat-document",
                    "a-book-unwarps-its-curved-pages-by-default",
                    "a-book-said-flat-stays-flat",
                    "a-document-said-curved-is-unwarped",
                ],
            )
            def prepared(self, request: pytest.FixtureRequest) -> PreparedKindAndUnwarping:
                given: KindAndUnwarping = request.param
                changes = DocumentChanges(title=TITLE, kind=given.kind, unwarp=given.unwarp)
                return PreparedKindAndUnwarping(given, prepare_new_document(changes))

            def test_should_settle_its_kind_and_whether_to_unwarp_its_pages(
                self, prepared: PreparedKindAndUnwarping
            ) -> None:
                new_document = prepared.new_document
                assert (new_document.kind, new_document.unwarp) == prepared.given.expected_kind_and_unwarp

    class TestTheCheckDocumentChangesFunction:
        class TestWhenTheTitleIsChangedToAnEmptyOne:
            @pytest.fixture
            def check(self) -> Callable[[], None]:
                changes = DocumentChanges(title="")
                return lambda: check_document_changes(changes)

            def test_should_refuse_it(self, check: Callable[[], None]) -> None:
                with pytest.raises(InvalidRequest, match=r"^title cannot be empty$"):
                    check()

    class TestTheProposeSlugsFunction:
        class TestWhenATitleIsGiven:
            @pytest.fixture(
                params=[
                    TitleSlugs(TITLE, ["sample-cafe-guide", "sample-cafe-guide-2", "sample-cafe-guide-3"]),
                    TitleSlugs("¿?", ["document", "document-2", "document-3"]),
                ],
                ids=["a-title-with-accents", "a-title-without-letters-or-digits"],
            )
            def proposed(self, request: pytest.FixtureRequest) -> ProposedSlugs:
                given: TitleSlugs = request.param
                return ProposedSlugs(given, list(islice(propose_slugs(given.title), TRIED_SLUG_COUNT)))

            def test_should_try_the_slug_of_its_title_then_number_it_from_2(self, proposed: ProposedSlugs) -> None:
                assert proposed.slugs == proposed.given.expected_slugs
