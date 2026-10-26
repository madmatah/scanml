"""The SQLite rows, read into the records of documents and pages, and the summary of a document's layout written into
them."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from scanmylib.adapters.sqlite.database import Database
from scanmylib.adapters.sqlite.rows import build_document_record, build_document_stats, encode_layout_summary
from scanmylib.domain.documents import LayoutSummary
from scanmylib.domain.ordering import Coverage
from scanmylib.domain.records import DocumentStats

DOCUMENT_ID = "0a000000-0000-4000-8000-000000000000"
MOMENT = "2026-10-12T20:00:00+02:00"
MOMENT_TIMESTAMP_SECONDS = datetime.fromisoformat(MOMENT).timestamp()
SUMMARY = LayoutSummary(
    DocumentStats(
        page_count=3,
        done_count=3,
        queued_count=0,
        processing_count=0,
        error_count=0,
        excluded_count=0,
        duplicate_count=0,
    ),
    Coverage(((1, 2),), 1),
    "page-1",
    3,
)
#: The json module escapes the en dash of the coverage's label.
STORED_SUMMARY = (
    r'{"stats": {"pages": 3, "done": 3, "queued": 0, "processing": 0, "error": 0, "excluded": 0, "duplicates": 0},'
    r' "coverage": {"ranges": [[1, 2]], "label": "1\u20132", "gaps": [], "min": 1, "max": 2, "unnumbered": 1},'
    r' "cover_page_id": "page-1", "pages_in_document": 3}'
)


@dataclass(frozen=True)
class StoredCounts:
    counts: dict[str, int]
    expected_stats: DocumentStats


@dataclass(frozen=True)
class ReadCounts:
    stored: StoredCounts
    stats: DocumentStats


class TestTheSqliteRows:
    class TestTheBuildDocumentStatsFunction:
        class TestWhenTheStoredCountsAreIncomplete:
            @pytest.fixture(
                params=[
                    StoredCounts(
                        {},
                        DocumentStats(
                            page_count=0,
                            done_count=0,
                            queued_count=0,
                            processing_count=0,
                            error_count=0,
                            excluded_count=0,
                            duplicate_count=0,
                        ),
                    ),
                    StoredCounts(
                        {"pages": 4, "done": 4},
                        DocumentStats(
                            page_count=4,
                            done_count=4,
                            queued_count=0,
                            processing_count=0,
                            error_count=0,
                            excluded_count=0,
                            duplicate_count=0,
                        ),
                    ),
                ],
                ids=["no-count", "only-some-counts"],
            )
            def read_counts(self, request: pytest.FixtureRequest) -> ReadCounts:
                stored: StoredCounts = request.param
                return ReadCounts(stored, build_document_stats(stored.counts))

            def test_should_count_zero_for_each_count_it_lacks(self, read_counts: ReadCounts) -> None:
                assert read_counts.stats == read_counts.stored.expected_stats

    class TestTheEncodeLayoutSummaryFunction:
        class TestWhenADocumentHasNumberedPages:
            @pytest.fixture
            def stored_summary(self) -> str:
                return encode_layout_summary(SUMMARY)

            def test_should_write_the_json_the_api_has_always_stored(self, stored_summary: str) -> None:
                assert stored_summary == STORED_SUMMARY

    class TestWhenTheSummaryOfALayoutIsStoredAndReadBack:
        @pytest.fixture
        def read_summaries(self, tmp_path: Path) -> Iterator[list[LayoutSummary]]:
            with contextlib.closing(Database(tmp_path / "scanmylib.db")) as database:
                database.execute(
                    "INSERT INTO documents (id, slug, title, kind, created_at, updated_at, updated_ts, layout)"
                    " VALUES (?, 'sample-cafe-guide', 'Sample Café Guide', 'book', ?, ?, ?, ?)",
                    (DOCUMENT_ID, MOMENT, MOMENT, MOMENT_TIMESTAMP_SECONDS, encode_layout_summary(SUMMARY)),
                )
                rows = database.all("SELECT * FROM documents WHERE id = ?", (DOCUMENT_ID,))
                records = [build_document_record(row) for row in rows]
                yield [
                    LayoutSummary(record.stats, record.coverage, record.cover_page_id, record.pages_in_document)
                    for record in records
                ]

        def test_should_read_back_the_summary_it_stored(self, read_summaries: list[LayoutSummary]) -> None:
            assert read_summaries == [SUMMARY]
