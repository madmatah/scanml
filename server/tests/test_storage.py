"""Library folder operations (storage.py): atomic writes, trash, safe file resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

import pytest

from scanmylib.storage import TRASH_DIR, LibraryFiles, atomic_write

SLUG = "book"
KEY = "20261012-201530_1a2b3c4d"
SCAN = b"scan"
ILLUSTRATION = b"img"


class RefusedPath(NamedTuple):
    path: str
    files_it_names: tuple[str, ...]


class TrashedTwice(NamedTuple):
    first_trash: Path | None
    second_trash: Path | None


def read_files_under(folder: Path) -> dict[str, bytes]:
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}


def write_files(document_folder: Path, relative_paths: tuple[str, ...]) -> None:
    for relative_path in relative_paths:
        path = document_folder / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")


def write_a_page_and_its_document(files: LibraryFiles) -> None:
    files.write_scan(SLUG, KEY, "jpg", SCAN)
    files.write_page_outputs(SLUG, KEY, "text", [(f"{KEY}_1.jpg", ILLUSTRATION)], {})
    files.write_document(SLUG, "# Book\n", {"title": "Book"})


class TestTheStorage:
    @pytest.fixture
    def files(self, tmp_path: Path) -> LibraryFiles:
        library = LibraryFiles(tmp_path / "library")
        library.ensure_root()
        library.ensure_document_dir(SLUG)
        return library

    class TestTheAtomicWriteFunction:
        class TestWhenTheFileExists:
            @pytest.fixture
            def written_file(self, tmp_path: Path) -> Path:
                target = tmp_path / "a" / "b.txt"
                atomic_write(target, b"one")
                atomic_write(target, b"two")
                return target

            def test_should_replace_its_content(self, written_file: Path) -> None:
                assert written_file.read_bytes() == b"two"

            def test_should_leave_no_temporary_file_beside_it(self, written_file: Path) -> None:
                assert os.listdir(written_file.parent) == ["b.txt"]

            def test_should_let_everyone_read_it_and_only_its_owner_write_it(self, written_file: Path) -> None:
                assert oct(written_file.stat().st_mode & 0o777) == "0o644"

    class TestTheWritePageOutputsMethod:
        class TestWhenThePageHasAnEarlierOcrOutput:
            @pytest.fixture(autouse=True)
            def trash_folders(self, files: LibraryFiles) -> list[Path]:
                first_images = [(f"{KEY}_1.jpg", b"i1"), (f"{KEY}_2.jpg", b"i2")]
                files.write_page_outputs(SLUG, KEY, "v1", first_images, {"v": 1})
                files.write_page_outputs(SLUG, KEY, "v2", [(f"{KEY}_1.jpg", b"j1")], {"v": 2})
                return sorted(files.trash.iterdir())

            def test_should_keep_only_the_new_markdown(self, files: LibraryFiles) -> None:
                assert (files.root / SLUG / "pages" / f"{KEY}.md").read_text() == "v2"

            def test_should_keep_only_the_new_illustrations(self, files: LibraryFiles) -> None:
                illustrations = files.root / SLUG / "images"
                assert sorted(path.name for path in illustrations.iterdir()) == [f"{KEY}_1.jpg"]

            def test_should_move_the_earlier_output_to_one_trash_folder_named_after_the_document_and_the_page(
                self, trash_folders: list[Path]
            ) -> None:
                names = [folder.name for folder in trash_folders]
                assert [(name.startswith(f"{SLUG}-"), name.endswith(f"-ocr-{KEY}")) for name in names] == [(True, True)]

            def test_should_keep_the_earlier_markdown_in_the_trash(self, trash_folders: list[Path]) -> None:
                assert [(folder / "pages" / f"{KEY}.md").read_text() for folder in trash_folders] == ["v1"]

            def test_should_keep_every_earlier_illustration_in_the_trash(self, trash_folders: list[Path]) -> None:
                illustrations = [sorted(path.name for path in (trash / "images").iterdir()) for trash in trash_folders]
                assert illustrations == [[f"{KEY}_1.jpg", f"{KEY}_2.jpg"]]

    class TestTheTrashPageMethod:
        class TestWhenThePageHasAScanAndAnOcrOutput:
            @pytest.fixture(autouse=True)
            def page_trash(self, files: LibraryFiles) -> Path | None:
                files.write_scan(SLUG, KEY, "jpg", SCAN)
                files.write_page_outputs(SLUG, KEY, "text", [], {})
                return files.trash_page(SLUG, KEY, "jpg")

            def test_should_move_the_scan_to_the_trash_folder_it_returns(self, page_trash: Path | None) -> None:
                assert page_trash is not None
                assert read_files_under(page_trash).get(f"scans/{KEY}.jpg") == SCAN

            def test_should_move_the_markdown_to_the_trash_folder_it_returns(self, page_trash: Path | None) -> None:
                assert page_trash is not None
                assert f"pages/{KEY}.md" in read_files_under(page_trash)

            def test_should_leave_no_scan_in_the_document_folder(self, files: LibraryFiles) -> None:
                assert not (files.root / SLUG / "scans" / f"{KEY}.jpg").exists()

    class TestTheTrashDocumentMethod:
        class TestWhenTheDocumentFolderExists:
            @pytest.fixture(autouse=True)
            def document_trash(self, files: LibraryFiles) -> Path | None:
                return files.trash_document(SLUG)

            def test_should_move_the_folder_into_the_trash(
                self, files: LibraryFiles, document_trash: Path | None
            ) -> None:
                assert document_trash is not None
                assert document_trash.parent == files.root / TRASH_DIR

            def test_should_leave_no_document_folder(self, files: LibraryFiles) -> None:
                assert not (files.root / SLUG).exists()

            class TestWhenTheDocumentIsTrashedAgain:
                @pytest.fixture
                def second_trash(self, files: LibraryFiles, document_trash: Path | None) -> Path | None:
                    return files.trash_document(SLUG)

                def test_should_return_none_since_there_is_no_folder_left(self, second_trash: Path | None) -> None:
                    assert second_trash is None

        class TestWhenADocumentOfTheSameSlugWasTrashedJustBefore:
            @pytest.fixture
            def trashed_twice(self, files: LibraryFiles) -> TrashedTwice:
                first_trash = files.trash_document(SLUG)
                files.ensure_document_dir(SLUG)
                return TrashedTwice(first_trash=first_trash, second_trash=files.trash_document(SLUG))

            def test_should_give_the_second_trash_folder_another_name(self, trashed_twice: TrashedTwice) -> None:
                assert None not in trashed_twice
                assert trashed_twice.first_trash != trashed_twice.second_trash

            def test_should_keep_both_trash_folders(self, trashed_twice: TrashedTwice) -> None:
                assert [folder is not None and folder.exists() for folder in trashed_twice] == [True, True]

    class TestTheResolveDocumentFileMethod:
        class TestWhenThePathIsNotThatOfAServableFile:
            refused_paths = (
                ("a path through the parent folder", RefusedPath("../book/document.md", ("document.md",))),
                ("an absolute path", RefusedPath("/etc/passwd", ())),
                ("a path climbing out of a subfolder", RefusedPath("pages/../../../etc/passwd", ("../../etc/passwd",))),
                (
                    "an encoded path climbing out of a subfolder",
                    RefusedPath("pages/..%2f..%2fx.md", ("pages/..%2f..%2fx.md",)),
                ),
                ("a page that is not markdown", RefusedPath("pages/x.txt", ("pages/x.txt",))),
                ("a hidden illustration", RefusedPath("images/.hidden.jpg", ("images/.hidden.jpg",))),
                ("a scan that is not a jpeg png or webp image", RefusedPath("scans/x.gif", ("scans/x.gif",))),
                ("an ocr result that is not json", RefusedPath("ocr/x.md", ("ocr/x.md",))),
                ("a file named as a folder", RefusedPath("document.md/", ("document.md",))),
                ("a subfolder", RefusedPath("pages/", ("pages/x.txt",))),
                ("an illustration in a nested folder", RefusedPath("images/a/b.jpg", ("images/a/b.jpg",))),
                ("a backslash", RefusedPath("pages\\x.md", ("pages\\x.md",))),
                ("an empty path", RefusedPath("", ())),
            )

            @pytest.fixture(
                params=[refused_path for _, refused_path in refused_paths], ids=[name for name, _ in refused_paths]
            )
            def resolved_file(self, request: pytest.FixtureRequest, files: LibraryFiles) -> Path | None:
                refused_path: RefusedPath = request.param
                write_files(files.document_dir(SLUG), refused_path.files_it_names)
                return files.resolve_document_file(SLUG, refused_path.path)

            def test_should_return_none(self, resolved_file: Path | None) -> None:
                assert resolved_file is None

        class TestWhenAPageIsALinkOutOfTheFolder:
            @pytest.fixture
            def resolved_file(self, files: LibraryFiles, tmp_path: Path) -> Path | None:
                secret = tmp_path / "secret.md"
                secret.write_text("secret")
                pages = files.document_dir(SLUG) / "pages"
                pages.mkdir()
                (pages / "evil.md").symlink_to(secret)
                return files.resolve_document_file(SLUG, "pages/evil.md")

            def test_should_return_none(self, resolved_file: Path | None) -> None:
                assert resolved_file is None

        class TestWhenThePathIsThatOfAnIllustrationOfAPage:
            @pytest.fixture
            def illustration(self, files: LibraryFiles) -> Path | None:
                write_a_page_and_its_document(files)
                return files.resolve_document_file(SLUG, f"images/{KEY}_1.jpg")

            def test_should_return_the_path_of_the_illustration(self, illustration: Path | None) -> None:
                assert illustration is not None
                assert illustration.read_bytes() == ILLUSTRATION

    class TestTheExportEntriesMethod:
        class TestWhenTheScansAreLeftOut:
            @pytest.fixture
            def archive_names(self, files: LibraryFiles) -> list[str]:
                write_a_page_and_its_document(files)
                return [name for name, _ in files.export_entries(SLUG, include_scans=False)]

            def test_should_list_the_document_then_each_page_s_markdown_illustrations_and_ocr_result(
                self, archive_names: list[str]
            ) -> None:
                assert archive_names == [
                    "book/document.md",
                    "book/document.json",
                    f"book/pages/{KEY}.md",
                    f"book/images/{KEY}_1.jpg",
                    f"book/ocr/{KEY}.json",
                ]

        class TestWhenTheScansAreIncluded:
            @pytest.fixture
            def archive_names(self, files: LibraryFiles) -> list[str]:
                write_a_page_and_its_document(files)
                return [name for name, _ in files.export_entries(SLUG, include_scans=True)]

            def test_should_list_the_scans_too(self, archive_names: list[str]) -> None:
                assert f"book/scans/{KEY}.jpg" in archive_names
