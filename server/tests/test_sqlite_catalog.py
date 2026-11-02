"""The catalog of documents and pages in SQLite (adapters/sqlite/catalog.py): its transactions, the order of its lists,
the changes of its documents, and the pages it queues again."""

from __future__ import annotations

import collections.abc
import contextlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from scanmylib.adapters.sqlite.catalog import SqliteCatalog
from scanmylib.adapters.sqlite.database import Database
from scanmylib.domain.documents import NewDocument
from scanmylib.domain.records import DocumentChanges, DocumentRecord, PageRecord

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


class AbandonedTransaction(Exception):
    pass


@dataclass(frozen=True)
class RequeuedPages:
    requeued_count: int
    page_statuses: list[str]


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
            def update_the_document(
                self, tmp_path: Path, request: pytest.FixtureRequest
            ) -> collections.abc.Callable[[], None]:
                database = Database(tmp_path / "scanmylib.db")
                request.addfinalizer(database.close)
                catalog = SqliteCatalog(database)
                add_example_document(catalog, FIRST_ADDED_DOCUMENT_ID, added_at=FIRST_MOMENT)
                return lambda: catalog.update_document(FIRST_ADDED_DOCUMENT_ID, DocumentChanges())

            def test_should_refuse_them_since_an_update_sets_at_least_one(
                self, update_the_document: collections.abc.Callable[[], None]
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
