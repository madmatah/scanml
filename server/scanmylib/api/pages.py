"""Page routes: upload, corrections, reprocessing, images."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from starlette.datastructures import FormData, UploadFile

from .. import clock
from ..domain.records import PageUpload
from ..images import MAX_UPLOAD_BYTES, SCAN_MEDIA_TYPES, ImageRejected
from .deps import ServicesDep, is_uuid, require_auth, require_uuid
from .schemas import PagePatchBody
from .serializers import page_json

router = APIRouter(dependencies=[Depends(require_auth)])


class _UploadFields(TypedDict):
    page_id: str
    session_id: str | None
    seq: int | None
    captured_at: datetime | None
    hint_number: int | None


def _optional_int(value: str | None, field: str, low: int, high: int) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        number = int(value.strip())
    except ValueError:
        raise HTTPException(422, f"{field} must be an integer") from None
    if not low <= number <= high:
        raise HTTPException(422, f"{field} must be between {low} and {high}")
    return number


def _upload_fields(
    page_id: str,
    session_id: str | None,
    seq: str | None,
    captured_at: str | None,
    page_number_hint: str | None,
) -> _UploadFields:
    session_id = (session_id or "").strip() or None
    if session_id is not None and not is_uuid(session_id):
        raise HTTPException(422, "session_id must be a lowercase hyphenated UUID")
    captured = None
    if captured_at and captured_at.strip():
        try:
            captured = clock.parse_client_time(captured_at)
        except ValueError:
            raise HTTPException(422, "captured_at must be an ISO-8601 time") from None
    return {
        "page_id": require_uuid(page_id.strip(), "page_id"),
        "session_id": session_id,
        "seq": _optional_int(seq, "seq", 0, 1_000_000),
        "captured_at": captured,
        "hint_number": _optional_int(page_number_hint, "page_number_hint", 1, 9999),
    }


def _form_text(form: FormData, name: str) -> str | None:
    value = form.get(name)
    return value if isinstance(value, str) else None


@router.post("/api/documents/{document_id}/pages", status_code=201)
async def upload_page(
    document_id: str, request: Request, response: Response, services: ServicesDep
) -> dict[str, object]:
    # The multipart body (up to 40 MiB) is read here, once require_auth has
    # accepted the request: File()/Form() parameters would make FastAPI read
    # and spool it before checking the credentials, for anyone on the LAN.
    async with request.form(max_files=1, max_fields=16) as form:
        file = form.get("file")
        page_id = _form_text(form, "page_id")
        if not isinstance(file, UploadFile) or page_id is None:
            raise HTTPException(422, "multipart fields file and page_id are required")
        fields = _upload_fields(
            page_id,
            _form_text(form, "session_id"),
            _form_text(form, "seq"),
            _form_text(form, "captured_at"),
            _form_text(form, "page_number_hint"),
        )
        data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file larger than 40 MiB")
    page, created = await services.library.add_page(document_id, PageUpload(data=data, **fields))
    response.status_code = 201 if created else 200
    return page_json(page)


@router.get("/api/pages/{page_id}")
async def get_page(page_id: str, services: ServicesDep) -> dict[str, object]:
    page = services.library.require_page(page_id)
    return {**page_json(page), "markdown": await services.library.page_markdown(page)}


@router.get("/api/pages/{page_id}/html")
async def page_html(page_id: str, services: ServicesDep) -> dict[str, object]:
    page = services.library.require_page(page_id)
    return {"html": await services.library.page_html(page)}


@router.patch("/api/pages/{page_id}")
async def patch_page(page_id: str, body: PagePatchBody, services: ServicesDep) -> dict[str, object]:
    return page_json(await services.library.patch_page(page_id, body.changes()))


@router.post("/api/pages/{page_id}/reprocess", status_code=202)
async def reprocess_page(page_id: str, services: ServicesDep) -> dict[str, object]:
    return page_json(services.library.reprocess_page(page_id))


@router.delete("/api/pages/{page_id}", status_code=204)
async def delete_page(page_id: str, services: ServicesDep) -> Response:
    if not await services.library.delete_page(page_id):
        raise HTTPException(404, "page not found")
    return Response(status_code=204)


@router.get("/api/pages/{page_id}/image")
async def page_image(page_id: str, services: ServicesDep) -> FileResponse:
    library = services.library
    page = library.require_page(page_id)
    scan = library.scan_path(page, library.require_document(page.document_id))
    if not scan.is_file():
        raise HTTPException(404, "scan not found")
    # The original photo of a page never changes.
    return FileResponse(
        scan, media_type=SCAN_MEDIA_TYPES[page.scan_ext], headers={"Cache-Control": "private, max-age=86400"}
    )


@router.get("/api/pages/{page_id}/thumb")
async def page_thumbnail(page_id: str, services: ServicesDep) -> FileResponse:
    page = services.library.require_page(page_id)
    try:
        thumbnail = await services.library.thumbnail(page)
    except (OSError, ImageRejected):
        raise HTTPException(404, "thumbnail not available") from None
    # Revalidated each time: it changes when the page is rotated.
    return FileResponse(thumbnail, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
