"""Files of the library (LIBRARY_DIR): document folders, atomic writes, trash.

Nothing is ever deleted here: removed documents, removed pages and OCR
results replaced by a new run are moved to ``.trash/`` with a timestamp.
Every file is written atomically (temporary file in the same folder, then
rename), so agents reading the library never see half-written files.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from .application.clock import Clock
from .domain import timestamps

TRASH_DIR = ".trash"
DOCUMENT_MARKDOWN = "document.md"
DOCUMENT_METADATA = "document.json"
INDEX_MARKDOWN = "INDEX.md"
INDEX_METADATA = "library.json"

_NAME = r"[A-Za-z0-9_-][A-Za-z0-9._-]*"
# Files of a document folder that may be served or exported.
_DOCUMENT_FILE = re.compile(
    rf"document\.md|document\.json|pages/{_NAME}\.md|images/{_NAME}\.jpg"
    rf"|ocr/{_NAME}\.json|scans/{_NAME}\.(?:jpg|png|webp)"
)
_SUBFOLDERS = ("pages", "images", "ocr", "scans")


def atomic_write(path: Path, data: bytes) -> None:
    """Write `data` to `path` so that readers see either the old or the new file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class LibraryFiles:
    """Paths and file operations under the library root."""

    def __init__(self, root: Path, clock: Clock) -> None:
        self.root = root
        self._clock = clock

    @property
    def trash(self) -> Path:
        return self.root / TRASH_DIR

    def ensure_root(self) -> None:
        self.trash.mkdir(parents=True, exist_ok=True)

    def document_dir(self, slug: str) -> Path:
        return self.root / slug

    def folder_exists(self, slug: str) -> bool:
        return self.document_dir(slug).exists()

    def ensure_document_dir(self, slug: str) -> None:
        self.document_dir(slug).mkdir(parents=True, exist_ok=True)

    # -- pages -------------------------------------------------------------

    def scan_path(self, slug: str, key: str, ext: str) -> Path:
        return self.document_dir(slug) / "scans" / f"{key}.{ext}"

    def write_scan(self, slug: str, key: str, ext: str, data: bytes) -> None:
        atomic_write(self.scan_path(slug, key, ext), data)

    def page_markdown_path(self, slug: str, key: str) -> Path:
        return self.document_dir(slug) / "pages" / f"{key}.md"

    def read_page_markdown(self, slug: str, key: str) -> str:
        """Content of pages/<key>.md, empty if the page has no OCR output (yet)."""
        try:
            return self.page_markdown_path(slug, key).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    def _page_outputs(self, slug: str, key: str) -> list[Path]:
        folder = self.document_dir(slug)
        candidates = [folder / "pages" / f"{key}.md", folder / "ocr" / f"{key}.json"]
        images = folder / "images"
        if images.is_dir():
            candidates += sorted(images.glob(f"{key}_*.jpg"))
        return [path for path in candidates if path.is_file()]

    def write_page_outputs(
        self,
        slug: str,
        key: str,
        markdown: str,
        images: Sequence[tuple[str, bytes]],
        raw: Mapping[str, object],
    ) -> None:
        """Store an OCR result; a previous result of the same page goes to the trash.

        The Markdown is written last: its presence means the page is complete.
        """
        previous = self._page_outputs(slug, key)
        if previous:
            self._move_to_trash(slug, previous, f"{slug}-{timestamps.compact(self._clock.now())}-ocr-{key}")
        folder = self.document_dir(slug)
        for filename, data in images:
            atomic_write(folder / "images" / filename, data)
        atomic_write(folder / "ocr" / f"{key}.json", _json_bytes(raw))
        atomic_write(folder / "pages" / f"{key}.md", markdown.encode("utf-8"))

    def trash_page(self, slug: str, key: str, ext: str) -> Path | None:
        """Move a page's scan and OCR outputs to the trash."""
        files = self._page_outputs(slug, key)
        scan = self.scan_path(slug, key, ext)
        if scan.is_file():
            files.append(scan)
        if not files:
            return None
        return self._move_to_trash(slug, files, f"{slug}-{timestamps.compact(self._clock.now())}-page-{key}")

    # -- documents ---------------------------------------------------------

    def trash_document(self, slug: str) -> Path | None:
        """Move a whole document folder to the trash."""
        folder = self.document_dir(slug)
        if not folder.exists():
            return None
        target = self._unique_trash_dir(f"{slug}-{timestamps.compact(self._clock.now())}")
        os.rename(folder, target)
        return target

    def write_document(self, slug: str, markdown: str, metadata: Mapping[str, object]) -> None:
        folder = self.document_dir(slug)
        atomic_write(folder / DOCUMENT_METADATA, _json_bytes(metadata))
        atomic_write(folder / DOCUMENT_MARKDOWN, markdown.encode("utf-8"))

    def write_index(self, markdown: str, metadata: Mapping[str, object]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write(self.root / INDEX_METADATA, _json_bytes(metadata))
        atomic_write(self.root / INDEX_MARKDOWN, markdown.encode("utf-8"))

    def resolve_document_file(self, slug: str, relative: str) -> Path | None:
        """Path of a servable file of the document, or None (unknown, missing, traversal)."""
        if not _DOCUMENT_FILE.fullmatch(relative):
            return None
        folder = self.document_dir(slug).resolve()
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            return None
        return path

    def export_entries(self, slug: str, include_scans: bool) -> list[tuple[str, Path]]:
        """(archive name, path) of the document's files, for export.zip."""
        folder = self.document_dir(slug)
        entries: list[tuple[str, Path]] = []
        for name in (DOCUMENT_MARKDOWN, DOCUMENT_METADATA):
            if (folder / name).is_file():
                entries.append((f"{slug}/{name}", folder / name))
        for subfolder in _SUBFOLDERS:
            if subfolder == "scans" and not include_scans:
                continue
            for path in self._regular_files(folder / subfolder):
                relative = f"{subfolder}/{path.name}"
                if _DOCUMENT_FILE.fullmatch(relative):
                    entries.append((f"{slug}/{relative}", path))
        return entries

    @staticmethod
    def _regular_files(folder: Path) -> Iterable[Path]:
        if not folder.is_dir():
            return []
        with os.scandir(folder) as scan:
            names = sorted(e.name for e in scan if e.is_file(follow_symlinks=False))
        return [folder / name for name in names]

    # -- trash -------------------------------------------------------------

    def _unique_trash_dir(self, name: str) -> Path:
        self.ensure_root()
        target = self.trash / name
        suffix = 2
        while target.exists():
            target = self.trash / f"{name}-{suffix}"
            suffix += 1
        return target

    def _move_to_trash(self, slug: str, files: Sequence[Path], name: str) -> Path:
        """Move files of a document folder into a new trash folder, keeping their layout."""
        target = self._unique_trash_dir(name)
        folder = self.document_dir(slug)
        for path in files:
            destination = target / path.relative_to(folder)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(path, destination)
        return target
