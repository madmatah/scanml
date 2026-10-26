"""Documents and pages: the SQLite state kept in sync with the library folder.

Every mutation goes through `LibraryService`:

* database changes happen in one transaction, without awaiting inside it, and
  end with `_refresh_layout`, which recomputes page numbers, duplicates,
  reading order and coverage (ordering.py) and stores them;
* file changes in a document folder happen under that document's lock, so a
  deletion (move to the trash) never races with a write into the folder;
* document.md / document.json / INDEX.md / library.json are rewritten by a
  debounced background batch (`schedule`), or immediately via `flush`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path

from . import clock, images
from .adapters.sqlite.database import Database
from .adapters.sqlite.rows import build_document_record, build_page_claim, build_page_record, encode_layout_summary
from .config import Settings
from .debounce import DebouncedBatch
from .domain import ordering, timestamps
from .domain.documents import check_document_changes, prepare_new_document, propose_slugs, summarize_layout
from .domain.pages import (
    AttemptOutcome,
    conclude_failed_attempt,
    conclude_released_attempt,
    propose_page_keys,
    summarize_ocr,
)
from .domain.records import (
    UNCHANGED,
    Conflict,
    DocumentChanges,
    DocumentRecord,
    NotFound,
    PageChanges,
    PageClaim,
    PageRecord,
    PageUpload,
)
from .ocr_result import PageOcrOutput
from .publisher import Publisher
from .storage import DOCUMENT_MARKDOWN, LibraryFiles, atomic_write

log = logging.getLogger(__name__)

_LAYOUT_COLUMNS = (
    "number",
    "number_end",
    "front_matter",
    "number_source",
    "page_label",
    "duplicate_of",
    "in_document",
    "placement",
    "rank",
)


class LibraryService:
    def __init__(self, settings: Settings, db: Database, files: LibraryFiles) -> None:
        self._settings = settings
        self._db = db
        self._files = files
        self._publisher = Publisher(files)
        self._locks: dict[str, asyncio.Lock] = {}
        #: Ids of the pages whose upload is being stored (their row does not exist yet).
        self._storing: set[str] = set()
        # HTML previews are rendered one at a time: rendering is CPU-bound, and
        # parallel renders of a hostile page would occupy every worker thread.
        self._render_lock = asyncio.Lock()
        self._assembly = DebouncedBatch(self._assemble, settings.assemble_delay_s)
        self._work_listeners: list[Callable[[], None]] = []

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> int:
        """Prepare folders, recover an interrupted run, start the assembly batch.

        Returns the number of pages that were being processed and are re-queued.
        """
        self._files.ensure_root()
        self._settings.thumbs_dir.mkdir(parents=True, exist_ok=True)
        with self._db.transaction():
            requeued = self._db.execute("UPDATE pages SET status = 'queued' WHERE status = 'processing'").rowcount
            document_ids = [row["id"] for row in self._db.all("SELECT id FROM documents")]
            for document_id in document_ids:
                self._refresh_layout(document_id)
        self._assembly.start()
        for document_id in document_ids:
            self._assembly.schedule(document_id)
        self._assembly.schedule()
        return requeued

    async def aclose(self) -> None:
        await self._assembly.aclose()

    def add_work_listener(self, listener: Callable[[], None]) -> None:
        """Call `listener` whenever pages are queued for OCR."""
        self._work_listeners.append(listener)

    def _work_queued(self) -> None:
        for listener in self._work_listeners:
            listener()

    def _lock(self, document_id: str) -> asyncio.Lock:
        return self._locks.setdefault(document_id, asyncio.Lock())

    # -- queries -------------------------------------------------------------

    def list_documents(self) -> list[DocumentRecord]:
        rows = self._db.all("SELECT * FROM documents ORDER BY updated_ts DESC, id")
        return [build_document_record(row) for row in rows]

    def get_document(self, document_id: str) -> DocumentRecord | None:
        row = self._db.one("SELECT * FROM documents WHERE id = ?", (document_id,))
        return build_document_record(row) if row else None

    def require_document(self, document_id: str) -> DocumentRecord:
        document = self.get_document(document_id)
        if document is None:
            raise NotFound("document not found")
        return document

    def list_pages(self, document_id: str) -> list[PageRecord]:
        """Pages of a document in the API order (reading order first)."""
        rows = self._db.all(
            "SELECT * FROM pages WHERE document_id = ? ORDER BY rank, captured_ts, id",
            (document_id,),
        )
        return [build_page_record(row) for row in rows]

    def get_page(self, page_id: str) -> PageRecord | None:
        row = self._db.one("SELECT * FROM pages WHERE id = ?", (page_id,))
        return build_page_record(row) if row else None

    def require_page(self, page_id: str) -> PageRecord:
        page = self.get_page(page_id)
        if page is None:
            raise NotFound("page not found")
        return page

    def queue_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(("queued", "processing", "error", "done"), 0)
        for row in self._db.all("SELECT status, COUNT(*) AS n FROM pages GROUP BY status"):
            counts[row["status"]] = row["n"]
        return counts

    def folder(self, document: DocumentRecord) -> str:
        """Host path of a document folder (display only)."""
        return f"{self._settings.library_host_path.rstrip('/')}/{document.slug}"

    def scan_path(self, page: PageRecord, document: DocumentRecord) -> Path:
        return self._files.scan_path(document.slug, page.key, page.scan_ext)

    def _thumb_path(self, page_id: str) -> Path:
        return self._settings.thumbs_dir / f"{page_id}.jpg"

    async def thumbnail(self, page: PageRecord) -> Path:
        """Thumbnail of a page, regenerated if the state directory lost it."""
        path = self._thumb_path(page.id)
        if not path.is_file():
            scan = self.scan_path(page, self.require_document(page.document_id))
            data = await asyncio.to_thread(images.make_thumbnail, scan, page.rotation)
            await asyncio.to_thread(atomic_write, path, data)
        return path

    async def page_markdown(self, page: PageRecord) -> str:
        document = self.require_document(page.document_id)
        return await asyncio.to_thread(self._files.read_page_markdown, document.slug, page.key)

    async def page_html(self, page: PageRecord) -> str:
        document = self.require_document(page.document_id)
        async with self._render_lock:
            return await asyncio.to_thread(self._publisher.page_html, document, page)

    async def document_html(self, document: DocumentRecord) -> str:
        pages = self.list_pages(document.id)
        async with self._render_lock:
            return await asyncio.to_thread(self._publisher.document_html, document, pages)

    async def document_markdown(self, document: DocumentRecord) -> str:
        """Current document.md (written now if a rewrite is pending or the file is missing)."""
        await self._assembly.flush(document.id)
        path = self._files.document_dir(document.slug) / DOCUMENT_MARKDOWN
        if not path.is_file():
            self._assembly.schedule(document.id)
            await self._assembly.flush(document.id)
        return await asyncio.to_thread(path.read_text, encoding="utf-8")

    def document_file(self, document: DocumentRecord, relative: str) -> Path | None:
        return self._files.resolve_document_file(document.slug, relative)

    async def export_entries(self, document: DocumentRecord, include_scans: bool) -> list[tuple[str, Path]]:
        await self._assembly.flush(document.id)
        return await asyncio.to_thread(self._files.export_entries, document.slug, include_scans)

    # -- documents -----------------------------------------------------------

    async def put_document(self, document_id: str, changes: DocumentChanges) -> tuple[DocumentRecord, bool]:
        """Create the document, or update it if it exists. Returns (document, created)."""
        async with self._lock(document_id):
            if self.get_document(document_id) is not None:  # checked under the lock: retries race
                return self.update_document(document_id, changes), False
            new_document = prepare_new_document(changes)
            moment = clock.now()
            with self._db.transaction():
                slug = self._free_slug(new_document.title)
                self._db.execute(
                    "INSERT INTO documents (id, slug, title, author, kind, notes, unwarp,"
                    " created_at, updated_at, updated_ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        document_id,
                        slug,
                        new_document.title,
                        new_document.author,
                        new_document.kind,
                        new_document.notes,
                        int(new_document.unwarp),
                        timestamps.iso(moment),
                        timestamps.iso(moment),
                        moment.timestamp(),
                    ),
                )
                self._refresh_layout(document_id)
            await asyncio.to_thread(self._files.ensure_document_dir, slug)
        self._assembly.schedule(document_id)
        return self.require_document(document_id), True

    def update_document(self, document_id: str, changes: DocumentChanges) -> DocumentRecord:
        self.require_document(document_id)
        check_document_changes(changes)
        values: dict[str, object] = {
            name: value
            for name, value in (
                ("title", changes.title),
                ("author", changes.author),
                ("kind", changes.kind),
                ("notes", changes.notes),
                ("unwarp", None if changes.unwarp is None else int(changes.unwarp)),
            )
            if value is not None
        }
        if values:
            with self._db.transaction():
                assignments = ", ".join(f"{name} = ?" for name in values)
                self._db.execute(
                    f"UPDATE documents SET {assignments} WHERE id = ?",  # noqa: S608 (column names from the code, values as ? parameters)
                    (*values.values(), document_id),
                )
                self._touch(document_id)
            self._assembly.schedule(document_id)
        return self.require_document(document_id)

    async def delete_document(self, document_id: str) -> bool:
        """Move the document folder to the trash and forget the document."""
        async with self._lock(document_id):
            document = self.get_document(document_id)
            if document is None:
                return False
            page_ids = [r["id"] for r in self._db.all("SELECT id FROM pages WHERE document_id = ?", (document_id,))]
            trashed = await asyncio.to_thread(self._files.trash_document, document.slug)
            with self._db.transaction():
                self._db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            await asyncio.to_thread(self._remove_thumbnails, page_ids)
        log.info("document %s deleted, folder moved to %s", document.slug, trashed)
        self._assembly.schedule()
        return True

    def _free_slug(self, title: str) -> str:
        return next(
            slug
            for slug in propose_slugs(title)
            if self._db.one("SELECT 1 FROM documents WHERE slug = ?", (slug,)) is None
            and not self._files.folder_exists(slug)
        )

    def _touch(self, document_id: str) -> None:
        moment = clock.now()
        self._db.execute(
            "UPDATE documents SET updated_at = ?, updated_ts = ? WHERE id = ?",
            (timestamps.iso(moment), moment.timestamp(), document_id),
        )

    def _remove_thumbnails(self, page_ids: Iterable[str]) -> None:
        # Thumbnails are a cache in the state directory, not library content.
        for page_id in page_ids:
            self._thumb_path(page_id).unlink(missing_ok=True)

    # -- pages ---------------------------------------------------------------

    async def add_page(self, document_id: str, upload: PageUpload) -> tuple[PageRecord, bool]:
        """Store an uploaded scan and queue it. Returns (page, created); idempotent on page id."""
        self.require_document(document_id)
        existing = self.get_page(upload.page_id)
        if existing is not None:
            return self._same_document(existing, document_id), False
        info, thumbnail = await asyncio.to_thread(images.ingest_scan, upload.data)
        captured = upload.captured_at or clock.now()
        async with self._lock(document_id):
            document = self.require_document(document_id)
            existing = self.get_page(upload.page_id)
            if existing is not None:  # the same page, uploaded twice concurrently
                return self._same_document(existing, document_id), False
            # Same page id being stored right now: into another document, since
            # this document's lock is held. Checked and reserved without awaiting.
            if upload.page_id in self._storing:
                raise Conflict("page_id already used by another document")
            self._storing.add(upload.page_id)
            try:
                key = self._free_key(document_id, captured, upload.page_id)
                await asyncio.to_thread(
                    self._store_scan, document.slug, key, info.ext, upload.data, upload.page_id, thumbnail
                )
                uploaded = clock.now()
                with self._db.transaction():
                    self._db.execute(
                        "INSERT INTO pages (id, document_id, key, scan_ext, session_id, seq,"
                        " captured_at, captured_ts, uploaded_at, uploaded_ts, width, height,"
                        " status, hint_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
                        (
                            upload.page_id,
                            document_id,
                            key,
                            info.ext,
                            upload.session_id,
                            upload.seq,
                            timestamps.iso(captured),
                            captured.timestamp(),
                            timestamps.iso(uploaded),
                            uploaded.timestamp(),
                            info.width,
                            info.height,
                            upload.hint_number,
                        ),
                    )
                    self._touch(document_id)
                    self._refresh_layout(document_id)
            finally:
                self._storing.discard(upload.page_id)
        self._assembly.schedule(document_id)
        self._work_queued()
        return self.require_page(upload.page_id), True

    @staticmethod
    def _same_document(page: PageRecord, document_id: str) -> PageRecord:
        if page.document_id != document_id:
            raise Conflict("page_id already used by another document")
        return page

    def _free_key(self, document_id: str, captured: datetime, page_id: str) -> str:
        for key in propose_page_keys(captured, page_id):
            clash = self._db.one("SELECT 1 FROM pages WHERE document_id = ? AND key = ?", (document_id, key))
            if clash is None:
                return key
        raise Conflict("page key already in use")

    def _store_scan(self, slug: str, key: str, ext: str, data: bytes, page_id: str, thumbnail: bytes) -> None:
        self._files.write_scan(slug, key, ext, data)
        atomic_write(self._thumb_path(page_id), thumbnail)

    async def patch_page(self, page_id: str, changes: PageChanges) -> PageRecord:
        """Apply user corrections; a new rotation re-queues the page for OCR."""
        page = self.require_page(page_id)
        rotate = changes.rotation is not None and changes.rotation != page.rotation
        if rotate:
            assert changes.rotation is not None
            await self._rotate_thumbnail(page, changes.rotation)
        values: dict[str, object] = {}
        if changes.manual_number is not UNCHANGED:
            values["manual_number"] = changes.manual_number
        if changes.excluded is not None:
            values["excluded"] = int(changes.excluded)
        if rotate:
            values["rotation"] = changes.rotation
        if values:
            with self._db.transaction():
                page = self.require_page(page_id)
                assignments = ", ".join(f"{name} = ?" for name in values)
                self._db.execute(
                    f"UPDATE pages SET {assignments} WHERE id = ?",  # noqa: S608 (column names from the code, values as ? parameters)
                    (*values.values(), page_id),
                )
                if rotate:
                    self._requeue(page_id)
                self._touch(page.document_id)
                self._refresh_layout(page.document_id)
            self._assembly.schedule(page.document_id)
            if rotate:
                self._work_queued()
        return self.require_page(page_id)

    async def _rotate_thumbnail(self, page: PageRecord, rotation: int) -> None:
        scan = self.scan_path(page, self.require_document(page.document_id))
        try:
            data = await asyncio.to_thread(images.make_thumbnail, scan, rotation)
        except (OSError, images.ImageRejected) as exc:
            log.warning("page %s: cannot redraw the thumbnail: %s", page.key, exc)
            return
        await asyncio.to_thread(atomic_write, self._thumb_path(page.id), data)

    def reprocess_page(self, page_id: str) -> PageRecord:
        """Queue the page for OCR again (its current outputs stay until replaced)."""
        with self._db.transaction():
            page = self.require_page(page_id)
            self._requeue(page_id)
            self._touch(page.document_id)
            self._refresh_layout(page.document_id)
        self._assembly.schedule(page.document_id)
        self._work_queued()
        return self.require_page(page_id)

    def _requeue(self, page_id: str) -> None:
        self._db.execute(
            "UPDATE pages SET status = 'queued', error = NULL, attempts = 0, generation = generation + 1 WHERE id = ?",
            (page_id,),
        )

    def reorder_pages(self, document_id: str, page_ids: Sequence[str]) -> DocumentRecord:
        """Put the pages of the reading order in the given order (PUT /api/documents/{id}/order).

        `page_ids` must be exactly the pages of the current reading order:
        otherwise the client worked on an outdated list (Conflict). Only the
        pages that moved get a position (ordering.positions_for_order).
        """
        with self._db.transaction():
            self.require_document(document_id)
            pages = {page.id: page for page in self._pages(document_id)}
            inputs = [page.ordering_input for page in pages.values()]
            layout = ordering.compute_layout(inputs)
            if len(set(page_ids)) != len(page_ids) or set(page_ids) != set(layout.reading_order):
                raise Conflict("page set changed")
            changes = [
                (position, page_id)
                for page_id, position in ordering.positions_for_order(inputs, page_ids).items()
                if position != pages[page_id].position
            ]
            for change in changes:
                self._db.execute("UPDATE pages SET position = ? WHERE id = ?", change)
            if changes:
                self._touch(document_id)
                self._refresh_layout(document_id)
        if changes:
            self._assembly.schedule(document_id)
        return self.require_document(document_id)

    def clear_page_order(self, document_id: str) -> DocumentRecord:
        """Forget the positions of the pages: back to the order of numbers and sessions."""
        with self._db.transaction():
            self.require_document(document_id)
            changed = self._db.execute(
                "UPDATE pages SET position = NULL WHERE document_id = ? AND position IS NOT NULL",
                (document_id,),
            ).rowcount
            if changed:
                self._touch(document_id)
                self._refresh_layout(document_id)
        if changed:
            self._assembly.schedule(document_id)
        return self.require_document(document_id)

    async def delete_page(self, page_id: str) -> bool:
        """Move the scan and OCR outputs of a page to the trash and forget the page."""
        page = self.get_page(page_id)
        if page is None:
            return False
        async with self._lock(page.document_id):
            page = self.get_page(page_id)
            if page is None:
                return False
            document = self.require_document(page.document_id)
            await asyncio.to_thread(self._files.trash_page, document.slug, page.key, page.scan_ext)
            with self._db.transaction():
                self._db.execute("DELETE FROM pages WHERE id = ?", (page_id,))
                self._touch(page.document_id)
                self._refresh_layout(page.document_id)
            await asyncio.to_thread(self._remove_thumbnails, [page_id])
        self._assembly.schedule(page.document_id)
        return True

    # -- OCR loop interface ----------------------------------------------------

    def claim_next_page(self) -> PageClaim | None:
        """Take the oldest queued page (FIFO by upload time) and mark it processing."""
        with self._db.transaction():
            row = self._db.one(
                "SELECT p.id, p.document_id, p.generation, p.attempts, p.key, p.scan_ext,"
                " p.rotation, d.slug, d.unwarp FROM pages p JOIN documents d ON d.id = p.document_id"
                " WHERE p.status = 'queued' ORDER BY p.uploaded_ts, p.id LIMIT 1"
            )
            if row is None:
                return None
            self._db.execute("UPDATE pages SET status = 'processing' WHERE id = ?", (row["id"],))
            self._refresh_layout(row["document_id"])
        return build_page_claim(row)

    def locate_claimed_scan(self, claim: PageClaim) -> Path:
        return self._files.scan_path(claim.slug, claim.key, claim.scan_ext)

    def release_page(self, claim: PageClaim) -> None:
        self._end_attempt(claim, conclude_released_attempt(claim.attempts))

    def fail_page(self, claim: PageClaim, message: str, *, retry: bool) -> bool:
        """Record a failed attempt; returns True if the page will be retried."""
        outcome = conclude_failed_attempt(claim.attempts, message, is_retryable=retry)
        self._end_attempt(claim, outcome)
        return outcome.status == "queued"

    def _end_attempt(self, claim: PageClaim, outcome: AttemptOutcome) -> None:
        with self._db.transaction():
            updated = self._db.execute(
                "UPDATE pages SET status = ?, attempts = ?, error = ?"
                " WHERE id = ? AND generation = ? AND status = 'processing'",
                (outcome.status, outcome.attempt_count, outcome.error, claim.page_id, claim.generation),
            ).rowcount
            if not updated:
                return
            if outcome.status == "error":
                self._touch(claim.document_id)
            self._refresh_layout(claim.document_id)
        if outcome.status == "error":
            self._assembly.schedule(claim.document_id)

    async def complete_page(self, claim: PageClaim, output: PageOcrOutput, duration_s: float) -> bool:
        """Store an OCR result; returns False if the page changed meanwhile (result dropped)."""
        async with self._lock(claim.document_id):
            page = self.get_page(claim.page_id)
            if page is None or page.generation != claim.generation or page.status != "processing":
                return False
            await asyncio.to_thread(
                self._files.write_page_outputs,
                claim.slug,
                claim.key,
                output.markdown,
                [(image.filename, image.data) for image in output.images],
                output.raw,
            )
            ocr = summarize_ocr(
                engine=output.engine,
                markdown=output.markdown,
                image_count=len(output.images),
                duration_seconds=duration_s,
                finished_at=clock.now(),
            )
            with self._db.transaction():
                updated = self._db.execute(
                    "UPDATE pages SET status = 'done', error = NULL, attempts = 0,"
                    " detected_numbers = ?, ocr = ?"
                    " WHERE id = ? AND generation = ? AND status = 'processing'",
                    (json.dumps(list(output.detected_numbers)), json.dumps(ocr), claim.page_id, claim.generation),
                ).rowcount
                if not updated:
                    return False
                self._touch(claim.document_id)
                self._refresh_layout(claim.document_id)
        self._assembly.schedule(claim.document_id)
        return True

    # -- layout and assembly ---------------------------------------------------

    def _pages(self, document_id: str) -> list[PageRecord]:
        rows = self._db.all("SELECT * FROM pages WHERE document_id = ?", (document_id,))
        return [build_page_record(row) for row in rows]

    def _refresh_layout(self, document_id: str) -> None:
        """Recompute numbering/order/coverage of a document and store it (in a transaction)."""
        rows = self._db.all("SELECT * FROM pages WHERE document_id = ?", (document_id,))
        inputs = [build_page_record(row).ordering_input for row in rows]
        layout = ordering.compute_layout(inputs)
        for row in rows:
            placement = layout.placements[row["id"]]
            number = placement.number
            values = (
                number.value if number else None,
                number.end if number else None,
                int(bool(number and number.front_matter)),
                placement.source,
                number.label if number else None,
                placement.duplicate_of,
                int(placement.in_document),
                placement.placed_by,
                placement.rank,
            )
            if values != tuple(row[column] for column in _LAYOUT_COLUMNS):
                assignments = ", ".join(f"{column} = ?" for column in _LAYOUT_COLUMNS)
                self._db.execute(
                    f"UPDATE pages SET {assignments} WHERE id = ?",  # noqa: S608 (column names from the code, values as ? parameters)
                    (*values, row["id"]),
                )
        summary = encode_layout_summary(summarize_layout(inputs, layout))
        self._db.execute("UPDATE documents SET layout = ? WHERE id = ?", (summary, document_id))

    async def _assemble(self, document_ids: set[str], index: bool) -> None:
        for document_id in sorted(document_ids):
            async with self._lock(document_id):
                document = self.get_document(document_id)
                if document is None:  # deleted meanwhile: its folder is in the trash
                    continue
                pages = self.list_pages(document_id)
                await asyncio.to_thread(self._publisher.write_document, document, pages)
        if index:
            await asyncio.to_thread(self._publisher.write_index, self.list_documents())
