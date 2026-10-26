"""A document's rules: what a new one takes, the slug of its folder, the summary of its layout."""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from .ordering import Coverage, Layout, PageInput
from .records import DocumentChanges, DocumentStats, InvalidRequest
from .text import slugify

DEFAULT_KIND = "document"


@dataclass(frozen=True)
class NewDocument:
    title: str
    author: str
    kind: str
    notes: str
    unwarp: bool


def prepare_new_document(changes: DocumentChanges) -> NewDocument:
    if not changes.title:
        raise InvalidRequest("title is required to create a document")
    kind = changes.kind or DEFAULT_KIND
    return NewDocument(
        title=changes.title,
        author=changes.author or "",
        kind=kind,
        notes=changes.notes or "",
        unwarp=changes.unwarp if changes.unwarp is not None else kind == "book",
    )


def check_document_changes(changes: DocumentChanges) -> None:
    if changes.title is not None and not changes.title:
        raise InvalidRequest("title cannot be empty")


def propose_slugs(title: str) -> Iterator[str]:
    base = slugify(title)
    yield base
    for suffix in itertools.count(2):
        yield f"{base}-{suffix}"


@dataclass(frozen=True)
class LayoutSummary:
    stats: DocumentStats
    coverage: Coverage
    cover_page_id: str | None
    pages_in_document: int


def summarize_layout(pages: Sequence[PageInput], layout: Layout) -> LayoutSummary:
    return LayoutSummary(
        stats=DocumentStats(
            page_count=len(pages),
            done_count=sum(page.status == "done" for page in pages),
            queued_count=sum(page.status == "queued" for page in pages),
            processing_count=sum(page.status == "processing" for page in pages),
            error_count=sum(page.status == "error" for page in pages),
            excluded_count=sum(page.excluded for page in pages),
            duplicate_count=sum(placement.duplicate_of is not None for placement in layout.placements.values()),
        ),
        coverage=layout.coverage,
        cover_page_id=layout.order[0] if layout.order else None,
        pages_in_document=len(layout.reading_order),
    )
