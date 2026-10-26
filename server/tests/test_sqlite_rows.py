"""The SQLite rows, read into the records of documents and pages."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from scanmylib.adapters.sqlite.rows import build_document_stats
from scanmylib.domain.records import DocumentStats


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
