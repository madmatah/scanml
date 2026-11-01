"""The pages' thumbnails on disk (adapters/filesystem/thumbnails.py): a cache in the state directory."""

from __future__ import annotations

import errno
import functools
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from scanmylib.adapters.filesystem import thumbnails as filesystem_thumbnails
from scanmylib.adapters.filesystem.thumbnails import FilesystemThumbnails

PAGE_ID = "0f8e2c4a-6b1d-4e3f-9a7c-5d2b8e1f3a6c"
OTHER_PAGE_ID = "7c3d9e1b-2a4f-4b8c-8d6e-1f5a3b9c7e2d"
THUMBNAIL_FILE_NAME = f"{PAGE_ID}.jpg"
FIRST_THUMBNAIL = b"first thumbnail"
SECOND_THUMBNAIL = b"second thumbnail"


def list_files_under(folder: Path) -> list[str]:
    return sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file())


def fail_to_write(path: Path, content: bytes) -> None:
    raise OSError(errno.ENOSPC, "No space left on device")


class TestTheFilesystemThumbnails:
    @pytest.fixture
    def thumbnail_directory(self, tmp_path: Path) -> Path:
        return tmp_path / "thumbnails"

    @pytest.fixture
    def thumbnails(self, thumbnail_directory: Path) -> FilesystemThumbnails:
        thumbnail_cache = FilesystemThumbnails(thumbnail_directory)
        thumbnail_cache.prepare()
        return thumbnail_cache

    class TestTheLocateMethod:
        @pytest.fixture
        def thumbnail_path(self, thumbnails: FilesystemThumbnails) -> Path:
            return thumbnails.locate(PAGE_ID)

        def test_should_name_the_file_after_the_page_id_in_the_thumbnail_directory_so_that_the_cache_keeps_its_layout(
            self, thumbnail_path: Path, thumbnail_directory: Path
        ) -> None:
            assert thumbnail_path.relative_to(thumbnail_directory).as_posix() == THUMBNAIL_FILE_NAME

        def test_should_create_no_file_since_locating_a_thumbnail_touches_no_disk(
            self, thumbnail_path: Path, thumbnail_directory: Path
        ) -> None:
            assert os.listdir(thumbnail_directory) == []

    class TestTheIsStoredMethod:
        class TestWhenThePageHasAThumbnail:
            @pytest.fixture
            def is_stored(self, thumbnails: FilesystemThumbnails) -> bool:
                thumbnails.store(PAGE_ID, FIRST_THUMBNAIL)
                return thumbnails.is_stored(PAGE_ID)

            def test_should_return_true(self, is_stored: bool) -> None:
                assert is_stored is True

        class TestWhenThePageHasNoThumbnail:
            @pytest.fixture
            def is_stored(self, thumbnails: FilesystemThumbnails) -> bool:
                return thumbnails.is_stored(PAGE_ID)

            def test_should_return_false(self, is_stored: bool) -> None:
                assert is_stored is False

    class TestTheStoreMethod:
        class TestWhenThePageAlreadyHasAThumbnail:
            @pytest.fixture(autouse=True)
            def store_twice(self, thumbnails: FilesystemThumbnails) -> None:
                thumbnails.store(PAGE_ID, FIRST_THUMBNAIL)
                thumbnails.store(PAGE_ID, SECOND_THUMBNAIL)

            def test_should_replace_the_thumbnail(self, thumbnail_directory: Path) -> None:
                assert (thumbnail_directory / THUMBNAIL_FILE_NAME).read_bytes() == SECOND_THUMBNAIL

            def test_should_leave_no_temporary_file_beside_it(self, thumbnail_directory: Path) -> None:
                assert os.listdir(thumbnail_directory) == [THUMBNAIL_FILE_NAME]

        class TestWhenTheDiskFails:
            @pytest.fixture
            def store_thumbnail(
                self, thumbnails: FilesystemThumbnails, monkeypatch: pytest.MonkeyPatch
            ) -> Callable[[], None]:
                monkeypatch.setattr(filesystem_thumbnails, "atomic_write", fail_to_write)
                return functools.partial(thumbnails.store, PAGE_ID, FIRST_THUMBNAIL)

            def test_should_fail_with_the_error_of_the_disk(self, store_thumbnail: Callable[[], None]) -> None:
                with pytest.raises(OSError, match="No space left on device"):
                    store_thumbnail()

    class TestTheRemoveMethod:
        class TestWhenThePageHasAThumbnail:
            @pytest.fixture(autouse=True)
            def store_then_remove(self, thumbnails: FilesystemThumbnails) -> None:
                thumbnails.store(PAGE_ID, FIRST_THUMBNAIL)
                thumbnails.remove([PAGE_ID])

            def test_should_delete_the_file_and_move_it_to_no_trash_since_a_thumbnail_is_only_a_cache(
                self, tmp_path: Path
            ) -> None:
                assert list_files_under(tmp_path) == []

        class TestWhenAPageBeforeAnotherHasNoThumbnail:
            @pytest.fixture(autouse=True)
            def remove_missing_then_stored(self, thumbnails: FilesystemThumbnails) -> None:
                thumbnails.store(OTHER_PAGE_ID, FIRST_THUMBNAIL)
                thumbnails.remove([PAGE_ID, OTHER_PAGE_ID])

            def test_should_still_remove_the_thumbnail_of_the_other_page_since_a_missing_thumbnail_is_already_removed(
                self, thumbnail_directory: Path
            ) -> None:
                assert os.listdir(thumbnail_directory) == []
