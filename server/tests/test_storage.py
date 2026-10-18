"""Library folder operations (storage.py): atomic writes, trash, safe file resolution."""

from __future__ import annotations

import os

import pytest

from scanmylib.storage import LibraryFiles, atomic_write

KEY = "20261012-201530_1a2b3c4d"


@pytest.fixture
def files(tmp_path) -> LibraryFiles:
    library = LibraryFiles(tmp_path / "library")
    library.ensure_root()
    library.ensure_document_dir("book")
    return library


def test_atomic_write_replaces_without_leftovers(tmp_path):
    target = tmp_path / "a" / "b.txt"
    atomic_write(target, b"one")
    atomic_write(target, b"two")
    assert target.read_bytes() == b"two"
    assert os.listdir(target.parent) == ["b.txt"]
    assert oct(target.stat().st_mode & 0o777) == "0o644"


def test_new_ocr_output_moves_the_previous_one_to_the_trash(files):
    files.write_page_outputs("book", KEY, "v1", [(f"{KEY}_1.jpg", b"i1"), (f"{KEY}_2.jpg", b"i2")], {"v": 1})
    files.write_page_outputs("book", KEY, "v2", [(f"{KEY}_1.jpg", b"j1")], {"v": 2})
    folder = files.document_dir("book")
    assert (folder / "pages" / f"{KEY}.md").read_text() == "v2"
    assert sorted(p.name for p in (folder / "images").iterdir()) == [f"{KEY}_1.jpg"]
    [trashed] = list(files.trash.iterdir())
    assert trashed.name.startswith("book-") and trashed.name.endswith(f"-ocr-{KEY}")
    assert (trashed / "pages" / f"{KEY}.md").read_text() == "v1"
    assert sorted(p.name for p in (trashed / "images").iterdir()) == [f"{KEY}_1.jpg", f"{KEY}_2.jpg"]


def test_trash_page_and_document(files):
    files.write_scan("book", KEY, "jpg", b"scan")
    files.write_page_outputs("book", KEY, "text", [], {})
    page_trash = files.trash_page("book", KEY, "jpg")
    assert (page_trash / "scans" / f"{KEY}.jpg").read_bytes() == b"scan"
    assert (page_trash / "pages" / f"{KEY}.md").is_file()
    assert not files.scan_path("book", KEY, "jpg").exists()

    document_trash = files.trash_document("book")
    assert document_trash.parent == files.trash
    assert not files.folder_exists("book")
    assert files.trash_document("book") is None


def test_trash_names_never_collide(files):
    first = files.trash_document("book")
    files.ensure_document_dir("book")
    second = files.trash_document("book")
    assert first != second and first.exists() and second.exists()


@pytest.mark.parametrize(
    "relative",
    [
        "../book/document.md",
        "/etc/passwd",
        "pages/../../../etc/passwd",
        "pages/..%2f..%2fx.md",
        "pages/x.txt",
        "images/.hidden.jpg",
        "scans/x.gif",
        "ocr/x.md",
        "document.md/",
        "pages/",
        "images/a/b.jpg",
        "pages\\x.md",
        "",
    ],
)
def test_file_resolution_rejects_anything_unexpected(files, relative):
    (files.document_dir("book") / "pages").mkdir(exist_ok=True)
    (files.document_dir("book") / "pages" / "x.txt").write_text("x")
    assert files.resolve_document_file("book", relative) is None


def test_file_resolution_rejects_symlinks_leaving_the_folder(files, tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("secret")
    pages = files.document_dir("book") / "pages"
    pages.mkdir()
    (pages / "evil.md").symlink_to(secret)
    assert files.resolve_document_file("book", "pages/evil.md") is None


def test_file_resolution_and_export_entries(files):
    files.write_scan("book", KEY, "jpg", b"scan")
    files.write_page_outputs("book", KEY, "text", [(f"{KEY}_1.jpg", b"img")], {})
    files.write_document("book", "# Book\n", {"title": "Book"})
    assert files.resolve_document_file("book", f"images/{KEY}_1.jpg").read_bytes() == b"img"
    names = [name for name, _ in files.export_entries("book", include_scans=False)]
    assert names == [
        "book/document.md",
        "book/document.json",
        f"book/pages/{KEY}.md",
        f"book/images/{KEY}_1.jpg",
        f"book/ocr/{KEY}.json",
    ]
    assert f"book/scans/{KEY}.jpg" in [name for name, _ in files.export_entries("book", include_scans=True)]
