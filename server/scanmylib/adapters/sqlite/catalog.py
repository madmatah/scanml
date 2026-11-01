"""The catalog of documents and pages, in the SQLite database."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager

from ...application.catalog import QueueCounts
from ...domain.documents import LayoutSummary
from ...domain.ordering import Placement
from ...domain.records import DocumentRecord, PageRecord
from .database import Database
from .rows import build_document_record, build_page_record, encode_layout_summary

_LAYOUT_COLUMNS = (
    "number",
    "number_end",
    "front_matter",
    "number_source",
    "page_label",
    "duplicate_of",
    "in_document",
    "placement",
    "rank",
)


class SqliteCatalog:
    def __init__(self, database: Database) -> None:
        self._database = database

    def open_transaction(self) -> AbstractContextManager[None]:
        return self._database.transaction()

    def list_documents(self) -> list[DocumentRecord]:
        rows = self._database.all("SELECT * FROM documents ORDER BY updated_ts DESC, id")
        return [build_document_record(row) for row in rows]

    def get_document(self, document_id: str) -> DocumentRecord | None:
        row = self._database.one("SELECT * FROM documents WHERE id = ?", (document_id,))
        return build_document_record(row) if row else None

    def list_document_ids(self) -> list[str]:
        return [row["id"] for row in self._database.all("SELECT id FROM documents")]

    def is_slug_taken(self, slug: str) -> bool:
        return self._database.one("SELECT 1 FROM documents WHERE slug = ?", (slug,)) is not None

    def list_pages(self, document_id: str) -> list[PageRecord]:
        rows = self._database.all(
            "SELECT * FROM pages WHERE document_id = ? ORDER BY rank, captured_ts, id",
            (document_id,),
        )
        return [build_page_record(row) for row in rows]

    def get_page(self, page_id: str) -> PageRecord | None:
        row = self._database.one("SELECT * FROM pages WHERE id = ?", (page_id,))
        return build_page_record(row) if row else None

    def list_page_ids(self, document_id: str) -> list[str]:
        return [row["id"] for row in self._database.all("SELECT id FROM pages WHERE document_id = ?", (document_id,))]

    def is_key_taken(self, document_id: str, key: str) -> bool:
        clash = self._database.one("SELECT 1 FROM pages WHERE document_id = ? AND key = ?", (document_id, key))
        return clash is not None

    def count_queue(self) -> QueueCounts:
        counts = dict.fromkeys(("queued", "processing", "error", "done"), 0)
        for row in self._database.all("SELECT status, COUNT(*) AS n FROM pages GROUP BY status"):
            counts[row["status"]] = row["n"]
        return QueueCounts(
            queued_count=counts["queued"],
            processing_count=counts["processing"],
            error_count=counts["error"],
            done_count=counts["done"],
        )

    def requeue_interrupted_pages(self) -> int:
        return self._database.execute("UPDATE pages SET status = 'queued' WHERE status = 'processing'").rowcount

    def store_layout(self, document_id: str, placements: Mapping[str, Placement], summary: LayoutSummary) -> None:
        rows = self._database.all("SELECT * FROM pages WHERE document_id = ?", (document_id,))
        for row in rows:
            placement = placements[row["id"]]
            number = placement.number
            values = (
                number.value if number else None,
                number.end if number else None,
                int(bool(number and number.front_matter)),
                placement.source,
                number.label if number else None,
                placement.duplicate_of,
                int(placement.in_document),
                placement.placed_by,
                placement.rank,
            )
            if values != tuple(row[column] for column in _LAYOUT_COLUMNS):
                assignments = ", ".join(f"{column} = ?" for column in _LAYOUT_COLUMNS)
                self._database.execute(
                    f"UPDATE pages SET {assignments} WHERE id = ?",  # noqa: S608 (column names from the code, values as ? parameters)
                    (*values, row["id"]),
                )
        self._database.execute(
            "UPDATE documents SET layout = ? WHERE id = ?", (encode_layout_summary(summary), document_id)
        )
