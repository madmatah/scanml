"""End-to-end API flows: the real app, the OCR loop and the fake sandbox on a Unix socket."""

from __future__ import annotations

import errno
import io
import json
import re
import threading
import time
import zipfile

import pytest
from markdown_it import MarkdownIt
from PIL import Image
from support import (
    AUTH,
    BROKEN_EXIF,
    CORRUPT_PNGS,
    create_document,
    jpeg,
    mpo,
    new_id,
    page_image,
    upload,
    wait_for,
    wait_until_processed,
)

from scanmylib.library import LibraryService
from scanmylib.publisher import Publisher
from scanmylib.storage import LibraryFiles


def get_document(client, document_id: str) -> dict:
    response = client.get(f"/api/documents/{document_id}", headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def page_labels(document: dict) -> list:
    return [page["page_label"] for page in document["pages"] if page["in_document"]]


# -- documents --------------------------------------------------------------------------


def test_document_lifecycle(client, library_dir):
    document_id = new_id()
    created = client.put(f"/api/documents/{document_id}", json={"title": "  Sample Café\tGuide  "}, headers=AUTH)
    assert created.status_code == 201
    document = created.json()
    assert document["title"] == "Sample Café Guide"
    assert document["slug"] == "sample-cafe-guide"
    assert (document["author"], document["kind"], document["notes"], document["unwarp"]) == ("", "document", "", False)
    assert document["stats"] == {
        "pages": 0,
        "done": 0,
        "queued": 0,
        "processing": 0,
        "error": 0,
        "excluded": 0,
        "duplicates": 0,
    }
    assert document["coverage"]["label"] == "" and document["cover_thumb_url"] is None
    assert document["folder"] == "/home/user/Documents/ScanMyLib/sample-cafe-guide"
    assert (library_dir / "sample-cafe-guide").is_dir()

    updated = client.put(
        f"/api/documents/{document_id}",
        json={
            "title": "Sample Café Guide, volume 1",
            "author": "J. Doe",
            "kind": "book",
            "notes": "a\r\nb",
            "unwarp": True,
        },
        headers=AUTH,
    )
    assert updated.status_code == 200
    assert updated.json()["slug"] == "sample-cafe-guide"  # never changes
    assert updated.json()["notes"] == "a\nb"
    patched = client.patch(f"/api/documents/{document_id}", json={"author": "Jane Doe"}, headers=AUTH).json()
    assert (patched["title"], patched["author"], patched["kind"]) == ("Sample Café Guide, volume 1", "Jane Doe", "book")

    markdown = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH)
    assert markdown.headers["content-type"] == "text/markdown; charset=utf-8"
    assert markdown.text.startswith('---\ntitle: "Sample Café Guide, volume 1"\nauthor: "Jane Doe"\nkind: book\n')

    assert client.delete(f"/api/documents/{document_id}", headers=AUTH).status_code == 204
    assert client.get(f"/api/documents/{document_id}", headers=AUTH).status_code == 404
    assert client.delete(f"/api/documents/{document_id}", headers=AUTH).status_code == 404
    assert not (library_dir / "sample-cafe-guide").exists()
    [trashed] = (library_dir / ".trash").iterdir()
    assert trashed.name.startswith("sample-cafe-guide-")
    assert (trashed / "document.md").is_file()


def test_new_books_default_to_unwarping(client):
    book = client.put(f"/api/documents/{new_id()}", json={"title": "Book", "kind": "book"}, headers=AUTH).json()
    assert book["unwarp"] is True
    flat = client.put(
        f"/api/documents/{new_id()}", json={"title": "Flat book", "kind": "book", "unwarp": False}, headers=AUTH
    ).json()
    assert flat["unwarp"] is False
    letter = client.put(f"/api/documents/{new_id()}", json={"title": "Letter", "kind": "document"}, headers=AUTH).json()
    assert letter["unwarp"] is False


def test_document_validation(client):
    assert client.put("/api/documents/not-a-uuid", json={"title": "x"}, headers=AUTH).status_code == 422
    assert client.put(f"/api/documents/{new_id().upper()}", json={"title": "x"}, headers=AUTH).status_code == 422
    assert client.put(f"/api/documents/{new_id()}", json={"author": "no title"}, headers=AUTH).status_code == 422
    assert client.put(f"/api/documents/{new_id()}", json={"title": "   "}, headers=AUTH).status_code == 422
    assert (
        client.put(f"/api/documents/{new_id()}", json={"title": "x", "kind": "magazine"}, headers=AUTH).status_code
        == 422
    )
    assert client.put(f"/api/documents/{new_id()}", json={"title": "x" * 301}, headers=AUTH).status_code == 422
    assert client.patch(f"/api/documents/{new_id()}", json={"title": "x"}, headers=AUTH).status_code == 404
    document_id = create_document(client)
    assert client.patch(f"/api/documents/{document_id}", json={"title": ""}, headers=AUTH).status_code == 422


def test_slugs_are_unique_and_documents_sorted_by_activity(client):
    first = create_document(client, "Letters")
    second = create_document(client, "Letters")
    third = create_document(client, "Complete Phœnix Résumés")
    slugs = {d["id"]: d["slug"] for d in client.get("/api/documents", headers=AUTH).json()["documents"]}
    assert slugs == {first: "letters", second: "letters-2", third: "complete-phoenix-resumes"}
    client.patch(f"/api/documents/{first}", json={"notes": "résumé"}, headers=AUTH)
    listed = [d["id"] for d in client.get("/api/documents", headers=AUTH).json()["documents"]]
    assert listed[0] == first


# -- scanning ---------------------------------------------------------------------------


def test_out_of_order_scanning_across_sessions(client, fake_ocr, library_dir):
    document_id = create_document(client, "Sample Café Guide", author="Jane Doe", kind="book")
    late, early = new_id(), new_id()
    # Session "late" (captured later, uploaded first): pages 3, 4 and 6.
    for seq, number in enumerate((3, 4, 6)):
        response = upload(
            client,
            document_id,
            page_image(number),
            session_id=late,
            seq=seq,
            captured_at=f"2026-10-12T21:00:0{seq}+02:00",
        )
        assert response.status_code == 201, response.text
    # Session "early": pages 1 and 2.
    for seq, number in enumerate((1, 2)):
        upload(
            client,
            document_id,
            page_image(number),
            session_id=early,
            seq=seq,
            captured_at=f"2026-10-12T20:00:0{seq}+02:00",
        )

    document = wait_until_processed(client, document_id)
    assert document["stats"] == {
        "pages": 5,
        "done": 5,
        "queued": 0,
        "processing": 0,
        "error": 0,
        "excluded": 0,
        "duplicates": 0,
    }
    assert page_labels(document) == ["1", "2", "3", "4", "6"]
    assert document["coverage"] == {
        "ranges": [[1, 4], [6, 6]],
        "label": "1–4, 6",
        "gaps": [[5, 5]],
        "min": 1,
        "max": 6,
        "unnumbered": 0,
    }
    first = document["pages"][0]
    assert document["cover_thumb_url"] == f"/api/pages/{first['id']}/thumb"
    assert first["key"].startswith("20261012-200000_")
    assert (first["number_source"], first["detected_numbers"], first["width"], first["height"]) == (
        "detected",
        ["1"],
        1200,
        1001,
    )
    assert first["ocr"]["engine"] == "fakeocr" and first["ocr"]["images"] == 1 and first["ocr"]["chars"] > 100

    folder = library_dir / "sample-cafe-guide"
    markdown = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
    assert markdown == (folder / "document.md").read_text()
    markers = re.findall(r"<!-- (.*?) -->", markdown)
    assert [m.split(" · ")[0] for m in markers] == ["page 1", "page 2", "page 3", "page 4", "missing page: 5", "page 6"]
    assert 'source: "ScanMyLib — OCR FakeOCR"' in markdown
    assert 'coverage: "1–4, 6"\nmissing: "5"' in markdown
    for page in document["pages"]:
        key = page["key"]
        assert (folder / "scans" / f"{key}.jpg").is_file()
        assert (folder / "pages" / f"{key}.md").is_file()
        assert (folder / "images" / f"{key}_1.jpg").is_file()
        assert json.loads((folder / "ocr" / f"{key}.json").read_text())["key"] == key
        assert f"images/{key}_1.jpg" in markdown

    metadata = json.loads((folder / "document.json").read_text())
    assert [p["label"] for p in metadata["pages"]] == ["1", "2", "3", "4", "6"]
    assert metadata["coverage"]["label"] == "1–4, 6"
    index = (library_dir / "INDEX.md").read_text()
    assert "| [Sample Café Guide](sample-cafe-guide/document.md) | Jane Doe | book | 5 | 1–4, 6 | 5 |" in index
    library = json.loads((library_dir / "library.json").read_text())
    assert library["documents"][0]["pages_scanned"] == 5

    status = client.get("/api/status", headers=AUTH).json()
    assert status["queue"] == {"queued": 0, "processing": 0, "error": 0, "done": 5}
    assert status["ocr"]["reachable"] and status["ocr"]["state"] == "ready" and status["ocr"]["backend"] == "fake"
    assert status["library_dir"] == "/home/user/Documents/ScanMyLib"


def test_page_views(client):
    document_id = create_document(client)
    page = upload(client, document_id, page_image(42)).json()
    wait_until_processed(client, document_id)

    detail = client.get(f"/api/pages/{page['id']}", headers=AUTH).json()
    assert f'src="../images/{page["key"]}_1.jpg"' in detail["markdown"]
    assert detail["page_label"] == "42" and detail["status"] == "done"

    html = client.get(f"/api/pages/{page['id']}/html", headers=AUTH).json()["html"]
    assert f'src="/api/documents/{document_id}/files/images/{page["key"]}_1.jpg"' in html
    whole = client.get(f"/api/documents/{document_id}/html", headers=AUTH).json()["html"]
    assert '<p class="page-marker" data-label="42">Page 42</p>' in whole

    image = client.get(f"/api/documents/{document_id}/files/images/{page['key']}_1.jpg", headers=AUTH)
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    original = client.get(page["image_url"], headers=AUTH)
    assert original.headers["content-type"] == "image/jpeg" and original.content == page_image(42)
    thumb = client.get(page["thumb_url"], headers=AUTH)
    assert thumb.headers["cache-control"] == "no-cache"
    assert max(Image.open(io.BytesIO(thumb.content)).size) == 480


def test_upload_is_idempotent(client, fake_ocr, library_dir):
    document_id = create_document(client)
    page_id = new_id()
    first = upload(client, document_id, page_image(7), page_id=page_id)
    second = upload(client, document_id, page_image(8), page_id=page_id)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["key"] == first.json()["key"]
    wait_until_processed(client, document_id)
    assert len(fake_ocr.requests) == 1
    assert len(list((library_dir / "sample-cafe-guide" / "scans").iterdir())) == 1
    assert get_document(client, document_id)["pages"][0]["number"] == 7

    other = create_document(client, "Other")
    assert upload(client, other, page_image(7), page_id=page_id).status_code == 409


def test_same_page_id_uploaded_to_two_documents_at_once(client, library_dir, monkeypatch):
    first, second = create_document(client, "Alpha"), create_document(client, "Beta")
    page_id = new_id()
    second_answered = threading.Event()
    stored: list[tuple] = []
    store_scan = LibraryService._store_scan

    def slow_store_scan(self, *args):
        stored.append(args)
        if len(stored) == 1:  # keep the first upload between its checks and its insert
            second_answered.wait(10)
        store_scan(self, *args)

    monkeypatch.setattr(LibraryService, "_store_scan", slow_store_scan)
    statuses = {}
    thread = threading.Thread(
        target=lambda: statuses.update(
            first=upload(client, first, jpeg(1200, 1001, color=(255, 0, 0)), page_id=page_id).status_code
        )
    )
    thread.start()
    wait_for(lambda: stored)
    statuses["second"] = upload(client, second, jpeg(1200, 1002, color=(0, 0, 255)), page_id=page_id).status_code
    second_answered.set()
    thread.join()

    assert statuses == {"first": 201, "second": 409}
    assert len(stored) == 1  # nothing written for the refused upload
    assert [p.parent.parent.name for p in library_dir.glob("*/scans/*")] == ["alpha"]
    page = client.get(f"/api/pages/{page_id}", headers=AUTH).json()
    assert page["document_id"] == first
    red, _, blue = Image.open(io.BytesIO(client.get(page["thumb_url"], headers=AUTH).content)).getpixel((5, 5))
    assert red > 200 and blue < 50  # the thumbnail is the first document's photo


def test_upload_metadata(client):
    document_id = create_document(client)
    page_id, session_id = new_id(), new_id()
    page = upload(
        client,
        document_id,
        jpeg(1600, 1200, orientation=6),
        page_id=page_id,
        session_id=session_id,
        seq=3,
        captured_at="2026-10-12T20:15:30.250+02:00",
        hint=12,
    ).json()
    assert page["key"] == f"20261012-201530_{page_id.replace('-', '')[:8]}"
    assert page["captured_at"] == "2026-10-12T20:15:30+02:00"
    assert (page["session_id"], page["seq"], page["hint_number"]) == (session_id, 3, 12)
    assert (page["width"], page["height"]) == (1200, 1600)  # EXIF orientation applied
    assert page["status"] == "queued" and page["ocr"] is None


@pytest.mark.parametrize(
    ("fields", "status"),
    [
        ({"page_id": "nope"}, 422),
        ({"page_id": "6F1C0000-0000-4000-8000-000000000001"}, 422),
        ({"session_id": "nope"}, 422),
        ({"seq": "two"}, 422),
        ({"seq": "-1"}, 422),
        ({"captured_at": "yesterday"}, 422),
        ({"captured_at": "1970-01-01T00:00:00Z"}, 422),
        ({"page_number_hint": "xii"}, 422),
        ({"page_number_hint": "0"}, 422),
    ],
)
def test_upload_field_validation(client, fields, status):
    document_id = create_document(client)
    data = {"page_id": new_id(), **fields}
    response = client.post(
        f"/api/documents/{document_id}/pages",
        headers=AUTH,
        data=data,
        files={"file": ("p.jpg", page_image(1), "image/jpeg")},
    )
    assert response.status_code == status, response.text


def test_upload_rejections(client):
    document_id = create_document(client)
    assert upload(client, new_id(), page_image(1)).status_code == 404
    missing_file = client.post(f"/api/documents/{document_id}/pages", headers=AUTH, data={"page_id": new_id()})
    assert missing_file.status_code == 422
    assert (
        client.post(
            f"/api/documents/{document_id}/pages", headers=AUTH, files={"file": ("p.jpg", page_image(1), "image/jpeg")}
        ).status_code
        == 422
    )
    assert upload(client, document_id, b"%PDF-1.7 not an image").status_code == 415
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    assert upload(client, document_id, gif.getvalue()).status_code == 415
    huge = io.BytesIO()
    Image.new("1", (11_000, 11_000)).save(huge, "PNG")
    assert upload(client, document_id, huge.getvalue()).status_code == 413
    for corrupt in CORRUPT_PNGS.values():  # refused for good (415), not a server error the phone would retry
        assert upload(client, document_id, corrupt).status_code == 415
    assert get_document(client, document_id)["stats"]["pages"] == 0


def test_camera_photos_with_extra_pictures_or_broken_exif_are_accepted(client):
    document_id = create_document(client)
    multi_picture = upload(client, document_id, mpo(1200, 1042))
    assert multi_picture.status_code == 201, multi_picture.text
    broken_exif = io.BytesIO()
    Image.new("RGB", (1200, 1043)).save(broken_exif, "JPEG", dpi=(72, 72), exif=BROKEN_EXIF)
    assert upload(client, document_id, broken_exif.getvalue()).status_code == 201
    document = wait_until_processed(client, document_id)
    assert [(p["status"], p["number"]) for p in document["pages"]] == [("done", 42), ("done", 43)]
    original = client.get(multi_picture.json()["image_url"], headers=AUTH)
    assert original.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize(
    "path",
    [
        "../../../../etc/passwd",
        "..%2f..%2f..%2fetc%2fpasswd",
        "%2e%2e/%2e%2e/state/token",
        "pages/../../sample-cafe-guide/document.md",
        "/etc/passwd",
        "scans",
        ".trash",
        "pages/x.txt",
    ],
)
def test_file_access_is_confined_to_the_document_folder(client, library_dir, path):
    document_id = create_document(client)
    (library_dir / "secret.md").write_text("secret")
    response = client.get(f"/api/documents/{document_id}/files/{path}", headers=AUTH)
    assert response.status_code == 404
    assert b"secret" not in response.content


def test_previews_are_rendered_one_at_a_time(client, monkeypatch):
    # Rendering is CPU-bound: parallel renders of a hostile page used to take
    # every worker thread, stalling uploads and thumbnails for minutes.
    document_id = create_document(client)
    page = upload(client, document_id, page_image(1)).json()
    wait_until_processed(client, document_id)
    counter_lock, active, peak = threading.Lock(), [0], [0]
    page_html = Publisher.page_html

    def slow_page_html(self, *args):
        with counter_lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.2)
        with counter_lock:
            active[0] -= 1
        return page_html(self, *args)

    monkeypatch.setattr(Publisher, "page_html", slow_page_html)
    statuses = []
    requests = [
        threading.Thread(
            target=lambda: statuses.append(client.get(f"/api/pages/{page['id']}/html", headers=AUTH).status_code)
        )
        for _ in range(4)
    ]
    for thread in requests:
        thread.start()
    for thread in requests:
        thread.join()
    assert statuses == [200] * 4
    assert peak[0] == 1


def test_document_files_are_served_with_their_type(client):
    document_id = create_document(client)
    page = upload(client, document_id, page_image(5)).json()
    wait_until_processed(client, document_id)
    expected = {
        "document.md": "text/markdown; charset=utf-8",
        "document.json": "application/json",
        f"pages/{page['key']}.md": "text/markdown; charset=utf-8",
        f"ocr/{page['key']}.json": "application/json",
        f"scans/{page['key']}.jpg": "image/jpeg",
    }
    wait_for(lambda: client.get(f"/api/documents/{document_id}/files/document.json", headers=AUTH).status_code == 200)
    for path, content_type in expected.items():
        response = client.get(f"/api/documents/{document_id}/files/{path}", headers=AUTH)
        assert response.status_code == 200, path
        assert response.headers["content-type"] == content_type


# -- corrections --------------------------------------------------------------------------


def test_manual_numbers_exclusion_and_duplicates(client):
    document_id = create_document(client)
    session = new_id()
    pages = [
        upload(
            client,
            document_id,
            page_image(number, variant),
            session_id=session,
            seq=seq,
            captured_at=f"2026-10-12T20:00:0{seq}+02:00",
        ).json()
        for seq, (number, variant) in enumerate([(10, 0), (0, 4), (12, 0), (12, 0)])
    ]
    document = wait_until_processed(client, document_id)
    by_id = {p["id"]: p for p in document["pages"]}
    inferred = by_id[pages[1]["id"]]
    assert (inferred["number"], inferred["number_source"]) == (11, "inferred")
    assert by_id[pages[2]["id"]]["duplicate_of"] == pages[3]["id"]  # latest capture wins
    assert document["stats"]["duplicates"] == 1
    assert [p["id"] for p in document["pages"]][-1] == pages[2]["id"]  # duplicates listed last

    corrected = client.patch(f"/api/pages/{pages[2]['id']}", json={"manual_number": 13}, headers=AUTH).json()
    assert (corrected["number"], corrected["number_source"], corrected["duplicate_of"]) == (13, "manual", None)
    assert page_labels(get_document(client, document_id)) == ["10", "11", "12", "13"]

    cleared = client.patch(f"/api/pages/{pages[2]['id']}", json={"manual_number": None}, headers=AUTH).json()
    assert cleared["manual_number"] is None and cleared["duplicate_of"] == pages[3]["id"]

    excluded = client.patch(f"/api/pages/{pages[0]['id']}", json={"excluded": True}, headers=AUTH).json()
    assert excluded["excluded"] and not excluded["in_document"]
    markdown = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
    assert pages[0]["key"] not in markdown

    assert client.patch(f"/api/pages/{pages[0]['id']}", json={"rotation": 45}, headers=AUTH).status_code == 422
    assert client.patch(f"/api/pages/{pages[0]['id']}", json={"manual_number": 0}, headers=AUTH).status_code == 422
    assert client.patch(f"/api/pages/{new_id()}", json={"excluded": True}, headers=AUTH).status_code == 404


def test_rotation_requeues_with_the_rotated_image(client, fake_ocr):
    document_id = create_document(client)
    # 1204×1500: the fake engine finds no number (variant 4); rotated: 1500×1204, page 204.
    page = upload(client, document_id, jpeg(1204, 1500)).json()
    wait_until_processed(client, document_id)
    assert client.get(f"/api/pages/{page['id']}", headers=AUTH).json()["number"] is None
    thumb_before = Image.open(io.BytesIO(client.get(page["thumb_url"], headers=AUTH).content)).size

    rotated = client.patch(f"/api/pages/{page['id']}", json={"rotation": 90}, headers=AUTH).json()
    assert (rotated["status"], rotated["rotation"], rotated["width"], rotated["height"]) == ("queued", 90, 1500, 1204)
    wait_until_processed(client, document_id)
    after = client.get(f"/api/pages/{page['id']}", headers=AUTH).json()
    assert (after["status"], after["number"]) == ("done", 204)
    assert fake_ocr.requests[-1]["width"] == 1500 and fake_ocr.requests[-1]["height"] == 1204
    assert fake_ocr.requests[-1]["params"]["orientation"] == "0"  # the user chose the orientation
    thumb_after = Image.open(io.BytesIO(client.get(page["thumb_url"], headers=AUTH).content)).size
    assert thumb_after == thumb_before[::-1]


def test_reprocess_keeps_the_previous_result_in_the_trash(client, fake_ocr, library_dir):
    document_id = create_document(client)
    page = upload(client, document_id, page_image(3)).json()
    wait_until_processed(client, document_id)
    response = client.post(f"/api/pages/{page['id']}/reprocess", headers=AUTH)
    assert response.status_code == 202 and response.json()["status"] == "queued"
    wait_until_processed(client, document_id)
    assert len(fake_ocr.requests) == 2
    assert client.get(f"/api/pages/{page['id']}", headers=AUTH).json()["status"] == "done"
    trashed = [p.name for p in (library_dir / ".trash").iterdir()]
    assert len(trashed) == 1 and trashed[0].endswith(f"-ocr-{page['key']}")
    assert client.post(f"/api/pages/{new_id()}/reprocess", headers=AUTH).status_code == 404


def test_deleting_a_page_moves_its_files_to_the_trash(client, library_dir):
    document_id = create_document(client)
    keep = upload(client, document_id, page_image(1)).json()
    gone = upload(client, document_id, page_image(2)).json()
    wait_until_processed(client, document_id)
    assert client.delete(f"/api/pages/{gone['id']}", headers=AUTH).status_code == 204
    assert client.delete(f"/api/pages/{gone['id']}", headers=AUTH).status_code == 404
    assert client.get(f"/api/pages/{gone['id']}", headers=AUTH).status_code == 404
    folder = library_dir / "sample-cafe-guide"
    assert not (folder / "scans" / f"{gone['key']}.jpg").exists()
    [trashed] = (library_dir / ".trash").iterdir()
    assert sorted(p.name for p in trashed.iterdir()) == ["images", "ocr", "pages", "scans"]
    document = get_document(client, document_id)
    assert [p["id"] for p in document["pages"]] == [keep["id"]]
    assert gone["key"] not in client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text


def test_library_files_catch_up_after_a_failed_write(client, library_dir, monkeypatch):
    document_id = create_document(client)
    keep = upload(client, document_id, page_image(1)).json()
    gone = upload(client, document_id, page_image(2)).json()
    wait_until_processed(client, document_id)
    document_md = library_dir / "sample-cafe-guide" / "document.md"
    wait_for(lambda: document_md.is_file() and gone["key"] in document_md.read_text())

    write_document = LibraryFiles.write_document
    failures: list[str] = []

    def full_disk_once(self, *args):
        if not failures:
            failures.append("ENOSPC")
            raise OSError(errno.ENOSPC, "No space left on device")
        write_document(self, *args)

    monkeypatch.setattr(LibraryFiles, "write_document", full_disk_once)
    assert client.delete(f"/api/pages/{gone['id']}", headers=AUTH).status_code == 204
    wait_for(lambda: failures)  # the rewrite after the deletion failed...
    # ...and is done again later, without any further change to the document.
    wait_for(lambda: gone["key"] not in document_md.read_text())
    assert keep["key"] in document_md.read_text()


def test_export_zip(client):
    document_id = create_document(client)
    page = upload(client, document_id, page_image(9)).json()
    wait_until_processed(client, document_id)
    without_scans = client.get(f"/api/documents/{document_id}/export.zip", headers=AUTH)
    assert without_scans.headers["content-type"] == "application/zip"
    assert without_scans.headers["content-disposition"] == 'attachment; filename="sample-cafe-guide.zip"'
    names = zipfile.ZipFile(io.BytesIO(without_scans.content)).namelist()
    assert names == [
        "sample-cafe-guide/document.md",
        "sample-cafe-guide/document.json",
        f"sample-cafe-guide/pages/{page['key']}.md",
        f"sample-cafe-guide/images/{page['key']}_1.jpg",
        f"sample-cafe-guide/ocr/{page['key']}.json",
    ]
    with_scans = zipfile.ZipFile(
        io.BytesIO(client.get(f"/api/documents/{document_id}/export.zip?scans=1", headers=AUTH).content)
    )
    assert with_scans.testzip() is None
    assert with_scans.read(f"sample-cafe-guide/scans/{page['key']}.jpg") == page_image(9)
    assert "# Sample Café Guide" in with_scans.read("sample-cafe-guide/document.md").decode()


def test_hostile_ocr_output_is_sanitized_end_to_end(client, fake_ocr, library_dir):
    fake_ocr.evil = True
    document_id = create_document(client)
    page = upload(client, document_id, page_image(4)).json()
    wait_until_processed(client, document_id)
    stored = (library_dir / "sample-cafe-guide" / "pages" / f"{page['key']}.md").read_text()
    for forbidden in ("<script", "onerror", "onload", "<iframe", "<svg", "](javascript", "<!--"):
        assert forbidden not in stored
    assert sorted(p.name for p in (library_dir / "sample-cafe-guide" / "images").iterdir()) == [f"{page['key']}_1.jpg"]
    html = client.get(f"/api/pages/{page['id']}/html", headers=AUTH).json()["html"]
    assert "<script" not in html and "onerror" not in html
    assert 'href="javascript' not in html and 'src="http' not in html
    document_md = client.get(f"/api/documents/{document_id}/markdown", headers=AUTH).text
    assert document_md.count("<!--") == 1  # only our page marker
    # Rendered by a plain CommonMark renderer (raw HTML on, front matter unknown):
    # only the page's own illustration may be loaded, nothing else is markup.
    rendered = MarkdownIt("commonmark").render(document_md)
    assert re.findall(r"<(img|script|a)\b[^>]*>", rendered) == ["img"]
    assert f'src="images/{page["key"]}_1.jpg"' in rendered


def test_document_options_reach_the_sandbox(client, fake_ocr):
    document_id = create_document(client, unwarp=True)
    upload(client, document_id, page_image(1))
    wait_until_processed(client, document_id)
    params = fake_ocr.requests[-1]["params"]
    assert (params["unwarp"], params["orientation"]) == ("1", "1")
    assert params["request_id"] == get_document(client, document_id)["pages"][0]["id"]
