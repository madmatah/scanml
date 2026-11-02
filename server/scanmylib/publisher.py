"""Turns records into the library files read by agents, and into the sections a document's preview shows.

Methods doing file I/O are meant to run in a worker thread: they only use the
records they are given, never the database.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .application.clock import Clock
from .application.library_files import PublishedFiles
from .domain import assemble, timestamps
from .domain.records import DocumentRecord, PageRecord


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


@dataclass(frozen=True)
class DocumentSections:
    sections: tuple[assemble.Section, ...]
    markdown_by_page_key: Mapping[str, str]


class Publisher:
    def __init__(self, files: PublishedFiles, clock: Clock) -> None:
        self._files = files
        self._clock = clock

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
        generated_at = timestamps.iso(self._clock.now())
        self._files.write_index(
            assemble.render_index_markdown(entries, generated_at),
            assemble.render_index_metadata(entries, generated_at),
        )

    def read_document_sections(self, document: DocumentRecord, pages: Sequence[PageRecord]) -> DocumentSections:
        reading = _reading_order(pages)
        sections = assemble.document_sections(reading, numbered=any(e.number for e in reading))
        return DocumentSections(
            sections=tuple(sections),
            markdown_by_page_key={
                section.key: self._files.read_page_markdown(document.slug, section.key)
                for section in sections
                if isinstance(section, assemble.PageSection)
            },
        )
