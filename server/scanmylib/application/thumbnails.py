"""A page's thumbnail is a JPEG kept as a cache outside the library, so removing one deletes it, where the library's
files go to the trash, and removing a missing one is no error. Locating a thumbnail touches no disk. Storing one
replaces it at once, and a failure of the disk raises OSError.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePath
from typing import Protocol


class Thumbnails(Protocol):
    def prepare(self) -> None: ...
    def locate(self, page_id: str) -> PurePath: ...
    def is_stored(self, page_id: str) -> bool: ...
    def store(self, page_id: str, thumbnail: bytes) -> None: ...
    def remove(self, page_ids: Iterable[str]) -> None: ...
