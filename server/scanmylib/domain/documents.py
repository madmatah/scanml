"""A document's rules: the summary of its layout."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .ordering import Coverage, Layout, PageInput
from .records import DocumentStats


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
