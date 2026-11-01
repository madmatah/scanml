"""The catalog of documents and pages in SQLite (adapters/sqlite/catalog.py): its transactions, the order of its lists,
and the pages it queues again."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from scanmylib.adapters.sqlite.catalog import SqliteCatalog
from scanmylib.adapters.sqlite.database import Database

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
