"""Turns records into the library files read by agents, and into HTML previews.

Methods doing file I/O are meant to run in a worker thread: they only use the
records they are given, never the database.
"""

from __future__ import annotations

from collections.abc import Sequence

from . import clock, preview
from .domain import assemble
from .records import DocumentRecord, PageRecord
from .storage import LibraryFiles


def files_url(document_id: str) -> str:
    """URL of the endpoint serving the files of a document folder."""
    return f"/api/documents/{document_id}/files"


def _meta(document: DocumentRecord) -> assemble.DocumentMeta:
    return assemble.DocumentMeta(
        id=document.id,
        slug=document.slug,
        title=document.title,
        author=document.author,
        kind=document.kind,
        notes=document.notes,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _entry(page: PageRecord) -> assemble.PageEntry:
    return assemble.PageEntry(
        id=page.id,
        key=page.key,
        status=page.status,
        number=page.number,
        number_source=page.number_source,
        in_document=page.in_document,
        excluded=page.excluded,
        duplicate_of=page.duplicate_of,
        position=page.position,
        placement=page.placement,
        session_id=page.session_id,
        seq=page.seq,
        captured_at=page.captured_at,
        scan_file=f"scans/{page.key}.{page.scan_ext}",
        image_count=page.ocr["images"] if page.ocr else 0,
        engine=page.ocr["model"] if page.ocr else None,
    )


def _reading_order(pages: Sequence[PageRecord]) -> list[assemble.PageEntry]:
    """Entries of the pages of document.md; `pages` must be in the API order (by rank)."""
    return [_entry(page) for page in pages if page.in_document]


class Publisher:
    def __init__(self, files: LibraryFiles) -> None:
        self._files = files

    def write_document(self, document: DocumentRecord, pages: Sequence[PageRecord]) -> None:
        """Rewrite document.md and document.json (`pages` in the API order, by rank)."""
        reading = _reading_order(pages)
        sections = assemble.document_sections(reading, numbered=any(e.number for e in reading))
        source = assemble.source_label([e.engine for e in reading if e.engine])
        meta = _meta(document)
        markdown = assemble.render_document_markdown(
            meta,
            sections,
            lambda key: self._files.read_page_markdown(document.slug, key),
            source=source,
            pages_scanned=len(reading),
            coverage=document.coverage,
        )
        metadata = assemble.render_document_metadata(
            meta,
            [_entry(page) for page in pages],
            source=source,
            pages_scanned=len(reading),
            coverage=document.coverage,
        )
        self._files.write_document(document.slug, markdown, metadata)

    def write_index(self, documents: Sequence[DocumentRecord]) -> None:
        """Rewrite INDEX.md and library.json."""
        entries = [
            assemble.IndexEntry(_meta(document), document.pages_in_document, document.coverage)
            for document in documents
        ]
        generated_at = clock.iso(clock.now())
        self._files.write_index(
            assemble.render_index_markdown(entries, generated_at),
            assemble.render_index_metadata(entries, generated_at),
        )

    def page_html(self, document: DocumentRecord, page: PageRecord) -> str:
        markdown = self._files.read_page_markdown(document.slug, page.key)
        return preview.render_markdown(markdown, files_url(document.id))

    def document_html(self, document: DocumentRecord, pages: Sequence[PageRecord]) -> str:
        reading = _reading_order(pages)
        sections = assemble.document_sections(reading, numbered=any(e.number for e in reading))
        return preview.render_document(
            document.title,
            sections,
            lambda key: self._files.read_page_markdown(document.slug, key),
            files_url(document.id),
        )
