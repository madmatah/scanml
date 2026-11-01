"""The pages' thumbnails, as files of the state directory."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .library_files import atomic_write


class FilesystemThumbnails:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def prepare(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)

    def locate(self, page_id: str) -> Path:
        return self._directory / f"{page_id}.jpg"

    def is_stored(self, page_id: str) -> bool:
        return self.locate(page_id).is_file()

    def store(self, page_id: str, thumbnail: bytes) -> None:
        atomic_write(self.locate(page_id), thumbnail)

    def remove(self, page_ids: Iterable[str]) -> None:
        for page_id in page_ids:
            self.locate(page_id).unlink(missing_ok=True)
