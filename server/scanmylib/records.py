"""Typed views of the database rows, and the inputs of library operations."""

from __future__ import annotations

import enum
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from .ordering import Coverage, PageInput, PageNumber

DEFAULT_KIND = "document"


class NotFound(LookupError):
    """No such document or page."""


class Conflict(Exception):
    """The request contradicts existing state (e.g. a page id used by another document)."""


class InvalidRequest(ValueError):
    """Semantically invalid input that the request schema cannot express."""


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    slug: str
    title: str
    author: str
    kind: str
    notes: str
    unwarp: bool
    created_at: str
    updated_at: str
    stats: dict[str, int]
    coverage: Coverage
    cover_page_id: str | None
    pages_in_document: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> DocumentRecord:
        layout = json.loads(row["layout"])
        coverage = layout.get("coverage") or {}
        return cls(
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


class OcrSummary(TypedDict):
    engine: str
    model: str
    duration_s: float
    at: str
    images: int
    chars: int


@dataclass(frozen=True)
class PageRecord:
    id: str
    document_id: str
    key: str
    scan_ext: str
    session_id: str | None
    seq: int | None
    captured_at: str
    captured_ts: float
    uploaded_at: str
    width: int
    height: int
    status: str
    error: str | None
    attempts: int
    generation: int
    rotation: int
    excluded: bool
    hint_number: int | None
    manual_number: int | None
    detected_numbers: tuple[str, ...]
    ocr: OcrSummary | None
    #: Place on the number line chosen by the user (PUT /api/documents/{id}/order).
    position: float | None
    number: PageNumber | None
    number_source: str | None
    duplicate_of: str | None
    in_document: bool
    #: How its place in the reading order was decided (ordering.PLACEMENT_*), None outside of it.
    placement: str | None
    #: Index of the page in the document's page list (reading order first).
    rank: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PageRecord:
        number = None
        if row["number"] is not None:
            number = PageNumber(row["number"], row["number_end"], bool(row["front_matter"]))
        return cls(
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

    @property
    def ordering_input(self) -> PageInput:
        return PageInput(
            id=self.id,
            session_id=self.session_id,
            seq=self.seq,
            captured_ts=self.captured_ts,
            status=self.status,
            excluded=self.excluded,
            manual_number=self.manual_number,
            hint_number=self.hint_number,
            detected_numbers=self.detected_numbers,
            position=self.position,
        )

    @property
    def displayed_size(self) -> tuple[int, int]:
        """Width and height of the page as it is OCRed (after its rotation)."""
        if self.rotation in (90, 270):
            return self.height, self.width
        return self.width, self.height


@dataclass(frozen=True)
class DocumentChanges:
    """Fields to set on a document; None means "leave unchanged"."""

    title: str | None = None
    author: str | None = None
    kind: str | None = None
    notes: str | None = None
    unwarp: bool | None = None


class _Unchanged(enum.Enum):
    TOKEN = 0


#: Marks a nullable field that the request did not mention.
UNCHANGED = _Unchanged.TOKEN


@dataclass(frozen=True)
class PageChanges:
    manual_number: int | _Unchanged | None = UNCHANGED
    excluded: bool | None = None
    rotation: int | None = None


@dataclass(frozen=True)
class PageUpload:
    page_id: str
    data: bytes
    session_id: str | None = None
    seq: int | None = None
    captured_at: datetime | None = None
    hint_number: int | None = None


@dataclass(frozen=True)
class PageClaim:
    """A page taken by the OCR loop; `generation` detects changes made meanwhile."""

    page_id: str
    document_id: str
    generation: int
    attempts: int
    key: str
    slug: str
    scan: Path
    rotation: int
    unwarp: bool
