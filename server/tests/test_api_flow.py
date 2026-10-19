"""End-to-end API flows: the real app, the OCR loop and the fake sandbox on a Unix socket."""

from __future__ import annotations

import errno
import io
import json
import re
import threading
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from markdown_it import MarkdownIt
from PIL import Image

from scanmylib.devtools.fake_ocr import ParseRequest
from scanmylib.library import LibraryService
from scanmylib.publisher import Publisher
from scanmylib.records import DocumentRecord, PageRecord
from scanmylib.storage import LibraryFiles
from support import (
    AUTH,
    BROKEN_EXIF,
    CORRUPT_PNGS,
    Answer,
    capture_answer,
    create_document,
    jpeg,
    list_labels,
    mpo,
    new_id,
    page_image,
    read_until,
    running_api,
    upload,
    wait_for,
    wait_until_processed,
)

SLUG = "sample-cafe-guide"
NO_NUMBER = 0  # page_image(0): the fake OCR finds no page number
NO_STATS = {"pages": 0, "done": 0, "queued": 0, "processing": 0, "error": 0, "excluded": 0, "duplicates": 0}


def read_document(client: TestClient, document_id: str) -> dict[str, Any]:
    response = client.get(f"/api/documents/{document_id}", headers=AUTH)
    response.raise_for_status()
    document: dict[str, Any] = response.json()
    return document


def measure_image(content: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(content)).size


def list_trashed_contents(library_dir: Path) -> list[list[str]]:
    trash = sorted((library_dir / ".trash").iterdir())
    return [sorted(trashed_file.name for trashed_file in trashed.iterdir()) for trashed in trash]


@dataclass(frozen=True)
class DocumentLifecycle:
    created: Answer
    is_folder_created: bool
    updated: Answer
    patched: dict[str, Any]
    markdown_type: str
    markdown: str
    deletion_status: int
    status_once_deleted: int
    second_deletion_status: int
    is_folder_left: bool
    trashed_names: list[str]
    trashed_contents: list[list[str]]
    trashed_contents_after_second_deletion: list[list[str]]


@dataclass(frozen=True)
class NewDocuments:
    book: dict[str, Any]
    flat_book: dict[str, Any]
    letter: dict[str, Any]


@dataclass(frozen=True)
class InvalidDocumentRequests:
    creation_statuses: dict[str, int]
    empty_title_status: int
    unknown_document_status: int


@dataclass(frozen=True)
class LibraryDocuments:
    first_id: str
    second_id: str
    third_id: str
    slugs: dict[str, str]
    listed_after_change: list[str]


@dataclass(frozen=True)
class PageFiles:
    has_scan: bool
    has_markdown: bool
    has_illustration: bool
    ocr_key: str


@dataclass(frozen=True)
class BookScannedOutOfOrder:
    upload_statuses: list[int]
    document: dict[str, Any]
    markdown: str
    markdown_file: str
    page_files: dict[str, PageFiles]
    metadata: dict[str, Any]
    index: str
    library: dict[str, Any]
    status: dict[str, Any]


@dataclass(frozen=True)
class PageViews:
    document_id: str
    page: dict[str, Any]
    detail: dict[str, Any]
    page_html: str
    document_html: str
    illustration_status: int
    illustration_type: str
    scan_type: str
    scan: bytes
    thumbnail_cache_control: str
    thumbnail_size: tuple[int, int]


@dataclass(frozen=True)
class RepeatedUpload:
    first: Answer
    second: Answer
    parse_request_count: int
    scan_count: int
    number: int
    other_document_status: int


@dataclass(frozen=True)
class ConcurrentUploads:
    statuses: dict[str, int]
    stored_slugs: list[str]
    scan_folders: list[str]
    owner_id: str
    first_document_id: str
    thumbnail_pixel: tuple[int, int, int]


@dataclass(frozen=True)
class UploadWithMetadata:
    page_id: str
    session_id: str
    page: dict[str, Any]


@dataclass(frozen=True)
class RefusedUploads:
    unknown_document_status: int
    missing_file_status: int
    missing_page_id_status: int
    non_image_status: int
    unsupported_format_status: int
    oversized_status: int
    corrupt_statuses: dict[str, int]
    page_count: int


@dataclass(frozen=True)
class CameraPhotos:
    multi_picture_status: int
    broken_exif_status: int
    read_pages: list[tuple[str, int]]
    multi_picture_scan_type: str


@dataclass(frozen=True)
class ConfinedFile:
    status: int
    is_secret_served: bool


@dataclass(frozen=True)
class ConcurrentPreviews:
    statuses: list[int]
    peak_renders: int


@dataclass(frozen=True)
class ServedFile:
    status: int
    content_type: str


@dataclass(frozen=True)
class CorrectedDocument:
    pages: list[dict[str, Any]]
    document_once_read: dict[str, Any]
    numbered_by_hand: dict[str, Any]
    labels_numbered_by_hand: list[str | None]
    cleared: dict[str, Any]
    exclusion: Answer
    markdown_after_exclusion: str
    rotation_by_45_degrees_status: int
    page_number_zero_status: int
    unknown_page_status: int


@dataclass(frozen=True)
class RotatedPage:
    number_before: int | None
    thumbnail_size_before: tuple[int, int]
    rotated: dict[str, Any]
    turned_page: dict[str, Any]
    last_request: ParseRequest
    thumbnail_size_after: tuple[int, int]


@dataclass(frozen=True)
class ReprocessedPage:
    key: str
    reprocessing: Answer
    parse_request_count: int
    status: str
    trashed_names: list[str]
    unknown_page_status: int


@dataclass(frozen=True)
class DeletedPage:
    kept_id: str
    deleted_key: str
    deletion_status: int
    second_deletion_status: int
    status_once_deleted: int
    is_scan_left: bool
    trashed_contents: list[list[str]]
    trashed_contents_after_second_deletion: list[list[str]]
    page_ids: list[str]
    markdown: str


@dataclass(frozen=True)
class RewriteAfterAFailure:
    kept_key: str
    deleted_key: str
    deletion_status: int
    markdown: str


@dataclass(frozen=True)
class ExportedDocument:
    key: str
    content_type: str
    content_disposition: str
    names: list[str]
    first_bad_file: str | None
    exported_scan: bytes
    exported_markdown: str


@dataclass(frozen=True)
class HostilePage:
    key: str
    stored_markdown: str
    illustrations: list[str]
    html: str
    document_markdown: str
    rendered: str


@dataclass(frozen=True)
class SentPage:
    page_id: str
    params: dict[str, str]


@pytest.fixture(scope="module")
def document_lifecycle(tmp_path_factory: pytest.TempPathFactory) -> DocumentLifecycle:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        path = f"/api/documents/{new_id()}"
        folder = api.settings.library_dir / SLUG
        created = capture_answer(client.put(path, json={"title": "  Sample Café\tGuide  "}, headers=AUTH))
        is_folder_created = folder.is_dir()
        update = {
            "title": "Sample Café Guide, volume 1",
            "author": "J. Doe",
            "kind": "book",
            "notes": "a\r\nb",
            "unwarp": True,
        }
        updated = capture_answer(client.put(path, json=update, headers=AUTH))
        patched = client.patch(path, json={"author": "Jane Doe"}, headers=AUTH).json()
        markdown = client.get(f"{path}/markdown", headers=AUTH)
        deletion_status = client.delete(path, headers=AUTH).status_code
        trashed_names = sorted(trashed.name for trashed in (api.settings.library_dir / ".trash").iterdir())
        trashed_contents = list_trashed_contents(api.settings.library_dir)
        status_once_deleted = client.get(path, headers=AUTH).status_code
        is_folder_left = folder.exists()
        second_deletion_status = client.delete(path, headers=AUTH).status_code
        return DocumentLifecycle(
            created=created,
            is_folder_created=is_folder_created,
            updated=updated,
            patched=patched,
            markdown_type=markdown.headers["content-type"],
            markdown=markdown.text,
            deletion_status=deletion_status,
            status_once_deleted=status_once_deleted,
            second_deletion_status=second_deletion_status,
            is_folder_left=is_folder_left,
            trashed_names=trashed_names,
            trashed_contents=trashed_contents,
            trashed_contents_after_second_deletion=list_trashed_contents(api.settings.library_dir),
        )


@pytest.fixture(scope="module")
def new_documents(tmp_path_factory: pytest.TempPathFactory) -> NewDocuments:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        return NewDocuments(
            book=client.put(f"/api/documents/{new_id()}", json={"title": "Book", "kind": "book"}, headers=AUTH).json(),
            flat_book=client.put(
                f"/api/documents/{new_id()}", json={"title": "Flat book", "kind": "book", "unwarp": False}, headers=AUTH
            ).json(),
            letter=client.put(
                f"/api/documents/{new_id()}", json={"title": "Letter", "kind": "document"}, headers=AUTH
            ).json(),
        )


@pytest.fixture(scope="module")
def invalid_document_requests(tmp_path_factory: pytest.TempPathFactory) -> InvalidDocumentRequests:
    creations = {
        "an-id-that-is-not-a-uuid": ("/api/documents/not-a-uuid", {"title": "x"}),
        "an-uppercase-id": (f"/api/documents/{new_id().upper()}", {"title": "x"}),
        "no-title": (f"/api/documents/{new_id()}", {"author": "no title"}),
        "a-blank-title": (f"/api/documents/{new_id()}", {"title": "   "}),
        "an-unknown-kind": (f"/api/documents/{new_id()}", {"title": "x", "kind": "magazine"}),
        "a-title-of-301-characters": (f"/api/documents/{new_id()}", {"title": "x" * 301}),
    }
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        creation_statuses = {
            name: client.put(path, json=fields, headers=AUTH).status_code for name, (path, fields) in creations.items()
        }
        document_id = create_document(client)
        return InvalidDocumentRequests(
            creation_statuses=creation_statuses,
            empty_title_status=client.patch(
                f"/api/documents/{document_id}", json={"title": ""}, headers=AUTH
            ).status_code,
            unknown_document_status=client.patch(
                f"/api/documents/{new_id()}", json={"title": "x"}, headers=AUTH
            ).status_code,
        )


@pytest.fixture(scope="module")
def library_documents(tmp_path_factory: pytest.TempPathFactory) -> LibraryDocuments:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        first = create_document(client, "Letters")
        second = create_document(client, "Letters")
        third = create_document(client, "Complete Phœnix Résumés")
        listed = client.get("/api/documents", headers=AUTH).json()["documents"]
        client.patch(f"/api/documents/{first}", json={"notes": "résumé"}, headers=AUTH)
        listed_after_change = client.get("/api/documents", headers=AUTH).json()["documents"]
        return LibraryDocuments(
            first_id=first,
            second_id=second,
            third_id=third,
            slugs={document["id"]: document["slug"] for document in listed},
            listed_after_change=[document["id"] for document in listed_after_change],
        )


@pytest.fixture(scope="module")
def repeated_upload(tmp_path_factory: pytest.TempPathFactory) -> RepeatedUpload:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client)
        page_id = new_id()
        first = capture_answer(upload(client, document_id, page_image(7), page_id=page_id))
        second = capture_answer(upload(client, document_id, page_image(8), page_id=page_id))
        wait_until_processed(client, document_id)
        other = create_document(client, "Other")
        return RepeatedUpload(
            first=first,
            second=second,
            parse_request_count=len(api.fake_ocr.requests),
            scan_count=len(list((api.settings.library_dir / SLUG / "scans").iterdir())),
            number=read_document(client, document_id)["pages"][0]["number"],
            other_document_status=upload(client, other, page_image(7), page_id=page_id).status_code,
        )


@pytest.fixture(scope="module")
def corrected_document(tmp_path_factory: pytest.TempPathFactory) -> CorrectedDocument:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client)
        session = new_id()
        scans = [page_image(10), page_image(NO_NUMBER), page_image(12), page_image(12)]
        pages = [
            upload(
                client,
                document_id,
                scan,
                session_id=session,
                seq=seq,
                captured_at=f"2026-10-12T20:00:0{seq}+02:00",
            ).json()
            for seq, scan in enumerate(scans)
        ]
        document_once_read = wait_until_processed(client, document_id)
        earlier_scan = f"/api/pages/{pages[2]['id']}"
        numbered_by_hand = client.patch(earlier_scan, json={"manual_number": 13}, headers=AUTH).json()
        labels_numbered_by_hand = list_labels(read_document(client, document_id))
        cleared = client.patch(earlier_scan, json={"manual_number": None}, headers=AUTH).json()
        first_page = f"/api/pages/{pages[0]['id']}"
        exclusion = capture_answer(client.patch(first_page, json={"excluded": True}, headers=AUTH))
        return CorrectedDocument(
            pages=pages,
            document_once_read=document_once_read,
            numbered_by_hand=numbered_by_hand,
            labels_numbered_by_hand=labels_numbered_by_hand,
            cleared=cleared,
            exclusion=exclusion,
            markdown_after_exclusion=client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text,
            rotation_by_45_degrees_status=client.patch(first_page, json={"rotation": 45}, headers=AUTH).status_code,
            page_number_zero_status=client.patch(first_page, json={"manual_number": 0}, headers=AUTH).status_code,
            unknown_page_status=client.patch(
                f"/api/pages/{new_id()}", json={"excluded": True}, headers=AUTH
            ).status_code,
        )


@pytest.fixture(scope="module")
def rotated_page(tmp_path_factory: pytest.TempPathFactory) -> RotatedPage:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client)
        # 1204×1500: the fake engine finds no number (variant 4); rotated: 1500×1204, page 204.
        page = upload(client, document_id, jpeg(1204, 1500)).json()
        wait_until_processed(client, document_id)
        number_before = client.get(f"/api/pages/{page['id']}", headers=AUTH).json()["number"]
        thumbnail_size_before = measure_image(client.get(page["thumb_url"], headers=AUTH).content)
        rotated = client.patch(f"/api/pages/{page['id']}", json={"rotation": 90}, headers=AUTH).json()
        wait_until_processed(client, document_id)
        return RotatedPage(
            number_before=number_before,
            thumbnail_size_before=thumbnail_size_before,
            rotated=rotated,
            turned_page=client.get(f"/api/pages/{page['id']}", headers=AUTH).json(),
            last_request=api.fake_ocr.requests[-1],
            thumbnail_size_after=measure_image(client.get(page["thumb_url"], headers=AUTH).content),
        )


@pytest.fixture(scope="module")
def reprocessed_page(tmp_path_factory: pytest.TempPathFactory) -> ReprocessedPage:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client)
        page = upload(client, document_id, page_image(3)).json()
        wait_until_processed(client, document_id)
        reprocessing = capture_answer(client.post(f"/api/pages/{page['id']}/reprocess", headers=AUTH))
        wait_until_processed(client, document_id)
        return ReprocessedPage(
            key=page["key"],
            reprocessing=reprocessing,
            parse_request_count=len(api.fake_ocr.requests),
            status=client.get(f"/api/pages/{page['id']}", headers=AUTH).json()["status"],
            trashed_names=[trashed.name for trashed in (api.settings.library_dir / ".trash").iterdir()],
            unknown_page_status=client.post(f"/api/pages/{new_id()}/reprocess", headers=AUTH).status_code,
        )


@pytest.fixture(scope="module")
def deleted_page(tmp_path_factory: pytest.TempPathFactory) -> DeletedPage:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client)
        kept = upload(client, document_id, page_image(1)).json()
        deleted = upload(client, document_id, page_image(2)).json()
        wait_until_processed(client, document_id)
        page_path = f"/api/pages/{deleted['id']}"
        deletion_status = client.delete(page_path, headers=AUTH).status_code
        status_once_deleted = client.get(page_path, headers=AUTH).status_code
        is_scan_left = (api.settings.library_dir / SLUG / "scans" / f"{deleted['key']}.jpg").exists()
        trashed_contents = list_trashed_contents(api.settings.library_dir)
        page_ids = [page["id"] for page in read_document(client, document_id)["pages"]]
        markdown = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
        second_deletion_status = client.delete(page_path, headers=AUTH).status_code
        return DeletedPage(
            kept_id=kept["id"],
            deleted_key=deleted["key"],
            deletion_status=deletion_status,
            second_deletion_status=second_deletion_status,
            status_once_deleted=status_once_deleted,
            is_scan_left=is_scan_left,
            trashed_contents=trashed_contents,
            trashed_contents_after_second_deletion=list_trashed_contents(api.settings.library_dir),
            page_ids=page_ids,
            markdown=markdown,
        )


@pytest.fixture(scope="module")
def exported_document(tmp_path_factory: pytest.TempPathFactory) -> ExportedDocument:
    with running_api(tmp_path_factory.mktemp("api")) as api:
        client = api.client
        document_id = create_document(client)
        page = upload(client, document_id, page_image(9)).json()
        wait_until_processed(client, document_id)
        without_scans = client.get(f"/api/documents/{document_id}/export.zip", headers=AUTH)
        with_scans = client.get(f"/api/documents/{document_id}/export.zip?scans=1", headers=AUTH)
    archive_with_scans = zipfile.ZipFile(io.BytesIO(with_scans.content))
    return ExportedDocument(
        key=page["key"],
        content_type=without_scans.headers["content-type"],
        content_disposition=without_scans.headers["content-disposition"],
        names=zipfile.ZipFile(io.BytesIO(without_scans.content)).namelist(),
        first_bad_file=archive_with_scans.testzip(),
        exported_scan=archive_with_scans.read(f"{SLUG}/scans/{page['key']}.jpg"),
        exported_markdown=archive_with_scans.read(f"{SLUG}/document.md").decode(),
    )


class TestADocument:
    class TestWhenItIsCreated:
        def test_should_answer_created(self, document_lifecycle: DocumentLifecycle) -> None:
            assert document_lifecycle.created.status == 201

        def test_should_collapse_the_spaces_of_its_title(self, document_lifecycle: DocumentLifecycle) -> None:
            assert document_lifecycle.created.body["title"] == "Sample Café Guide"

        def test_should_make_its_slug_from_its_title_without_accents(
            self, document_lifecycle: DocumentLifecycle
        ) -> None:
            assert document_lifecycle.created.body["slug"] == SLUG

        def test_should_default_its_author_kind_notes_and_unwarping(
            self, document_lifecycle: DocumentLifecycle
        ) -> None:
            document = document_lifecycle.created.body
            assert (document["author"], document["kind"], document["notes"], document["unwarp"]) == (
                "",
                "document",
                "",
                False,
            )

        def test_should_count_no_page(self, document_lifecycle: DocumentLifecycle) -> None:
            assert document_lifecycle.created.body["stats"] == NO_STATS

        def test_should_cover_no_page(self, document_lifecycle: DocumentLifecycle) -> None:
            assert document_lifecycle.created.body["coverage"]["label"] == ""

        def test_should_have_no_cover(self, document_lifecycle: DocumentLifecycle) -> None:
            assert document_lifecycle.created.body["cover_thumb_url"] is None

        def test_should_show_its_folder_on_the_host(self, document_lifecycle: DocumentLifecycle) -> None:
            assert document_lifecycle.created.body["folder"] == f"/home/user/Documents/ScanMyLib/{SLUG}"

        def test_should_create_its_folder_in_the_library(self, document_lifecycle: DocumentLifecycle) -> None:
            assert document_lifecycle.is_folder_created is True

        class TestWhenItIsUpdated:
            def test_should_answer_ok(self, document_lifecycle: DocumentLifecycle) -> None:
                assert document_lifecycle.updated.status == 200

            def test_should_keep_its_slug_so_that_its_folder_never_moves(
                self, document_lifecycle: DocumentLifecycle
            ) -> None:
                assert document_lifecycle.updated.body["slug"] == SLUG

            def test_should_end_the_lines_of_its_notes_with_line_feeds(
                self, document_lifecycle: DocumentLifecycle
            ) -> None:
                assert document_lifecycle.updated.body["notes"] == "a\nb"

            class TestWhenItIsPatched:
                def test_should_change_only_the_field_patched(self, document_lifecycle: DocumentLifecycle) -> None:
                    patched = document_lifecycle.patched
                    assert (patched["title"], patched["author"], patched["kind"]) == (
                        "Sample Café Guide, volume 1",
                        "Jane Doe",
                        "book",
                    )

                def test_should_serve_its_markdown_as_markdown(self, document_lifecycle: DocumentLifecycle) -> None:
                    assert document_lifecycle.markdown_type == "text/markdown; charset=utf-8"

                def test_should_open_its_markdown_with_its_fields(self, document_lifecycle: DocumentLifecycle) -> None:
                    assert document_lifecycle.markdown.startswith(
                        '---\ntitle: "Sample Café Guide, volume 1"\nauthor: "Jane Doe"\nkind: book\n'
                    )

                class TestWhenItIsDeleted:
                    def test_should_answer_no_content(self, document_lifecycle: DocumentLifecycle) -> None:
                        assert document_lifecycle.deletion_status == 204

                    def test_should_forget_it(self, document_lifecycle: DocumentLifecycle) -> None:
                        assert document_lifecycle.status_once_deleted == 404

                    def test_should_answer_not_found_when_deleted_again(
                        self, document_lifecycle: DocumentLifecycle
                    ) -> None:
                        assert document_lifecycle.second_deletion_status == 404

                    def test_should_remove_its_folder_from_the_library(
                        self, document_lifecycle: DocumentLifecycle
                    ) -> None:
                        assert document_lifecycle.is_folder_left is False

                    def test_should_move_its_folder_to_the_trash_under_its_slug(
                        self, document_lifecycle: DocumentLifecycle
                    ) -> None:
                        assert [name.startswith(f"{SLUG}-") for name in document_lifecycle.trashed_names] == [True]

                    def test_should_keep_its_markdown_in_the_trash(self, document_lifecycle: DocumentLifecycle) -> None:
                        assert ["document.md" in contents for contents in document_lifecycle.trashed_contents] == [True]

                    def test_should_move_nothing_more_to_the_trash_when_deleted_again(
                        self, document_lifecycle: DocumentLifecycle
                    ) -> None:
                        lifecycle = document_lifecycle
                        assert lifecycle.trashed_contents_after_second_deletion == lifecycle.trashed_contents

    class TestWhenItIsCreatedWithFieldsThatDoNotHoldUp:
        def test_should_refuse_it_as_invalid(self, invalid_document_requests: InvalidDocumentRequests) -> None:
            statuses = invalid_document_requests.creation_statuses
            accepted_creations = [name for name, status in statuses.items() if status != 422]
            assert len(statuses) == 6
            assert accepted_creations == []

    class TestWhenItsTitleIsPatchedEmpty:
        def test_should_refuse_it_as_invalid(self, invalid_document_requests: InvalidDocumentRequests) -> None:
            assert invalid_document_requests.empty_title_status == 422

    class TestWhenAnUnknownOneIsPatched:
        def test_should_answer_not_found(self, invalid_document_requests: InvalidDocumentRequests) -> None:
            assert invalid_document_requests.unknown_document_status == 404

    class TestWhenABookIsCreatedWithoutSayingWhetherToUnwarpIt:
        def test_should_unwarp_its_pages(self, new_documents: NewDocuments) -> None:
            assert new_documents.book["unwarp"] is True

    class TestWhenABookIsCreatedFlat:
        def test_should_not_unwarp_its_pages(self, new_documents: NewDocuments) -> None:
            assert new_documents.flat_book["unwarp"] is False

    class TestWhenAnotherKindOfDocumentIsCreatedWithoutSayingWhetherToUnwarpIt:
        def test_should_not_unwarp_its_pages(self, new_documents: NewDocuments) -> None:
            assert new_documents.letter["unwarp"] is False

    class TestWhenItsPagesAreSentToTheSandbox:
        @pytest.fixture(scope="class")
        @classmethod
        def sent_page(cls, tmp_path_factory: pytest.TempPathFactory) -> SentPage:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client, unwarp=True)
                upload(api.client, document_id, page_image(1))
                wait_until_processed(api.client, document_id)
                page_id = read_document(api.client, document_id)["pages"][0]["id"]
                return SentPage(page_id, api.fake_ocr.requests[-1]["params"])

        def test_should_ask_to_unwarp_them_and_to_find_their_orientation(self, sent_page: SentPage) -> None:
            assert (sent_page.params["unwarp"], sent_page.params["orientation"]) == ("1", "1")

        def test_should_name_each_request_after_its_page(self, sent_page: SentPage) -> None:
            assert sent_page.params["request_id"] == sent_page.page_id

    class TestWhenItIsExportedWithoutItsScans:
        def test_should_send_a_zip_archive(self, exported_document: ExportedDocument) -> None:
            assert exported_document.content_type == "application/zip"

        def test_should_name_the_archive_after_its_slug(self, exported_document: ExportedDocument) -> None:
            assert exported_document.content_disposition == f'attachment; filename="{SLUG}.zip"'

        def test_should_hold_its_markdown_its_metadata_and_the_markdown_illustration_and_ocr_result_of_each_page(
            self, exported_document: ExportedDocument
        ) -> None:
            key = exported_document.key
            assert exported_document.names == [
                f"{SLUG}/document.md",
                f"{SLUG}/document.json",
                f"{SLUG}/pages/{key}.md",
                f"{SLUG}/images/{key}_1.jpg",
                f"{SLUG}/ocr/{key}.json",
            ]

    class TestWhenItIsExportedWithItsScans:
        def test_should_send_a_sound_archive(self, exported_document: ExportedDocument) -> None:
            assert exported_document.first_bad_file is None

        def test_should_hold_the_scans_as_uploaded(self, exported_document: ExportedDocument) -> None:
            assert exported_document.exported_scan == page_image(9)

        def test_should_hold_its_markdown(self, exported_document: ExportedDocument) -> None:
            assert "# Sample Café Guide" in exported_document.exported_markdown


class TestTheDocumentsOfALibrary:
    class TestWhenTheyAreCreated:
        def test_should_give_each_a_slug_of_its_own_without_accents_or_ligatures(
            self, library_documents: LibraryDocuments
        ) -> None:
            assert library_documents.slugs == {
                library_documents.first_id: "letters",
                library_documents.second_id: "letters-2",
                library_documents.third_id: "complete-phoenix-resumes",
            }

        class TestWhenTheFirstOneIsChanged:
            def test_should_list_it_first(self, library_documents: LibraryDocuments) -> None:
                assert library_documents.listed_after_change[0] == library_documents.first_id


class TestABookScannedOutOfOrderAcrossSessions:
    class TestWhenItsPagesAreRead:
        @pytest.fixture(scope="class")
        @classmethod
        def book(cls, tmp_path_factory: pytest.TempPathFactory) -> BookScannedOutOfOrder:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client, "Sample Café Guide", author="Jane Doe", kind="book")
                late, early = new_id(), new_id()
                sessions = [(late, "21", (3, 4, 6)), (early, "20", (1, 2))]
                upload_statuses = [
                    upload(
                        client,
                        document_id,
                        page_image(number),
                        session_id=session,
                        seq=seq,
                        captured_at=f"2026-10-12T{hour}:00:0{seq}+02:00",
                    ).status_code
                    for session, hour, numbers in sessions
                    for seq, number in enumerate(numbers)
                ]
                document = wait_until_processed(client, document_id)
                folder = api.settings.library_dir / SLUG
                keys = [page["key"] for page in document["pages"]]
                return BookScannedOutOfOrder(
                    upload_statuses=upload_statuses,
                    document=document,
                    markdown=client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text,
                    markdown_file=(folder / "document.md").read_text(),
                    page_files={
                        key: PageFiles(
                            has_scan=(folder / "scans" / f"{key}.jpg").is_file(),
                            has_markdown=(folder / "pages" / f"{key}.md").is_file(),
                            has_illustration=(folder / "images" / f"{key}_1.jpg").is_file(),
                            ocr_key=json.loads((folder / "ocr" / f"{key}.json").read_text())["key"],
                        )
                        for key in keys
                    },
                    metadata=json.loads((folder / "document.json").read_text()),
                    index=(api.settings.library_dir / "INDEX.md").read_text(),
                    library=json.loads((api.settings.library_dir / "library.json").read_text()),
                    status=client.get("/api/status", headers=AUTH).json(),
                )

        def test_should_accept_every_scan(self, book: BookScannedOutOfOrder) -> None:
            assert book.upload_statuses == [201] * 5

        def test_should_read_every_page(self, book: BookScannedOutOfOrder) -> None:
            assert book.document["stats"] == {**NO_STATS, "pages": 5, "done": 5}

        def test_should_read_the_pages_in_the_order_of_their_numbers(self, book: BookScannedOutOfOrder) -> None:
            assert list_labels(book.document) == ["1", "2", "3", "4", "6"]

        def test_should_cover_its_pages_and_their_gap(self, book: BookScannedOutOfOrder) -> None:
            assert book.document["coverage"] == {
                "ranges": [[1, 4], [6, 6]],
                "label": "1–4, 6",
                "gaps": [[5, 5]],
                "min": 1,
                "max": 6,
                "unnumbered": 0,
            }

        def test_should_take_page_one_as_the_cover(self, book: BookScannedOutOfOrder) -> None:
            page_one = book.document["pages"][0]
            assert book.document["cover_thumb_url"] == f"/api/pages/{page_one['id']}/thumb"

        def test_should_key_page_one_by_the_time_of_its_capture(self, book: BookScannedOutOfOrder) -> None:
            assert book.document["pages"][0]["key"].startswith("20261012-200000_")

        def test_should_read_the_number_and_the_size_of_page_one(self, book: BookScannedOutOfOrder) -> None:
            page_one = book.document["pages"][0]
            assert (
                page_one["number_source"],
                page_one["detected_numbers"],
                page_one["width"],
                page_one["height"],
            ) == ("detected", ["1"], 1200, 1001)

        def test_should_record_the_engine_the_illustrations_and_the_text_of_the_ocr(
            self, book: BookScannedOutOfOrder
        ) -> None:
            ocr = book.document["pages"][0]["ocr"]
            assert (ocr["engine"], ocr["images"], ocr["chars"] > 100) == ("fakeocr", 1, True)

        def test_should_serve_the_markdown_of_its_file(self, book: BookScannedOutOfOrder) -> None:
            assert book.markdown == book.markdown_file

        def test_should_mark_each_page_and_the_missing_one_in_its_markdown(self, book: BookScannedOutOfOrder) -> None:
            markers = re.findall(r"<!-- (.*?) -->", book.markdown)
            assert [marker.split(" · ")[0] for marker in markers] == [
                "page 1",
                "page 2",
                "page 3",
                "page 4",
                "missing page: 5",
                "page 6",
            ]

        def test_should_name_the_ocr_engine_as_its_source(self, book: BookScannedOutOfOrder) -> None:
            assert 'source: "ScanMyLib — OCR FakeOCR"' in book.markdown

        def test_should_state_its_coverage_and_its_missing_pages(self, book: BookScannedOutOfOrder) -> None:
            assert 'coverage: "1–4, 6"\nmissing: "5"' in book.markdown

        def test_should_store_the_scan_of_each_page(self, book: BookScannedOutOfOrder) -> None:
            assert [files.has_scan for files in book.page_files.values()] == [True] * 5

        def test_should_store_the_markdown_of_each_page(self, book: BookScannedOutOfOrder) -> None:
            assert [files.has_markdown for files in book.page_files.values()] == [True] * 5

        def test_should_store_the_illustration_of_each_page(self, book: BookScannedOutOfOrder) -> None:
            assert [files.has_illustration for files in book.page_files.values()] == [True] * 5

        def test_should_store_the_ocr_result_of_each_page_under_its_key(self, book: BookScannedOutOfOrder) -> None:
            assert [files.ocr_key == key for key, files in book.page_files.items()] == [True] * 5

        def test_should_link_the_illustration_of_each_page_in_its_markdown(self, book: BookScannedOutOfOrder) -> None:
            assert [f"images/{key}_1.jpg" in book.markdown for key in book.page_files] == [True] * 5

        def test_should_list_the_labels_of_its_pages_in_its_metadata(self, book: BookScannedOutOfOrder) -> None:
            assert [page["label"] for page in book.metadata["pages"]] == ["1", "2", "3", "4", "6"]

        def test_should_state_its_coverage_in_its_metadata(self, book: BookScannedOutOfOrder) -> None:
            assert book.metadata["coverage"]["label"] == "1–4, 6"

        def test_should_list_it_in_the_index_of_the_library(self, book: BookScannedOutOfOrder) -> None:
            assert "| [Sample Café Guide](sample-cafe-guide/document.md) | Jane Doe | book | 5 | 1–4, 6 | 5 |" in (
                book.index
            )

        def test_should_count_its_scanned_pages_in_the_metadata_of_the_library(
            self, book: BookScannedOutOfOrder
        ) -> None:
            assert book.library["documents"][0]["pages_scanned"] == 5

        def test_should_report_a_queue_of_pages_all_read(self, book: BookScannedOutOfOrder) -> None:
            assert book.status["queue"] == {"queued": 0, "processing": 0, "error": 0, "done": 5}

        def test_should_report_the_engine_ready(self, book: BookScannedOutOfOrder) -> None:
            ocr = book.status["ocr"]
            assert (ocr["reachable"], ocr["state"], ocr["backend"]) == (True, "ready", "fake")

        def test_should_report_the_folder_of_the_library_on_the_host(self, book: BookScannedOutOfOrder) -> None:
            assert book.status["library_dir"] == "/home/user/Documents/ScanMyLib"


class TestAnUploadedPage:
    class TestWhenItCarriesItsCaptureMetadata:
        @pytest.fixture(scope="class")
        @classmethod
        def upload_with_metadata(cls, tmp_path_factory: pytest.TempPathFactory) -> UploadWithMetadata:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                page_id, session_id = new_id(), new_id()
                page = upload(
                    api.client,
                    document_id,
                    jpeg(1600, 1200, orientation=6),
                    page_id=page_id,
                    session_id=session_id,
                    seq=3,
                    captured_at="2026-10-12T20:15:30.250+02:00",
                    hint=12,
                ).json()
                return UploadWithMetadata(page_id, session_id, page)

        def test_should_key_it_by_the_time_of_its_capture_and_its_id(
            self, upload_with_metadata: UploadWithMetadata
        ) -> None:
            page_id = upload_with_metadata.page_id
            assert upload_with_metadata.page["key"] == f"20261012-201530_{page_id.replace('-', '')[:8]}"

        def test_should_keep_the_time_of_its_capture_to_the_second(
            self, upload_with_metadata: UploadWithMetadata
        ) -> None:
            assert upload_with_metadata.page["captured_at"] == "2026-10-12T20:15:30+02:00"

        def test_should_keep_its_session_its_sequence_number_and_its_page_number_hint(
            self, upload_with_metadata: UploadWithMetadata
        ) -> None:
            page = upload_with_metadata.page
            assert (page["session_id"], page["seq"], page["hint_number"]) == (upload_with_metadata.session_id, 3, 12)

        def test_should_turn_its_size_by_its_exif_orientation(self, upload_with_metadata: UploadWithMetadata) -> None:
            page = upload_with_metadata.page
            assert (page["width"], page["height"]) == (1200, 1600)

        def test_should_queue_it_for_the_ocr(self, upload_with_metadata: UploadWithMetadata) -> None:
            page = upload_with_metadata.page
            assert (page["status"], page["ocr"]) == ("queued", None)

    class TestWhenAFieldDoesNotHoldUp:
        @pytest.fixture(scope="class")
        @classmethod
        def statuses(cls, tmp_path_factory: pytest.TempPathFactory) -> dict[str, int]:
            fields = {
                "a-page-id-that-is-not-a-uuid": {"page_id": "nope"},
                "an-uppercase-page-id": {"page_id": "6F1C0000-0000-4000-8000-000000000001"},
                "a-session-id-that-is-not-a-uuid": {"session_id": "nope"},
                "a-sequence-number-in-words": {"seq": "two"},
                "a-negative-sequence-number": {"seq": "-1"},
                "a-capture-time-that-is-no-time": {"captured_at": "yesterday"},
                "a-capture-time-at-the-epoch": {"captured_at": "1970-01-01T00:00:00Z"},
                "a-page-number-hint-in-roman-numerals": {"page_number_hint": "xii"},
                "a-page-number-hint-of-zero": {"page_number_hint": "0"},
            }
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                return {
                    name: api.client.post(
                        f"/api/documents/{document_id}/pages",
                        headers=AUTH,
                        data={"page_id": new_id(), **field},
                        files={"file": ("p.jpg", page_image(1), "image/jpeg")},
                    ).status_code
                    for name, field in fields.items()
                }

        def test_should_refuse_the_upload_as_invalid(self, statuses: dict[str, int]) -> None:
            accepted_fields = [name for name, status in statuses.items() if status != 422]
            assert len(statuses) == 9
            assert accepted_fields == []

    class TestWhenItCannotBeTaken:
        @pytest.fixture(scope="class")
        @classmethod
        def refused_uploads(cls, tmp_path_factory: pytest.TempPathFactory) -> RefusedUploads:
            unsupported_image = io.BytesIO()
            Image.new("RGB", (10, 10)).save(unsupported_image, "GIF")
            oversized = io.BytesIO()
            Image.new("1", (11_000, 11_000)).save(oversized, "PNG")
            with running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client)
                pages_path = f"/api/documents/{document_id}/pages"
                return RefusedUploads(
                    unknown_document_status=upload(client, new_id(), page_image(1)).status_code,
                    missing_file_status=client.post(pages_path, headers=AUTH, data={"page_id": new_id()}).status_code,
                    missing_page_id_status=client.post(
                        pages_path, headers=AUTH, files={"file": ("p.jpg", page_image(1), "image/jpeg")}
                    ).status_code,
                    non_image_status=upload(client, document_id, b"%PDF-1.7 not an image").status_code,
                    unsupported_format_status=upload(client, document_id, unsupported_image.getvalue()).status_code,
                    oversized_status=upload(client, document_id, oversized.getvalue()).status_code,
                    corrupt_statuses={
                        name: upload(client, document_id, corrupt).status_code for name, corrupt in CORRUPT_PNGS.items()
                    },
                    page_count=read_document(client, document_id)["stats"]["pages"],
                )

        def test_should_answer_not_found_for_an_unknown_document(self, refused_uploads: RefusedUploads) -> None:
            assert refused_uploads.unknown_document_status == 404

        def test_should_refuse_an_upload_without_a_file_as_invalid(self, refused_uploads: RefusedUploads) -> None:
            assert refused_uploads.missing_file_status == 422

        def test_should_refuse_an_upload_without_a_page_id_as_invalid(self, refused_uploads: RefusedUploads) -> None:
            assert refused_uploads.missing_page_id_status == 422

        def test_should_refuse_a_file_that_is_not_an_image_as_unsupported(
            self, refused_uploads: RefusedUploads
        ) -> None:
            assert refused_uploads.non_image_status == 415

        def test_should_refuse_an_image_of_an_unsupported_format(self, refused_uploads: RefusedUploads) -> None:
            assert refused_uploads.unsupported_format_status == 415

        def test_should_refuse_an_image_of_too_many_pixels_as_too_large(self, refused_uploads: RefusedUploads) -> None:
            assert refused_uploads.oversized_status == 413

        def test_should_refuse_a_corrupt_image_for_good_and_not_as_a_server_error_the_phone_would_retry(
            self, refused_uploads: RefusedUploads
        ) -> None:
            statuses = refused_uploads.corrupt_statuses
            retriable_images = [name for name, status in statuses.items() if status != 415]
            assert len(statuses) == 3
            assert retriable_images == []

        def test_should_store_no_page(self, refused_uploads: RefusedUploads) -> None:
            assert refused_uploads.page_count == 0

    class TestWhenItIsACameraPhotoWithExtraPicturesOrBrokenExif:
        @pytest.fixture(scope="class")
        @classmethod
        def camera_photos(cls, tmp_path_factory: pytest.TempPathFactory) -> CameraPhotos:
            broken_exif = io.BytesIO()
            Image.new("RGB", (1200, 1043)).save(broken_exif, "JPEG", dpi=(72, 72), exif=BROKEN_EXIF)
            with running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client)
                multi_picture = upload(client, document_id, mpo(1200, 1042))
                broken_exif_status = upload(client, document_id, broken_exif.getvalue()).status_code
                document = wait_until_processed(client, document_id)
                multi_picture_scan = client.get(multi_picture.json()["image_url"], headers=AUTH)
                return CameraPhotos(
                    multi_picture_status=multi_picture.status_code,
                    broken_exif_status=broken_exif_status,
                    read_pages=[(page["status"], page["number"]) for page in document["pages"]],
                    multi_picture_scan_type=multi_picture_scan.headers["content-type"],
                )

        def test_should_accept_a_photo_with_extra_pictures(self, camera_photos: CameraPhotos) -> None:
            assert camera_photos.multi_picture_status == 201

        def test_should_accept_a_photo_with_broken_exif(self, camera_photos: CameraPhotos) -> None:
            assert camera_photos.broken_exif_status == 201

        def test_should_read_the_numbers_of_both(self, camera_photos: CameraPhotos) -> None:
            assert camera_photos.read_pages == [("done", 42), ("done", 43)]

        def test_should_serve_the_photo_with_extra_pictures_as_a_jpeg(self, camera_photos: CameraPhotos) -> None:
            assert camera_photos.multi_picture_scan_type == "image/jpeg"

    class TestWhenItsUploadIsRepeated:
        def test_should_create_it_once_and_answer_the_repeat_as_done_so_that_the_phone_may_retry(
            self, repeated_upload: RepeatedUpload
        ) -> None:
            assert (repeated_upload.first.status, repeated_upload.second.status) == (201, 200)

        def test_should_keep_its_key(self, repeated_upload: RepeatedUpload) -> None:
            assert repeated_upload.second.body["key"] == repeated_upload.first.body["key"]

        def test_should_read_it_once(self, repeated_upload: RepeatedUpload) -> None:
            assert repeated_upload.parse_request_count == 1

        def test_should_store_one_scan(self, repeated_upload: RepeatedUpload) -> None:
            assert repeated_upload.scan_count == 1

        def test_should_keep_the_first_image(self, repeated_upload: RepeatedUpload) -> None:
            assert repeated_upload.number == 7

        class TestWhenItsIdIsUploadedToAnotherDocument:
            def test_should_refuse_it_as_a_conflict(self, repeated_upload: RepeatedUpload) -> None:
                assert repeated_upload.other_document_status == 409

    class TestWhenItsIdIsUploadedToTwoDocumentsAtOnce:
        @pytest.fixture(scope="class")
        @classmethod
        def concurrent_uploads(cls, tmp_path_factory: pytest.TempPathFactory) -> ConcurrentUploads:
            second_answered = threading.Event()
            stored_slugs: list[str] = []
            store_scan = LibraryService._store_scan

            def slow_store_scan(
                self: LibraryService,
                slug: str,
                key: str,
                extension: str,
                scan: bytes,
                scan_page_id: str,
                thumbnail: bytes,
            ) -> None:
                stored_slugs.append(slug)
                if len(stored_slugs) == 1:  # keep the first upload between its checks and its insert
                    second_answered.wait(10)
                store_scan(self, slug, key, extension, scan, scan_page_id, thumbnail)

            with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                patch.setattr(LibraryService, "_store_scan", slow_store_scan)
                first, second = create_document(client, "Alpha"), create_document(client, "Beta")
                page_id = new_id()
                statuses: dict[str, int] = {}
                red_photo, blue_photo = jpeg(1200, 1001, color=(255, 0, 0)), jpeg(1200, 1002, color=(0, 0, 255))
                thread = threading.Thread(
                    target=lambda: statuses.update(first=upload(client, first, red_photo, page_id=page_id).status_code)
                )
                thread.start()
                wait_for(lambda: stored_slugs)
                statuses["second"] = upload(client, second, blue_photo, page_id=page_id).status_code
                second_answered.set()
                thread.join()
                page = client.get(f"/api/pages/{page_id}", headers=AUTH).json()
                thumbnail = Image.open(io.BytesIO(client.get(page["thumb_url"], headers=AUTH).content))
                return ConcurrentUploads(
                    statuses=dict(statuses),
                    stored_slugs=list(stored_slugs),
                    scan_folders=[path.parent.parent.name for path in api.settings.library_dir.glob("*/scans/*")],
                    owner_id=page["document_id"],
                    first_document_id=first,
                    thumbnail_pixel=cast(tuple[int, int, int], thumbnail.getpixel((5, 5))),
                )

        def test_should_accept_the_first_and_refuse_the_second_as_a_conflict(
            self, concurrent_uploads: ConcurrentUploads
        ) -> None:
            assert concurrent_uploads.statuses == {"first": 201, "second": 409}

        def test_should_store_nothing_for_the_refused_upload(self, concurrent_uploads: ConcurrentUploads) -> None:
            assert concurrent_uploads.stored_slugs == ["alpha"]

        def test_should_keep_the_scan_in_the_folder_of_the_first_document_only(
            self, concurrent_uploads: ConcurrentUploads
        ) -> None:
            assert concurrent_uploads.scan_folders == ["alpha"]

        def test_should_give_the_page_to_the_first_document(self, concurrent_uploads: ConcurrentUploads) -> None:
            assert concurrent_uploads.owner_id == concurrent_uploads.first_document_id

        def test_should_draw_the_thumbnail_from_the_photo_of_the_first_document(
            self, concurrent_uploads: ConcurrentUploads
        ) -> None:
            red, _, blue = concurrent_uploads.thumbnail_pixel
            assert (red > 200, blue < 50) == (True, True)


class TestAPage:
    class TestWhenItIsViewed:
        @pytest.fixture(scope="class")
        @classmethod
        def page_views(cls, tmp_path_factory: pytest.TempPathFactory) -> PageViews:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client)
                page = upload(client, document_id, page_image(42)).json()
                wait_until_processed(client, document_id)
                illustration = client.get(
                    f"/api/documents/{document_id}/files/images/{page['key']}_1.jpg", headers=AUTH
                )
                scan = client.get(page["image_url"], headers=AUTH)
                thumbnail = client.get(page["thumb_url"], headers=AUTH)
                return PageViews(
                    document_id=document_id,
                    page=page,
                    detail=client.get(f"/api/pages/{page['id']}", headers=AUTH).json(),
                    page_html=client.get(f"/api/pages/{page['id']}/html", headers=AUTH).json()["html"],
                    document_html=client.get(f"/api/documents/{document_id}/html", headers=AUTH).json()["html"],
                    illustration_status=illustration.status_code,
                    illustration_type=illustration.headers["content-type"],
                    scan_type=scan.headers["content-type"],
                    scan=scan.content,
                    thumbnail_cache_control=thumbnail.headers["cache-control"],
                    thumbnail_size=measure_image(thumbnail.content),
                )

        def test_should_point_its_markdown_to_its_illustration_in_the_library(self, page_views: PageViews) -> None:
            assert f'src="../images/{page_views.page["key"]}_1.jpg"' in page_views.detail["markdown"]

        def test_should_give_its_label_and_its_status(self, page_views: PageViews) -> None:
            assert (page_views.detail["page_label"], page_views.detail["status"]) == ("42", "done")

        def test_should_point_its_html_preview_to_the_illustration_the_api_serves(self, page_views: PageViews) -> None:
            illustration_url = f"/api/documents/{page_views.document_id}/files/images/{page_views.page['key']}_1.jpg"
            assert f'src="{illustration_url}"' in page_views.page_html

        def test_should_mark_the_page_in_the_html_preview_of_its_document(self, page_views: PageViews) -> None:
            assert '<p class="page-marker" data-label="42">Page 42</p>' in page_views.document_html

        def test_should_serve_its_illustration(self, page_views: PageViews) -> None:
            assert page_views.illustration_status == 200

        def test_should_serve_its_illustration_as_a_jpeg(self, page_views: PageViews) -> None:
            assert page_views.illustration_type == "image/jpeg"

        def test_should_serve_its_scan_as_a_jpeg(self, page_views: PageViews) -> None:
            assert page_views.scan_type == "image/jpeg"

        def test_should_serve_its_scan_as_uploaded(self, page_views: PageViews) -> None:
            assert page_views.scan == page_image(42)

        def test_should_have_its_thumbnail_checked_again_before_it_is_shown(self, page_views: PageViews) -> None:
            assert page_views.thumbnail_cache_control == "no-cache"

        def test_should_draw_its_thumbnail_480_pixels_on_its_longer_side(self, page_views: PageViews) -> None:
            assert max(page_views.thumbnail_size) == 480

    class TestWhenSeveralPreviewsOfItAreRequestedAtOnce:
        @pytest.fixture(scope="class")
        @classmethod
        def concurrent_previews(cls, tmp_path_factory: pytest.TempPathFactory) -> ConcurrentPreviews:
            counter_lock, active, peak = threading.Lock(), [0], [0]
            page_html = Publisher.page_html

            def slow_page_html(self: Publisher, document: DocumentRecord, page: PageRecord) -> str:
                with counter_lock:
                    active[0] += 1
                    peak[0] = max(peak[0], active[0])
                time.sleep(0.2)
                with counter_lock:
                    active[0] -= 1
                return page_html(self, document, page)

            with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client)
                page = upload(client, document_id, page_image(1)).json()
                wait_until_processed(client, document_id)
                patch.setattr(Publisher, "page_html", slow_page_html)
                statuses: list[int] = []
                requests = [
                    threading.Thread(
                        target=lambda: statuses.append(
                            client.get(f"/api/pages/{page['id']}/html", headers=AUTH).status_code
                        )
                    )
                    for _ in range(4)
                ]
                for thread in requests:
                    thread.start()
                for thread in requests:
                    thread.join()
                return ConcurrentPreviews(list(statuses), peak[0])

        def test_should_answer_each(self, concurrent_previews: ConcurrentPreviews) -> None:
            assert concurrent_previews.statuses == [200] * 4

        def test_should_render_them_one_at_a_time_so_that_a_hostile_page_never_takes_every_worker_thread(
            self, concurrent_previews: ConcurrentPreviews
        ) -> None:
            # Rendering is CPU-bound: parallel renders of a hostile page used to take every worker thread, stalling
            # uploads and thumbnails for minutes.
            assert concurrent_previews.peak_renders == 1

    class TestWhenItIsScannedSideways:
        def test_should_find_no_number(self, rotated_page: RotatedPage) -> None:
            assert rotated_page.number_before is None

        class TestWhenItIsRotatedByHand:
            def test_should_queue_it_again_with_its_rotation_and_its_turned_size(
                self, rotated_page: RotatedPage
            ) -> None:
                rotated = rotated_page.rotated
                assert (rotated["status"], rotated["rotation"], rotated["width"], rotated["height"]) == (
                    "queued",
                    90,
                    1500,
                    1204,
                )

            def test_should_read_its_number_once_turned(self, rotated_page: RotatedPage) -> None:
                assert (rotated_page.turned_page["status"], rotated_page.turned_page["number"]) == ("done", 204)

            def test_should_send_the_turned_image_to_the_sandbox(self, rotated_page: RotatedPage) -> None:
                assert (rotated_page.last_request["width"], rotated_page.last_request["height"]) == (1500, 1204)

            def test_should_ask_the_sandbox_not_to_turn_it_since_the_user_chose_its_orientation(
                self, rotated_page: RotatedPage
            ) -> None:
                assert rotated_page.last_request["params"]["orientation"] == "0"

            def test_should_turn_its_thumbnail(self, rotated_page: RotatedPage) -> None:
                assert rotated_page.thumbnail_size_after == rotated_page.thumbnail_size_before[::-1]

    class TestWhenItIsReprocessed:
        def test_should_queue_it_again(self, reprocessed_page: ReprocessedPage) -> None:
            reprocessing = reprocessed_page.reprocessing
            assert (reprocessing.status, reprocessing.body["status"]) == (202, "queued")

        def test_should_send_it_to_the_sandbox_again(self, reprocessed_page: ReprocessedPage) -> None:
            assert reprocessed_page.parse_request_count == 2

        def test_should_read_it_again(self, reprocessed_page: ReprocessedPage) -> None:
            assert reprocessed_page.status == "done"

        def test_should_keep_its_previous_result_in_the_trash(self, reprocessed_page: ReprocessedPage) -> None:
            assert [name.endswith(f"-ocr-{reprocessed_page.key}") for name in reprocessed_page.trashed_names] == [True]

    class TestWhenAnUnknownOneIsReprocessed:
        def test_should_answer_not_found(self, reprocessed_page: ReprocessedPage) -> None:
            assert reprocessed_page.unknown_page_status == 404

    class TestWhenItIsDeleted:
        def test_should_answer_no_content(self, deleted_page: DeletedPage) -> None:
            assert deleted_page.deletion_status == 204

        def test_should_forget_it(self, deleted_page: DeletedPage) -> None:
            assert deleted_page.status_once_deleted == 404

        def test_should_remove_its_scan_from_the_folder_of_its_document(self, deleted_page: DeletedPage) -> None:
            assert deleted_page.is_scan_left is False

        def test_should_move_its_files_to_the_trash(self, deleted_page: DeletedPage) -> None:
            assert deleted_page.trashed_contents == [["images", "ocr", "pages", "scans"]]

        def test_should_keep_the_other_page_in_its_document(self, deleted_page: DeletedPage) -> None:
            assert deleted_page.page_ids == [deleted_page.kept_id]

        def test_should_leave_it_out_of_the_markdown_of_its_document(self, deleted_page: DeletedPage) -> None:
            assert deleted_page.deleted_key not in deleted_page.markdown

        class TestWhenItIsDeletedAgain:
            def test_should_answer_not_found(self, deleted_page: DeletedPage) -> None:
                assert deleted_page.second_deletion_status == 404

            def test_should_move_nothing_more_to_the_trash(self, deleted_page: DeletedPage) -> None:
                assert deleted_page.trashed_contents_after_second_deletion == deleted_page.trashed_contents


class TestAPageWhoseOcrOutputIsHostile:
    class TestWhenItIsStoredAndPreviewed:
        @pytest.fixture(scope="class")
        @classmethod
        def hostile_page(cls, tmp_path_factory: pytest.TempPathFactory) -> HostilePage:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                api.fake_ocr.evil = True
                document_id = create_document(client)
                page = upload(client, document_id, page_image(4)).json()
                wait_until_processed(client, document_id)
                folder = api.settings.library_dir / SLUG
                document_markdown = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
                return HostilePage(
                    key=page["key"],
                    stored_markdown=(folder / "pages" / f"{page['key']}.md").read_text(),
                    illustrations=sorted(path.name for path in (folder / "images").iterdir()),
                    html=client.get(f"/api/pages/{page['id']}/html", headers=AUTH).json()["html"],
                    document_markdown=document_markdown,
                    # A plain CommonMark renderer: raw HTML on, front matter unknown.
                    rendered=MarkdownIt("commonmark").render(document_markdown),
                )

        def test_should_store_its_markdown_without_markup_that_runs_or_loads_anything(
            self, hostile_page: HostilePage
        ) -> None:
            forbidden = ["<script", "onerror", "onload", "<iframe", "<svg", "](javascript", "<!--"]
            assert {markup: markup in hostile_page.stored_markdown for markup in forbidden} == dict.fromkeys(
                forbidden, False
            )

        def test_should_store_its_own_illustration_only(self, hostile_page: HostilePage) -> None:
            assert hostile_page.illustrations == [f"{hostile_page.key}_1.jpg"]

        def test_should_preview_it_without_scripts_or_event_handlers(self, hostile_page: HostilePage) -> None:
            assert ("<script" in hostile_page.html, "onerror" in hostile_page.html) == (False, False)

        def test_should_preview_it_without_javascript_links_or_remote_images(self, hostile_page: HostilePage) -> None:
            assert ('href="javascript' in hostile_page.html, 'src="http' in hostile_page.html) == (False, False)

        def test_should_keep_no_comment_but_its_page_marker_in_the_markdown_of_its_document(
            self, hostile_page: HostilePage
        ) -> None:
            assert hostile_page.document_markdown.count("<!--") == 1

        def test_should_let_a_plain_markdown_renderer_load_its_own_illustration_and_no_other_markup(
            self, hostile_page: HostilePage
        ) -> None:
            assert re.findall(r"<(img|script|a)\b[^>]*>", hostile_page.rendered) == ["img"]

        def test_should_point_the_rendered_illustration_to_its_file(self, hostile_page: HostilePage) -> None:
            assert f'src="images/{hostile_page.key}_1.jpg"' in hostile_page.rendered


class TestTheFilesOfADocument:
    class TestWhenAPathLeadsOutOfThemOrToAFolder:
        @pytest.fixture(scope="class")
        @classmethod
        def confined_files(cls, tmp_path_factory: pytest.TempPathFactory) -> dict[str, ConfinedFile]:
            paths = {
                "a-path-up-to-the-root": "../../../../etc/passwd",
                "an-encoded-path-up-to-the-root": "..%2f..%2f..%2fetc%2fpasswd",
                "an-encoded-path-up-to-the-state": "%2e%2e/%2e%2e/state/token",
                "a-path-out-of-the-pages": f"pages/../../{SLUG}/document.md",
                "an-absolute-path": "/etc/passwd",
                "the-scans-folder": "scans",
                "the-trash": ".trash",
                "a-file-of-no-known-kind": "pages/x.txt",
            }
            with running_api(tmp_path_factory.mktemp("api")) as api:
                document_id = create_document(api.client)
                (api.settings.library_dir / "secret.md").write_text("secret")
                responses = {
                    name: api.client.get(f"/api/documents/{document_id}/files/{path}", headers=AUTH)
                    for name, path in paths.items()
                }
                return {
                    name: ConfinedFile(response.status_code, b"secret" in response.content)
                    for name, response in responses.items()
                }

        def test_should_answer_not_found(self, confined_files: dict[str, ConfinedFile]) -> None:
            found_paths = [name for name, confined_file in confined_files.items() if confined_file.status != 404]
            assert len(confined_files) == 8
            assert found_paths == []

        def test_should_serve_nothing_of_the_library_outside_them(
            self, confined_files: dict[str, ConfinedFile]
        ) -> None:
            leaking_paths = [name for name, confined_file in confined_files.items() if confined_file.is_secret_served]
            assert len(confined_files) == 8
            assert leaking_paths == []

    class TestWhenTheyAreRead:
        @pytest.fixture(scope="class")
        @classmethod
        def served_files(cls, tmp_path_factory: pytest.TempPathFactory) -> dict[str, ServedFile]:
            with running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client)
                key = upload(client, document_id, page_image(5)).json()["key"]
                wait_until_processed(client, document_id)
                files_path = f"/api/documents/{document_id}/files"
                wait_for(lambda: client.get(f"{files_path}/document.json", headers=AUTH).status_code == 200)
                paths = {
                    "the-markdown-of-the-document": "document.md",
                    "the-metadata-of-the-document": "document.json",
                    "the-markdown-of-a-page": f"pages/{key}.md",
                    "the-ocr-result-of-a-page": f"ocr/{key}.json",
                    "the-scan-of-a-page": f"scans/{key}.jpg",
                }
                responses = {name: client.get(f"{files_path}/{path}", headers=AUTH) for name, path in paths.items()}
                return {
                    name: ServedFile(response.status_code, response.headers["content-type"])
                    for name, response in responses.items()
                }

        def test_should_serve_each(self, served_files: dict[str, ServedFile]) -> None:
            unserved_files = [name for name, served_file in served_files.items() if served_file.status != 200]
            assert len(served_files) == 5
            assert unserved_files == []

        def test_should_serve_each_with_its_type(self, served_files: dict[str, ServedFile]) -> None:
            content_types = {
                "the-markdown-of-the-document": "text/markdown; charset=utf-8",
                "the-metadata-of-the-document": "application/json",
                "the-markdown-of-a-page": "text/markdown; charset=utf-8",
                "the-ocr-result-of-a-page": "application/json",
                "the-scan-of-a-page": "image/jpeg",
            }
            mistyped_files = [
                name for name, served_file in served_files.items() if served_file.content_type != content_types[name]
            ]
            assert len(served_files) == 5
            assert mistyped_files == []

    class TestWhenTheirRewriteAfterADeletionFails:
        @pytest.fixture(scope="class")
        @classmethod
        def rewrite(cls, tmp_path_factory: pytest.TempPathFactory) -> RewriteAfterAFailure:
            write_document = LibraryFiles.write_document
            failures: list[str] = []

            def full_disk_once(self: LibraryFiles, slug: str, markdown: str, metadata: Mapping[str, object]) -> None:
                if not failures:
                    failures.append("ENOSPC")
                    raise OSError(errno.ENOSPC, "No space left on device")
                write_document(self, slug, markdown, metadata)

            with pytest.MonkeyPatch.context() as patch, running_api(tmp_path_factory.mktemp("api")) as api:
                client = api.client
                document_id = create_document(client)
                kept = upload(client, document_id, page_image(1)).json()
                deleted = upload(client, document_id, page_image(2)).json()
                wait_until_processed(client, document_id)
                markdown_file = api.settings.library_dir / SLUG / "document.md"
                wait_for(lambda: markdown_file.is_file() and deleted["key"] in markdown_file.read_text())
                patch.setattr(LibraryFiles, "write_document", full_disk_once)
                deletion_status = client.delete(f"/api/pages/{deleted['id']}", headers=AUTH).status_code
                wait_for(lambda: failures)
                return RewriteAfterAFailure(
                    kept_key=kept["key"],
                    deleted_key=deleted["key"],
                    deletion_status=deletion_status,
                    markdown=read_until(markdown_file.read_text, lambda markdown: deleted["key"] not in markdown),
                )

        def test_should_answer_the_deletion_with_no_content(self, rewrite: RewriteAfterAFailure) -> None:
            assert rewrite.deletion_status == 204

        def test_should_rewrite_them_later_without_any_further_change_to_the_document(
            self, rewrite: RewriteAfterAFailure
        ) -> None:
            assert rewrite.deleted_key not in rewrite.markdown

        def test_should_keep_the_other_page_in_them(self, rewrite: RewriteAfterAFailure) -> None:
            assert rewrite.kept_key in rewrite.markdown


class TestADocumentWithAMissingNumberAndAPageScannedTwice:
    class TestWhenItsPagesAreRead:
        def test_should_infer_the_missing_number_from_the_numbers_around_it(
            self, corrected_document: CorrectedDocument
        ) -> None:
            pages_by_id = {page["id"]: page for page in corrected_document.document_once_read["pages"]}
            unnumbered = pages_by_id[corrected_document.pages[1]["id"]]
            assert (unnumbered["number"], unnumbered["number_source"]) == (11, "inferred")

        def test_should_make_the_earlier_scan_a_duplicate_of_the_later_one_since_the_latest_capture_wins(
            self, corrected_document: CorrectedDocument
        ) -> None:
            pages_by_id = {page["id"]: page for page in corrected_document.document_once_read["pages"]}
            earlier_scan = pages_by_id[corrected_document.pages[2]["id"]]
            assert earlier_scan["duplicate_of"] == corrected_document.pages[3]["id"]

        def test_should_count_one_duplicate(self, corrected_document: CorrectedDocument) -> None:
            assert corrected_document.document_once_read["stats"]["duplicates"] == 1

        def test_should_list_the_duplicate_last(self, corrected_document: CorrectedDocument) -> None:
            assert corrected_document.document_once_read["pages"][-1]["id"] == corrected_document.pages[2]["id"]

        class TestWhenTheDuplicateIsNumberedByHand:
            def test_should_take_the_typed_number_and_be_a_duplicate_no_more(
                self, corrected_document: CorrectedDocument
            ) -> None:
                page = corrected_document.numbered_by_hand
                assert (page["number"], page["number_source"], page["duplicate_of"]) == (13, "manual", None)

            def test_should_label_the_pages_in_order(self, corrected_document: CorrectedDocument) -> None:
                assert corrected_document.labels_numbered_by_hand == ["10", "11", "12", "13"]

            class TestWhenItsTypedNumberIsCleared:
                def test_should_make_it_a_duplicate_again(self, corrected_document: CorrectedDocument) -> None:
                    page = corrected_document.cleared
                    assert (page["manual_number"], page["duplicate_of"]) == (None, corrected_document.pages[3]["id"])

                class TestWhenAnotherPageIsExcluded:
                    def test_should_answer_ok(self, corrected_document: CorrectedDocument) -> None:
                        assert corrected_document.exclusion.status == 200

                    def test_should_take_it_out_of_the_document(self, corrected_document: CorrectedDocument) -> None:
                        page = corrected_document.exclusion.body
                        assert (page["excluded"], page["in_document"]) == (True, False)

                    def test_should_leave_it_out_of_the_markdown(self, corrected_document: CorrectedDocument) -> None:
                        assert corrected_document.pages[0]["key"] not in corrected_document.markdown_after_exclusion

    class TestWhenAPageIsPatchedWithFieldsThatDoNotHoldUp:
        def test_should_refuse_a_rotation_by_other_than_quarter_turns(
            self, corrected_document: CorrectedDocument
        ) -> None:
            assert corrected_document.rotation_by_45_degrees_status == 422

        def test_should_refuse_a_page_number_of_zero(self, corrected_document: CorrectedDocument) -> None:
            assert corrected_document.page_number_zero_status == 422

    class TestWhenAnUnknownPageIsPatched:
        def test_should_answer_not_found(self, corrected_document: CorrectedDocument) -> None:
            assert corrected_document.unknown_page_status == 404
