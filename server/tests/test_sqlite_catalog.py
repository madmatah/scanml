"""The catalog of documents and pages in SQLite (adapters/sqlite/catalog.py): its transactions, the order of its lists,
the changes of its documents and pages, and its queue of pages to read."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

import pytest

from scanmylib.adapters.sqlite.catalog import SqliteCatalog
from scanmylib.adapters.sqlite.database import Database
from scanmylib.application.catalog import NewPage
from scanmylib.application.scan_images import ScanInfo
from scanmylib.domain.documents import NewDocument
from scanmylib.domain.pages import AttemptOutcome
from scanmylib.domain.records import DocumentChanges, DocumentRecord, OcrSummary, PageChanges, PageClaim, PageRecord

DOCUMENT_ID = "0f000000-0000-4000-8000-000000000000"
MOMENT = "2026-10-12T20:00:00+02:00"
MOMENT_TIMESTAMP_SECONDS = datetime.fromisoformat(MOMENT).timestamp()
PAGE_BEING_READ_ID = "1f000000-0000-4000-8000-000000000000"
EARLIER_UPDATED_DOCUMENT_ID = "0a000000-0000-4000-8000-000000000000"
FIRST_TIED_DOCUMENT_ID = "0b000000-0000-4000-8000-000000000000"
SECOND_TIED_DOCUMENT_ID = "0c000000-0000-4000-8000-000000000000"
EARLIER_UPDATE_SECONDS = 100.0
LATER_UPDATE_SECONDS = 200.0
SECOND_RANK_PAGE_ID = "1a000000-0000-4000-8000-000000000000"
LATER_CAPTURE_PAGE_ID = "1b000000-0000-4000-8000-000000000000"
FIRST_TIED_PAGE_ID = "1c000000-0000-4000-8000-000000000001"
SECOND_TIED_PAGE_ID = "1c000000-0000-4000-8000-000000000002"
EARLIEST_CAPTURE_SECONDS = 1.0
TIED_CAPTURE_SECONDS = 5.0
LATER_CAPTURE_SECONDS = 9.0
STATUSES_BY_RANK = ("processing", "processing", "queued", "done", "error")
EXAMPLE_SLUG_PREFIX = "example-book-"
NEW_DOCUMENT = NewDocument("Example Book", "Jane Doe", "book", "Bought second-hand", True)
OTHER_AUTHOR = "John Roe"
FIRST_MOMENT_TEXT = "2026-10-13T09:00:00+02:00"
LATER_MOMENT_TEXT = "2026-10-13T10:30:00+02:00"
LATEST_MOMENT_TEXT = "2026-10-14T08:15:00+02:00"
FIRST_MOMENT = datetime.fromisoformat(FIRST_MOMENT_TEXT)
LATER_MOMENT = datetime.fromisoformat(LATER_MOMENT_TEXT)
LATEST_MOMENT = datetime.fromisoformat(LATEST_MOMENT_TEXT)
FIRST_ADDED_DOCUMENT_ID = "0d000000-0000-4000-8000-000000000001"
LATER_ADDED_DOCUMENT_ID = "0d000000-0000-4000-8000-000000000002"
OTHER_DOCUMENT_ID = "0e000000-0000-4000-8000-000000000000"
NEW_PAGE_ID = "1d000000-0000-4000-8000-000000000000"
SCAN = ScanInfo("jpg", 1200, 1600)
SEQ = 3
HINT_NUMBER = 12
SESSION_ID = "5e000000-0000-4000-8000-000000000000"
CAPTURED_MOMENT_TEXT = "2026-10-13T08:45:10+02:00"
CAPTURED_MOMENT = datetime.fromisoformat(CAPTURED_MOMENT_TEXT)
CAPTURED_TIMESTAMP_SECONDS = CAPTURED_MOMENT.timestamp()
UPLOADED_MOMENT_TEXT = "2026-10-13T08:45:40+02:00"
UPLOADED_MOMENT = datetime.fromisoformat(UPLOADED_MOMENT_TEXT)
MANUAL_NUMBER = 7
QUARTER_TURN_DEGREES = 90
REMOVED_PAGE_ID = "1f000000-0000-4000-8000-000000000001"
KEPT_PAGE_ID = "1f000000-0000-4000-8000-000000000002"
POSITIONS = MappingProxyType({"1e000000-0000-4000-8000-000000000001": 1.5, "1e000000-0000-4000-8000-000000000002": 2.5})
POSITIONED_PAGE_IDS = tuple(POSITIONS)
UNPOSITIONED_PAGE_ID = "1e000000-0000-4000-8000-000000000003"
POSITION_TO_CLEAR = 3.5
OTHER_DOCUMENT_PAGE_ID = "1e000000-0000-4000-8000-000000000004"
OTHER_DOCUMENT_POSITION = 0.5
ALREADY_READ_PAGE_ID = "3a000000-0000-4000-8000-000000000000"
FIRST_TIED_QUEUED_PAGE_ID = "3b000000-0000-4000-8000-000000000001"
SECOND_TIED_QUEUED_PAGE_ID = "3b000000-0000-4000-8000-000000000002"
EARLIER_UPLOADED_PAGE_ID = "3c000000-0000-4000-8000-000000000000"
QUEUED_PAGE_IDS = (EARLIER_UPLOADED_PAGE_ID, SECOND_TIED_QUEUED_PAGE_ID, FIRST_TIED_QUEUED_PAGE_ID)
EARLIEST_UPLOAD_MOMENT = datetime.fromisoformat("2026-10-13T08:46:00+02:00")
EARLIER_UPLOAD_MOMENT = datetime.fromisoformat("2026-10-13T08:47:00+02:00")
LATER_UPLOAD_MOMENT = datetime.fromisoformat("2026-10-13T08:48:00+02:00")
FAILURE_MESSAGE = "the sandbox could not read the page"
FAILED_OUTCOME = AttemptOutcome("error", 1, FAILURE_MESSAGE)
RETRIED_OUTCOME = AttemptOutcome("queued", 1, None)
DETECTED_NUMBERS = ("12",)
OCR_SUMMARY: OcrSummary = {
    "engine": "fake",
    "model": "Fake",
    "duration_s": 1.25,
    "at": "2026-10-13T08:49:00+02:00",
    "images": 0,
    "chars": 42,
}
FIRST_GENERATION = 0
SECOND_GENERATION = 1


@dataclass(frozen=True)
class ChangeUnderAClaim:
    description: str
    apply: Callable[[SqliteCatalog, PageClaim], bool]


CHANGES_UNDER_A_CLAIM = (
    ChangeUnderAClaim("ending-its-attempt", lambda catalog, claim: catalog.end_attempt(claim, FAILED_OUTCOME)),
    ChangeUnderAClaim(
        "completing-its-page", lambda catalog, claim: catalog.complete_page(claim, DETECTED_NUMBERS, OCR_SUMMARY)
    ),
)


def insert_document(database: Database, document_id: str, *, updated_timestamp_seconds: float) -> None:
    database.execute(
        "INSERT INTO documents (id, slug, title, kind, created_at, updated_at, updated_ts)"
        " VALUES (?, ?, 'Example Book', 'book', ?, ?, ?)",
        (document_id, document_id, MOMENT, MOMENT, updated_timestamp_seconds),
    )


def insert_page(
    database: Database, document_id: str, page_id: str, *, status: str, rank: int, captured_timestamp_seconds: float
) -> None:
    database.execute(
        "INSERT INTO pages (id, document_id, key, scan_ext, captured_at, captured_ts, uploaded_at, uploaded_ts,"
        " width, height, status, rank) VALUES (?, ?, ?, 'jpg', ?, ?, ?, ?, 1200, 1000, ?, ?)",
        (
            page_id,
            document_id,
            page_id,
            MOMENT,
            captured_timestamp_seconds,
            MOMENT,
            MOMENT_TIMESTAMP_SECONDS,
            status,
            rank,
        ),
    )


def insert_a_page_being_read(database: Database) -> None:
    insert_document(database, DOCUMENT_ID, updated_timestamp_seconds=MOMENT_TIMESTAMP_SECONDS)
    insert_page(
        database,
        DOCUMENT_ID,
        PAGE_BEING_READ_ID,
        status="processing",
        rank=0,
        captured_timestamp_seconds=MOMENT_TIMESTAMP_SECONDS,
    )


def add_example_document(catalog: SqliteCatalog, document_id: str, *, added_at: datetime) -> None:
    catalog.add_document(document_id, f"{EXAMPLE_SLUG_PREFIX}{document_id}", NEW_DOCUMENT, added_at)


def add_example_page(
    catalog: SqliteCatalog, page_id: str, *, document_id: str = DOCUMENT_ID, uploaded_at: datetime = UPLOADED_MOMENT
) -> None:
    catalog.add_page(
        NewPage(
            id=page_id,
            document_id=document_id,
            key=page_id,
            scan=SCAN,
            session_id=SESSION_ID,
            seq=SEQ,
            hint_number=HINT_NUMBER,
            captured_at=CAPTURED_MOMENT,
            uploaded_at=uploaded_at,
        )
    )


def claim_the_next_page(catalog: SqliteCatalog) -> PageClaim:
    claim = catalog.claim_next_page()
    if claim is None:
        raise LookupError("no queued page to claim")
    return claim


class AbandonedTransaction(Exception):
    pass


@dataclass(frozen=True)
class RequeuedPages:
    requeued_count: int
    page_statuses: list[str]


@dataclass(frozen=True)
class ClearedPositions:
    cleared_count: int
    other_document_positions: list[float | None]


@dataclass(frozen=True)
class ClaimedPages:
    claimed_page_ids: list[str]
    claim_once_none_is_queued: PageClaim | None


@dataclass(frozen=True)
class ChangedPage:
    is_changed: bool
    pages: list[PageRecord]


class TestTheSqliteCatalog:
    class TestTheOpenTransactionMethod:
        class TestWhenItsBlockRaises:
            @pytest.fixture
            def page_statuses(self, tmp_path: Path) -> list[str]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    insert_a_page_being_read(database)
                    catalog = SqliteCatalog(database)
                    with contextlib.suppress(AbandonedTransaction), catalog.open_transaction():
                        catalog.requeue_interrupted_pages()
                        raise AbandonedTransaction
                    return [page.status for page in catalog.list_pages(DOCUMENT_ID)]

            def test_should_drop_its_changes(self, page_statuses: list[str]) -> None:
                assert page_statuses == ["processing"]

        class TestWhenItIsOpenedInsideAnotherWhoseBlockRaises:
            @pytest.fixture
            def page_statuses(self, tmp_path: Path) -> list[str]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    insert_a_page_being_read(database)
                    catalog = SqliteCatalog(database)
                    with contextlib.suppress(AbandonedTransaction), catalog.open_transaction():
                        with catalog.open_transaction():
                            catalog.requeue_interrupted_pages()
                        raise AbandonedTransaction
                    return [page.status for page in catalog.list_pages(DOCUMENT_ID)]

            def test_should_drop_the_changes_of_the_inner_one_too_since_it_joined_the_outer_one(
                self, page_statuses: list[str]
            ) -> None:
                assert page_statuses == ["processing"]

    class TestTheListDocumentsMethod:
        class TestWhenTwoDocumentsWereUpdatedAtTheSameMoment:
            @pytest.fixture
            def listed_document_ids(self, tmp_path: Path) -> list[str]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    insert_document(database, SECOND_TIED_DOCUMENT_ID, updated_timestamp_seconds=LATER_UPDATE_SECONDS)
                    insert_document(
                        database, EARLIER_UPDATED_DOCUMENT_ID, updated_timestamp_seconds=EARLIER_UPDATE_SECONDS
                    )
                    insert_document(database, FIRST_TIED_DOCUMENT_ID, updated_timestamp_seconds=LATER_UPDATE_SECONDS)
                    return [document.id for document in SqliteCatalog(database).list_documents()]

            def test_should_list_the_most_recently_updated_first_and_those_updated_together_by_id(
                self, listed_document_ids: list[str]
            ) -> None:
                assert listed_document_ids == [
                    FIRST_TIED_DOCUMENT_ID,
                    SECOND_TIED_DOCUMENT_ID,
                    EARLIER_UPDATED_DOCUMENT_ID,
                ]

    class TestTheListPagesMethod:
        class TestWhenPagesShareARank:
            @pytest.fixture
            def listed_page_ids(self, tmp_path: Path) -> list[str]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    insert_document(database, DOCUMENT_ID, updated_timestamp_seconds=MOMENT_TIMESTAMP_SECONDS)
                    for page_id, rank, captured_timestamp_seconds in (
                        (SECOND_RANK_PAGE_ID, 1, EARLIEST_CAPTURE_SECONDS),
                        (LATER_CAPTURE_PAGE_ID, 0, LATER_CAPTURE_SECONDS),
                        (SECOND_TIED_PAGE_ID, 0, TIED_CAPTURE_SECONDS),
                        (FIRST_TIED_PAGE_ID, 0, TIED_CAPTURE_SECONDS),
                    ):
                        insert_page(
                            database,
                            DOCUMENT_ID,
                            page_id,
                            status="done",
                            rank=rank,
                            captured_timestamp_seconds=captured_timestamp_seconds,
                        )
                    return [page.id for page in SqliteCatalog(database).list_pages(DOCUMENT_ID)]

            def test_should_list_them_by_rank_then_by_capture_then_by_id(self, listed_page_ids: list[str]) -> None:
                assert listed_page_ids == [
                    FIRST_TIED_PAGE_ID,
                    SECOND_TIED_PAGE_ID,
                    LATER_CAPTURE_PAGE_ID,
                    SECOND_RANK_PAGE_ID,
                ]

    class TestTheRequeueInterruptedPagesMethod:
        class TestWhenPagesAreBeingRead:
            @pytest.fixture
            def requeued_pages(self, tmp_path: Path) -> RequeuedPages:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    insert_document(database, DOCUMENT_ID, updated_timestamp_seconds=MOMENT_TIMESTAMP_SECONDS)
                    for rank, status in enumerate(STATUSES_BY_RANK):
                        insert_page(
                            database,
                            DOCUMENT_ID,
                            f"2a000000-0000-4000-8000-{rank:012d}",
                            status=status,
                            rank=rank,
                            captured_timestamp_seconds=MOMENT_TIMESTAMP_SECONDS,
                        )
                    catalog = SqliteCatalog(database)
                    requeued_count = catalog.requeue_interrupted_pages()
                    return RequeuedPages(requeued_count, [page.status for page in catalog.list_pages(DOCUMENT_ID)])

            def test_should_queue_again_the_pages_being_read_and_only_those(
                self, requeued_pages: RequeuedPages
            ) -> None:
                assert requeued_pages.page_statuses == ["queued", "queued", "queued", "done", "error"]

            def test_should_count_the_pages_it_queued_again(self, requeued_pages: RequeuedPages) -> None:
                assert requeued_pages.requeued_count == 2

    class TestTheAddDocumentMethod:
        class TestWhenTwoAreAddedOneAfterTheOther:
            @pytest.fixture
            def documents(self, tmp_path: Path) -> list[DocumentRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, FIRST_ADDED_DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_document(catalog, LATER_ADDED_DOCUMENT_ID, added_at=LATER_MOMENT)
                    return catalog.list_documents()

            def test_should_record_each_created_and_last_updated_at_the_moment_it_was_added(
                self, documents: list[DocumentRecord]
            ) -> None:
                assert [(document.id, document.created_at, document.updated_at) for document in documents] == [
                    (LATER_ADDED_DOCUMENT_ID, LATER_MOMENT_TEXT, LATER_MOMENT_TEXT),
                    (FIRST_ADDED_DOCUMENT_ID, FIRST_MOMENT_TEXT, FIRST_MOMENT_TEXT),
                ]

            def test_should_record_each_with_its_slug_and_the_fields_of_the_new_document(
                self, documents: list[DocumentRecord]
            ) -> None:
                assert {
                    document.id: (
                        document.slug,
                        document.title,
                        document.author,
                        document.kind,
                        document.notes,
                        document.unwarp,
                    )
                    for document in documents
                } == {
                    document_id: (
                        f"{EXAMPLE_SLUG_PREFIX}{document_id}",
                        NEW_DOCUMENT.title,
                        NEW_DOCUMENT.author,
                        NEW_DOCUMENT.kind,
                        NEW_DOCUMENT.notes,
                        NEW_DOCUMENT.unwarp,
                    )
                    for document_id in (FIRST_ADDED_DOCUMENT_ID, LATER_ADDED_DOCUMENT_ID)
                }

    class TestTheTouchDocumentMethod:
        class TestWhenTheFirstOfTwoDocumentsIsTouched:
            @pytest.fixture
            def documents(self, tmp_path: Path) -> list[DocumentRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, FIRST_ADDED_DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_document(catalog, LATER_ADDED_DOCUMENT_ID, added_at=LATER_MOMENT)
                    catalog.touch_document(FIRST_ADDED_DOCUMENT_ID, LATEST_MOMENT)
                    return catalog.list_documents()

            def test_should_record_the_moment_of_its_last_update_and_keep_that_of_its_creation(
                self, documents: list[DocumentRecord]
            ) -> None:
                assert [(document.id, document.created_at, document.updated_at) for document in documents] == [
                    (FIRST_ADDED_DOCUMENT_ID, FIRST_MOMENT_TEXT, LATEST_MOMENT_TEXT),
                    (LATER_ADDED_DOCUMENT_ID, LATER_MOMENT_TEXT, LATER_MOMENT_TEXT),
                ]

    class TestTheUpdateDocumentMethod:
        class TestWhenItsChangesHoldSomeOfItsFields:
            @pytest.fixture
            def documents(self, tmp_path: Path) -> list[DocumentRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, FIRST_ADDED_DOCUMENT_ID, added_at=FIRST_MOMENT)
                    catalog.update_document(FIRST_ADDED_DOCUMENT_ID, DocumentChanges(author=OTHER_AUTHOR, unwarp=False))
                    return catalog.list_documents()

            def test_should_set_those_fields_and_keep_the_others(self, documents: list[DocumentRecord]) -> None:
                assert [
                    (document.title, document.author, document.kind, document.notes, document.unwarp)
                    for document in documents
                ] == [(NEW_DOCUMENT.title, OTHER_AUTHOR, NEW_DOCUMENT.kind, NEW_DOCUMENT.notes, False)]

        class TestWhenItsChangesHoldNoField:
            @pytest.fixture
            def update_the_document(self, tmp_path: Path, request: pytest.FixtureRequest) -> Callable[[], None]:
                database = Database(tmp_path / "scanmylib.db")
                request.addfinalizer(database.close)
                catalog = SqliteCatalog(database)
                add_example_document(catalog, FIRST_ADDED_DOCUMENT_ID, added_at=FIRST_MOMENT)
                return lambda: catalog.update_document(FIRST_ADDED_DOCUMENT_ID, DocumentChanges())

            def test_should_refuse_them_since_an_update_sets_at_least_one(
                self, update_the_document: Callable[[], None]
            ) -> None:
                with pytest.raises(ValueError, match="at least one"):
                    update_the_document()

    class TestTheRemoveDocumentMethod:
        class TestWhenItHasAPage:
            @pytest.fixture
            def page(self, tmp_path: Path) -> PageRecord | None:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    insert_a_page_being_read(database)
                    catalog = SqliteCatalog(database)
                    catalog.remove_document(DOCUMENT_ID)
                    return catalog.get_page(PAGE_BEING_READ_ID)

            def test_should_remove_its_page_with_it(self, page: PageRecord | None) -> None:
                assert page is None

    class TestTheAddPageMethod:
        class TestWhenAPageIsAdded:
            @pytest.fixture
            def pages(self, tmp_path: Path) -> list[PageRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    return catalog.list_pages(DOCUMENT_ID)

            def test_should_record_it_queued_for_reading_with_the_fields_of_its_upload(
                self, pages: list[PageRecord]
            ) -> None:
                assert [
                    (
                        page.id,
                        page.key,
                        page.scan_ext,
                        page.width,
                        page.height,
                        page.session_id,
                        page.seq,
                        page.hint_number,
                        page.captured_at,
                        page.captured_ts,
                        page.uploaded_at,
                        page.status,
                    )
                    for page in pages
                ] == [
                    (
                        NEW_PAGE_ID,
                        NEW_PAGE_ID,
                        SCAN.ext,
                        SCAN.width,
                        SCAN.height,
                        SESSION_ID,
                        SEQ,
                        HINT_NUMBER,
                        CAPTURED_MOMENT_TEXT,
                        CAPTURED_TIMESTAMP_SECONDS,
                        UPLOADED_MOMENT_TEXT,
                        "queued",
                    )
                ]

    class TestTheUpdatePageMethod:
        class TestWhenItsChangesLeaveItsManualNumberAsItIs:
            @pytest.fixture
            def pages(self, tmp_path: Path) -> list[PageRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    catalog.update_page(NEW_PAGE_ID, PageChanges(manual_number=MANUAL_NUMBER))
                    catalog.update_page(NEW_PAGE_ID, PageChanges(excluded=True))
                    return catalog.list_pages(DOCUMENT_ID)

            def test_should_keep_its_manual_number_and_set_the_field_they_hold(self, pages: list[PageRecord]) -> None:
                assert [(page.manual_number, page.excluded) for page in pages] == [(MANUAL_NUMBER, True)]

        class TestWhenItsChangesHoldNoField:
            @pytest.fixture
            def update_the_page(self, tmp_path: Path, request: pytest.FixtureRequest) -> Callable[[], None]:
                database = Database(tmp_path / "scanmylib.db")
                request.addfinalizer(database.close)
                catalog = SqliteCatalog(database)
                add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                add_example_page(catalog, NEW_PAGE_ID)
                return lambda: catalog.update_page(NEW_PAGE_ID, PageChanges())

            def test_should_refuse_them_since_an_update_sets_at_least_one(
                self, update_the_page: Callable[[], None]
            ) -> None:
                with pytest.raises(ValueError, match="at least one"):
                    update_the_page()

        class TestWhenItsManualNumberIsNone:
            @pytest.fixture
            def pages(self, tmp_path: Path) -> list[PageRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    catalog.update_page(NEW_PAGE_ID, PageChanges(manual_number=MANUAL_NUMBER))
                    catalog.update_page(NEW_PAGE_ID, PageChanges(manual_number=None))
                    return catalog.list_pages(DOCUMENT_ID)

            def test_should_clear_the_manual_number_of_the_page(self, pages: list[PageRecord]) -> None:
                assert [page.manual_number for page in pages] == [None]

        class TestWhenItsChangesHoldARotation:
            @pytest.fixture
            def pages(self, tmp_path: Path) -> list[PageRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    catalog.update_page(NEW_PAGE_ID, PageChanges(rotation=QUARTER_TURN_DEGREES))
                    return catalog.list_pages(DOCUMENT_ID)

            def test_should_set_the_rotation_of_the_page(self, pages: list[PageRecord]) -> None:
                assert [page.rotation for page in pages] == [QUARTER_TURN_DEGREES]

    class TestTheSetPagePositionsMethod:
        class TestWhenOneOfThePositionsIsNone:
            @pytest.fixture
            def positions_by_page_id(self, tmp_path: Path) -> dict[str, float | None]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    for page_id in (*POSITIONED_PAGE_IDS, UNPOSITIONED_PAGE_ID):
                        add_example_page(catalog, page_id)
                    catalog.set_page_positions({UNPOSITIONED_PAGE_ID: POSITION_TO_CLEAR})
                    catalog.set_page_positions({**POSITIONS, UNPOSITIONED_PAGE_ID: None})
                    return {page.id: page.position for page in catalog.list_pages(DOCUMENT_ID)}

            def test_should_give_each_page_its_own_position(
                self, positions_by_page_id: dict[str, float | None]
            ) -> None:
                assert {page_id: positions_by_page_id[page_id] for page_id in POSITIONED_PAGE_IDS} == POSITIONS

            def test_should_clear_the_position_of_the_page_given_none(
                self, positions_by_page_id: dict[str, float | None]
            ) -> None:
                assert positions_by_page_id[UNPOSITIONED_PAGE_ID] is None

    class TestTheRemovePageMethod:
        class TestWhenItsDocumentHasAnotherPage:
            @pytest.fixture
            def page_ids(self, tmp_path: Path) -> list[str]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, REMOVED_PAGE_ID)
                    add_example_page(catalog, KEPT_PAGE_ID)
                    catalog.remove_page(REMOVED_PAGE_ID)
                    return [page.id for page in catalog.list_pages(DOCUMENT_ID)]

            def test_should_remove_that_page_and_keep_the_other(self, page_ids: list[str]) -> None:
                assert page_ids == [KEPT_PAGE_ID]

    class TestTheClearPagePositionsMethod:
        class TestWhenSomeOfItsPagesHaveAPosition:
            @pytest.fixture
            def cleared_positions(self, tmp_path: Path) -> ClearedPositions:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_document(catalog, OTHER_DOCUMENT_ID, added_at=FIRST_MOMENT)
                    for page_id in (*POSITIONED_PAGE_IDS, UNPOSITIONED_PAGE_ID):
                        add_example_page(catalog, page_id)
                    add_example_page(catalog, OTHER_DOCUMENT_PAGE_ID, document_id=OTHER_DOCUMENT_ID)
                    catalog.set_page_positions({**POSITIONS, OTHER_DOCUMENT_PAGE_ID: OTHER_DOCUMENT_POSITION})
                    cleared_count = catalog.clear_page_positions(DOCUMENT_ID)
                    return ClearedPositions(
                        cleared_count, [page.position for page in catalog.list_pages(OTHER_DOCUMENT_ID)]
                    )

            def test_should_count_the_pages_that_had_one(self, cleared_positions: ClearedPositions) -> None:
                assert cleared_positions.cleared_count == len(POSITIONS)

            def test_should_keep_the_positions_of_another_document(self, cleared_positions: ClearedPositions) -> None:
                assert cleared_positions.other_document_positions == [OTHER_DOCUMENT_POSITION]

    class TestTheClaimNextPageMethod:
        class TestWhenPagesAreQueued:
            @pytest.fixture
            def claimed_pages(self, tmp_path: Path) -> ClaimedPages:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, ALREADY_READ_PAGE_ID, uploaded_at=EARLIEST_UPLOAD_MOMENT)
                    catalog.complete_page(claim_the_next_page(catalog), DETECTED_NUMBERS, OCR_SUMMARY)
                    add_example_page(catalog, EARLIER_UPLOADED_PAGE_ID, uploaded_at=EARLIER_UPLOAD_MOMENT)
                    add_example_page(catalog, SECOND_TIED_QUEUED_PAGE_ID, uploaded_at=LATER_UPLOAD_MOMENT)
                    add_example_page(catalog, FIRST_TIED_QUEUED_PAGE_ID, uploaded_at=LATER_UPLOAD_MOMENT)
                    claimed_page_ids = [claim_the_next_page(catalog).page_id for _ in QUEUED_PAGE_IDS]
                    return ClaimedPages(claimed_page_ids, catalog.claim_next_page())

            def test_should_claim_each_queued_page_once_by_upload_then_by_id(self, claimed_pages: ClaimedPages) -> None:
                assert claimed_pages.claimed_page_ids == [
                    EARLIER_UPLOADED_PAGE_ID,
                    FIRST_TIED_QUEUED_PAGE_ID,
                    SECOND_TIED_QUEUED_PAGE_ID,
                ]

            def test_should_claim_none_once_every_queued_page_is_claimed(self, claimed_pages: ClaimedPages) -> None:
                assert claimed_pages.claim_once_none_is_queued is None

    class TestTheRequeuePageMethod:
        class TestWhenItsReadingFailed:
            @pytest.fixture
            def pages(self, tmp_path: Path) -> list[PageRecord]:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    catalog.end_attempt(claim_the_next_page(catalog), FAILED_OUTCOME)
                    catalog.requeue_page(NEW_PAGE_ID)
                    return catalog.list_pages(DOCUMENT_ID)

            def test_should_queue_it_again_with_its_error_and_attempts_cleared_under_a_new_generation(
                self, pages: list[PageRecord]
            ) -> None:
                assert [(page.status, page.error, page.attempts, page.generation) for page in pages] == [
                    ("queued", None, 0, SECOND_GENERATION)
                ]

    class TestTheEndAttemptMethod:
        class TestWhenItsClaimIsCurrent:
            @pytest.fixture
            def changed_page(self, tmp_path: Path) -> ChangedPage:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    is_changed = catalog.end_attempt(claim_the_next_page(catalog), FAILED_OUTCOME)
                    return ChangedPage(is_changed, catalog.list_pages(DOCUMENT_ID))

            def test_should_record_its_outcome(self, changed_page: ChangedPage) -> None:
                assert [(page.status, page.attempts, page.error) for page in changed_page.pages] == [
                    ("error", FAILED_OUTCOME.attempt_count, FAILURE_MESSAGE)
                ]

            def test_should_say_that_it_did(self, changed_page: ChangedPage) -> None:
                assert changed_page.is_changed is True

    class TestTheCompletePageMethod:
        class TestWhenItsClaimIsCurrent:
            @pytest.fixture
            def changed_page(self, tmp_path: Path) -> ChangedPage:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    catalog.end_attempt(claim_the_next_page(catalog), RETRIED_OUTCOME)
                    is_changed = catalog.complete_page(claim_the_next_page(catalog), DETECTED_NUMBERS, OCR_SUMMARY)
                    return ChangedPage(is_changed, catalog.list_pages(DOCUMENT_ID))

            def test_should_mark_the_page_read_with_its_numbers_and_ocr_summary_and_no_attempts(
                self, changed_page: ChangedPage
            ) -> None:
                assert [
                    (page.status, page.attempts, page.detected_numbers, page.ocr) for page in changed_page.pages
                ] == [("done", 0, DETECTED_NUMBERS, OCR_SUMMARY)]

            def test_should_say_that_it_did(self, changed_page: ChangedPage) -> None:
                assert changed_page.is_changed is True

    class TestWhenAClaimIsNoLongerCurrent:
        @pytest.fixture(params=CHANGES_UNDER_A_CLAIM, ids=[change.description for change in CHANGES_UNDER_A_CLAIM])
        def change_under_a_claim(self, request: pytest.FixtureRequest) -> ChangeUnderAClaim:
            change: ChangeUnderAClaim = request.param
            return change

        class TestWhenItsPageWasQueuedAgainAndClaimedAnew:
            @pytest.fixture
            def changed_page(self, tmp_path: Path, change_under_a_claim: ChangeUnderAClaim) -> ChangedPage:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    stale_claim = claim_the_next_page(catalog)
                    catalog.requeue_page(NEW_PAGE_ID)
                    claim_the_next_page(catalog)
                    is_changed = change_under_a_claim.apply(catalog, stale_claim)
                    return ChangedPage(is_changed, catalog.list_pages(DOCUMENT_ID))

            def test_should_say_that_it_changed_nothing(self, changed_page: ChangedPage) -> None:
                assert changed_page.is_changed is False

            def test_should_leave_the_page_being_read_under_its_new_claim(self, changed_page: ChangedPage) -> None:
                assert [
                    (page.status, page.generation, page.attempts, page.error, page.detected_numbers)
                    for page in changed_page.pages
                ] == [("processing", SECOND_GENERATION, 0, None, ())]

        class TestWhenItsAttemptHasAlreadyEnded:
            @pytest.fixture
            def changed_page(self, tmp_path: Path, change_under_a_claim: ChangeUnderAClaim) -> ChangedPage:
                with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                    catalog = SqliteCatalog(database)
                    add_example_document(catalog, DOCUMENT_ID, added_at=FIRST_MOMENT)
                    add_example_page(catalog, NEW_PAGE_ID)
                    claim = claim_the_next_page(catalog)
                    catalog.end_attempt(claim, RETRIED_OUTCOME)
                    is_changed = change_under_a_claim.apply(catalog, claim)
                    return ChangedPage(is_changed, catalog.list_pages(DOCUMENT_ID))

            def test_should_say_that_it_changed_nothing(self, changed_page: ChangedPage) -> None:
                assert changed_page.is_changed is False

            def test_should_leave_the_page_queued_as_its_ended_attempt_left_it(self, changed_page: ChangedPage) -> None:
                assert [
                    (page.status, page.generation, page.attempts, page.error, page.detected_numbers)
                    for page in changed_page.pages
                ] == [("queued", FIRST_GENERATION, RETRIED_OUTCOME.attempt_count, None, ())]
