"""The rows of the SQLite database, read into the records of documents and pages."""

from __future__ import annotations

import json
import sqlite3

from ...domain.ordering import Coverage, PageNumber
from ...domain.records import DocumentRecord, PageClaim, PageRecord


def build_document_record(row: sqlite3.Row) -> DocumentRecord:
    layout = json.loads(row["layout"])
    coverage = layout.get("coverage") or {}
    return DocumentRecord(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        author=row["author"],
        kind=row["kind"],
        notes=row["notes"],
        unwarp=bool(row["unwarp"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stats=layout.get("stats") or {},
        coverage=Coverage(
            ranges=tuple((start, end) for start, end in coverage.get("ranges", [])),
            unnumbered=coverage.get("unnumbered", 0),
        ),
        cover_page_id=layout.get("cover_page_id"),
        pages_in_document=layout.get("pages_in_document", 0),
    )


def build_page_record(row: sqlite3.Row) -> PageRecord:
    number = None
    if row["number"] is not None:
        number = PageNumber(row["number"], row["number_end"], bool(row["front_matter"]))
    return PageRecord(
        id=row["id"],
        document_id=row["document_id"],
        key=row["key"],
        scan_ext=row["scan_ext"],
        session_id=row["session_id"],
        seq=row["seq"],
        captured_at=row["captured_at"],
        captured_ts=row["captured_ts"],
        uploaded_at=row["uploaded_at"],
        width=row["width"],
        height=row["height"],
        status=row["status"],
        error=row["error"],
        attempts=row["attempts"],
        generation=row["generation"],
        rotation=row["rotation"],
        excluded=bool(row["excluded"]),
        hint_number=row["hint_number"],
        manual_number=row["manual_number"],
        detected_numbers=tuple(json.loads(row["detected_numbers"])),
        ocr=json.loads(row["ocr"]) if row["ocr"] else None,
        position=row["position"],
        number=number,
        number_source=row["number_source"],
        duplicate_of=row["duplicate_of"],
        in_document=bool(row["in_document"]),
        placement=row["placement"],
        rank=row["rank"],
    )


def build_page_claim(row: sqlite3.Row) -> PageClaim:
    return PageClaim(
        page_id=row["id"],
        document_id=row["document_id"],
        generation=row["generation"],
        attempts=row["attempts"],
        key=row["key"],
        slug=row["slug"],
        scan_ext=row["scan_ext"],
        rotation=row["rotation"],
        unwarp=bool(row["unwarp"]),
    )
