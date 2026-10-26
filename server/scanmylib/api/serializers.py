"""JSON shapes of the Document and Page objects (docs/API.md)."""

from __future__ import annotations

from ..domain.records import DocumentRecord, PageRecord
from ..library import LibraryService

_OCR_FIELDS = ("engine", "duration_s", "at", "images", "chars")


def document_json(document: DocumentRecord, library: LibraryService) -> dict[str, object]:
    return {
        "id": document.id,
        "slug": document.slug,
        "title": document.title,
        "author": document.author,
        "kind": document.kind,
        "notes": document.notes,
        "unwarp": document.unwarp,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "stats": {
            "pages": document.stats.page_count,
            "done": document.stats.done_count,
            "queued": document.stats.queued_count,
            "processing": document.stats.processing_count,
            "error": document.stats.error_count,
            "excluded": document.stats.excluded_count,
            "duplicates": document.stats.duplicate_count,
        },
        "coverage": document.coverage.to_json(),
        "cover_thumb_url": f"/api/pages/{document.cover_page_id}/thumb" if document.cover_page_id else None,
        "folder": library.folder(document),
    }


def page_json(page: PageRecord) -> dict[str, object]:
    width, height = page.displayed_size
    done = page.status == "done"
    return {
        "id": page.id,
        "document_id": page.document_id,
        "key": page.key,
        "session_id": page.session_id,
        "seq": page.seq,
        "captured_at": page.captured_at,
        "uploaded_at": page.uploaded_at,
        "status": page.status,
        "error": page.error if page.status == "error" else None,
        "number": page.number.value if page.number else None,
        "number_end": page.number.end if page.number else None,
        "page_label": page.number.label if page.number else None,
        "number_source": page.number_source,
        "detected_numbers": list(page.detected_numbers),
        "hint_number": page.hint_number,
        "manual_number": page.manual_number,
        "excluded": page.excluded,
        "duplicate_of": page.duplicate_of,
        "in_document": page.in_document,
        "position": page.position,
        "placement": page.placement,
        "rotation": page.rotation,
        "width": width,
        "height": height,
        "ocr": {name: page.ocr.get(name) for name in _OCR_FIELDS} if done and page.ocr else None,
        "thumb_url": f"/api/pages/{page.id}/thumb",
        "image_url": f"/api/pages/{page.id}/image",
    }
