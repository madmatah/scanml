"""The records of documents and pages, and the inputs of library operations."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from .ordering import Coverage, PageInput, PageNumber

DEFAULT_KIND = "document"


class NotFound(LookupError):
    """No such document or page."""


class Conflict(Exception):
    """The change contradicts the library's state (e.g. a page id used by another document)."""


class InvalidRequest(ValueError):
    """An operation's input that breaks a rule its types cannot express."""


@dataclass(frozen=True)
class DocumentStats:
    page_count: int
    done_count: int
    queued_count: int
    processing_count: int
    error_count: int
    excluded_count: int
    duplicate_count: int


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
    stats: DocumentStats
    coverage: Coverage
    cover_page_id: str | None
    pages_in_document: int


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
    #: Place on the number line chosen by the user, when they reorder the pages of the document.
    position: float | None
    number: PageNumber | None
    number_source: str | None
    duplicate_of: str | None
    in_document: bool
    #: How its place in the reading order was decided (ordering.PLACEMENT_*), None outside of it.
    placement: str | None
    #: Index of the page in the document's page list (reading order first).
    rank: int

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


#: Marks a nullable field that the operation leaves as it is.
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
    scan_ext: str
    rotation: int
    unwarp: bool
