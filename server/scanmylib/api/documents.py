"""Document routes: CRUD, page order, assembled Markdown/HTML, files and export."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse

from ..domain.records import DocumentRecord
from ..export import iter_zip
from .deps import Services, ServicesDep, require_auth, require_uuid
from .schemas import DocumentBody, PageOrderBody
from .serializers import document_json, page_json

router = APIRouter(prefix="/api/documents", dependencies=[Depends(require_auth)])

_FILE_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _document(services: Services, document_id: str) -> DocumentRecord:
    return services.library.require_document(document_id)


def _document_with_pages(services: Services, document: DocumentRecord) -> dict[str, object]:
    return {
        **document_json(document, services.library),
        "pages": [page_json(page) for page in services.library.list_pages(document.id)],
    }


@router.get("")
async def list_documents(services: ServicesDep) -> dict[str, object]:
    library = services.library
    return {"documents": [document_json(d, library) for d in library.list_documents()]}


@router.put("/{document_id}")
async def put_document(
    document_id: str, body: DocumentBody, response: Response, services: ServicesDep
) -> dict[str, object]:
    require_uuid(document_id, "document id")
    document, created = await services.library.put_document(document_id, body.changes())
    response.status_code = 201 if created else 200
    return document_json(document, services.library)


@router.get("/{document_id}")
async def get_document(document_id: str, services: ServicesDep) -> dict[str, object]:
    return _document_with_pages(services, _document(services, document_id))


@router.patch("/{document_id}")
async def patch_document(document_id: str, body: DocumentBody, services: ServicesDep) -> dict[str, object]:
    document = services.library.update_document(document_id, body.changes())
    return document_json(document, services.library)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, services: ServicesDep) -> Response:
    if not await services.library.delete_document(document_id):
        raise HTTPException(404, "document not found")
    return Response(status_code=204)


@router.put("/{document_id}/order")
async def put_page_order(document_id: str, body: PageOrderBody, services: ServicesDep) -> dict[str, object]:
    """Reading order chosen by the user; 409 if `page_ids` is not exactly the current reading order."""
    return _document_with_pages(services, services.library.reorder_pages(document_id, body.page_ids))


@router.delete("/{document_id}/order")
async def delete_page_order(document_id: str, services: ServicesDep) -> dict[str, object]:
    """Back to the automatic order (page numbers, scanning sessions)."""
    return _document_with_pages(services, services.library.clear_page_order(document_id))


@router.get("/{document_id}/markdown")
async def document_markdown(document_id: str, services: ServicesDep) -> Response:
    document = _document(services, document_id)
    markdown = await services.library.document_markdown(document)
    return Response(markdown, media_type="text/markdown; charset=utf-8")


@router.get("/{document_id}/html")
async def document_html(document_id: str, services: ServicesDep) -> dict[str, object]:
    document = _document(services, document_id)
    return {"html": await services.library.document_html(document)}


@router.get("/{document_id}/export.zip")
async def export_zip(
    document_id: str,
    services: ServicesDep,
    scans: Annotated[bool, Query(description="include the original photos")] = False,
) -> StreamingResponse:
    document = _document(services, document_id)
    entries = await services.library.export_entries(document, include_scans=scans)
    return StreamingResponse(
        iter_zip(entries),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{document.slug}.zip"'},
    )


@router.get("/{document_id}/files/{path:path}")
async def document_file(document_id: str, path: str, services: ServicesDep) -> FileResponse:
    document = _document(services, document_id)
    file = services.library.document_file(document, path)
    if file is None:
        raise HTTPException(404, "file not found")
    return FileResponse(file, media_type=_FILE_TYPES[file.suffix], headers={"Cache-Control": "no-cache"})
