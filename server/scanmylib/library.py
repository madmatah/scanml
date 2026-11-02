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
import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import PurePath

from .adapters.sqlite.database import Database
from .application.catalog import Catalog, NewPage, QueueCounts
from .application.clock import Clock
from .application.library_files import LibraryFiles
from .application.ocr_engine import PageOcrOutput
from .application.scan_images import ImageRejected, ScanImages
from .application.thumbnails import Thumbnails
from .config import Settings
from .debounce import DebouncedBatch
from .domain import ordering
from .domain.documents import check_document_changes, prepare_new_document, propose_slugs, summarize_layout
from .domain.pages import (
    AttemptOutcome,
    conclude_failed_attempt,
    conclude_released_attempt,
    propose_page_keys,
    summarize_ocr,
)
from .domain.records import (
    Conflict,
    DocumentChanges,
    DocumentRecord,
    NotFound,
    PageChanges,
    PageClaim,
    PageRecord,
    PageUpload,
)
from .publisher import Publisher

log = logging.getLogger(__name__)


class LibraryService:
    def __init__(
        self,
        settings: Settings,
        catalog: Catalog,
        db: Database,
        files: LibraryFiles,
        thumbnails: Thumbnails,
        publisher: Publisher,
        clock: Clock,
        scan_images: ScanImages,
    ) -> None:
        self._settings = settings
        self._catalog = catalog
        self._db = db
        self._files = files
        self._thumbnails = thumbnails
        self._clock = clock
        self._scan_images = scan_images
        self._publisher = publisher
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
        self._files.prepare()
        self._thumbnails.prepare()
        with self._catalog.open_transaction():
            requeued_count = self._catalog.requeue_interrupted_pages()
            document_ids = self._catalog.list_document_ids()
            for document_id in document_ids:
                self._refresh_layout(document_id)
        self._assembly.start()
        for document_id in document_ids:
            self._assembly.schedule(document_id)
        self._assembly.schedule()
        return requeued_count

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
        return self._catalog.list_documents()

    def get_document(self, document_id: str) -> DocumentRecord | None:
        return self._catalog.get_document(document_id)

    def require_document(self, document_id: str) -> DocumentRecord:
        document = self.get_document(document_id)
        if document is None:
            raise NotFound("document not found")
        return document

    def list_pages(self, document_id: str) -> list[PageRecord]:
        """Pages of a document in the API order (reading order first)."""
        return self._catalog.list_pages(document_id)

    def get_page(self, page_id: str) -> PageRecord | None:
        return self._catalog.get_page(page_id)

    def require_page(self, page_id: str) -> PageRecord:
        page = self.get_page(page_id)
        if page is None:
            raise NotFound("page not found")
        return page

    def count_queue(self) -> QueueCounts:
        return self._catalog.count_queue()

    def folder(self, document: DocumentRecord) -> str:
        """Host path of a document folder (display only)."""
        return f"{self._settings.library_host_path.rstrip('/')}/{document.slug}"

    def scan_path(self, page: PageRecord, document: DocumentRecord) -> PurePath:
        return self._files.locate_scan(document.slug, page.key, page.scan_ext)

    async def thumbnail(self, page: PageRecord) -> PurePath:
        if not await asyncio.to_thread(self._thumbnails.is_stored, page.id):
            scan = self.scan_path(page, self.require_document(page.document_id))
            thumbnail = await asyncio.to_thread(self._scan_images.make_thumbnail, scan, page.rotation)
            await asyncio.to_thread(self._thumbnails.store, page.id, thumbnail)
        return self._thumbnails.locate(page.id)

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
        if not await asyncio.to_thread(self._files.has_document_markdown, document.slug):
            self._assembly.schedule(document.id)
            await self._assembly.flush(document.id)
        return await asyncio.to_thread(self._files.read_document_markdown, document.slug)

    def document_file(self, document: DocumentRecord, relative: str) -> PurePath | None:
        return self._files.resolve_document_file(document.slug, relative)

    async def export_entries(self, document: DocumentRecord, include_scans: bool) -> Sequence[tuple[str, PurePath]]:
        await self._assembly.flush(document.id)
        return await asyncio.to_thread(self._files.export_entries, document.slug, include_scans)

    # -- documents -----------------------------------------------------------

    async def put_document(self, document_id: str, changes: DocumentChanges) -> tuple[DocumentRecord, bool]:
        """Create the document, or update it if it exists. Returns (document, created)."""
        async with self._lock(document_id):
            if self.get_document(document_id) is not None:  # checked under the lock: retries race
                return self.update_document(document_id, changes), False
            new_document = prepare_new_document(changes)
            moment = self._clock.now()
            with self._catalog.open_transaction():
                slug = self._free_slug(new_document.title)
                self._catalog.add_document(document_id, slug, new_document, moment)
                self._refresh_layout(document_id)
            await asyncio.to_thread(self._files.create_folder, slug)
        self._assembly.schedule(document_id)
        return self.require_document(document_id), True

    def update_document(self, document_id: str, changes: DocumentChanges) -> DocumentRecord:
        self.require_document(document_id)
        check_document_changes(changes)
        if changes != DocumentChanges():
            with self._catalog.open_transaction():
                self._catalog.update_document(document_id, changes)
                self._touch(document_id)
            self._assembly.schedule(document_id)
        return self.require_document(document_id)

    async def delete_document(self, document_id: str) -> bool:
        """Move the document folder to the trash and forget the document."""
        async with self._lock(document_id):
            document = self.get_document(document_id)
            if document is None:
                return False
            page_ids = self._catalog.list_page_ids(document_id)
            trashed = await asyncio.to_thread(self._files.trash_document, document.slug)
            with self._catalog.open_transaction():
                self._catalog.remove_document(document_id)
            await asyncio.to_thread(self._thumbnails.remove, page_ids)
        log.info("document %s deleted, folder moved to %s", document.slug, trashed)
        self._assembly.schedule()
        return True

    def _free_slug(self, title: str) -> str:
        return next(
            slug
            for slug in propose_slugs(title)
            if not self._catalog.is_slug_taken(slug) and not self._files.has_folder(slug)
        )

    def _touch(self, document_id: str) -> None:
        self._catalog.touch_document(document_id, self._clock.now())

    # -- pages ---------------------------------------------------------------

    async def add_page(self, document_id: str, upload: PageUpload) -> tuple[PageRecord, bool]:
        """Store an uploaded scan and queue it. Returns (page, created); idempotent on page id."""
        self.require_document(document_id)
        existing = self.get_page(upload.page_id)
        if existing is not None:
            return self._same_document(existing, document_id), False
        info, thumbnail = await asyncio.to_thread(self._scan_images.ingest_scan, upload.data)
        captured = upload.captured_at or self._clock.now()
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
                uploaded = self._clock.now()
                with self._catalog.open_transaction():
                    self._catalog.add_page(
                        NewPage(
                            id=upload.page_id,
                            document_id=document_id,
                            key=key,
                            scan=info,
                            session_id=upload.session_id,
                            seq=upload.seq,
                            hint_number=upload.hint_number,
                            captured_at=captured,
                            uploaded_at=uploaded,
                        )
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
            if not self._catalog.is_key_taken(document_id, key):
                return key
        raise Conflict("page key already in use")

    def _store_scan(self, slug: str, key: str, ext: str, data: bytes, page_id: str, thumbnail: bytes) -> None:
        self._files.write_scan(slug, key, ext, data)
        self._thumbnails.store(page_id, thumbnail)

    async def patch_page(self, page_id: str, changes: PageChanges) -> PageRecord:
        """Apply user corrections; a new rotation re-queues the page for OCR."""
        page = self.require_page(page_id)
        rotate = changes.rotation is not None and changes.rotation != page.rotation
        if rotate:
            assert changes.rotation is not None
            await self._rotate_thumbnail(page, changes.rotation)
        changes_to_store = replace(changes, rotation=changes.rotation if rotate else None)
        if changes_to_store != PageChanges():
            with self._catalog.open_transaction():
                page = self.require_page(page_id)
                self._catalog.update_page(page_id, changes_to_store)
                if rotate:
                    self._catalog.requeue_page(page_id)
                self._touch(page.document_id)
                self._refresh_layout(page.document_id)
            self._assembly.schedule(page.document_id)
            if rotate:
                self._work_queued()
        return self.require_page(page_id)

    async def _rotate_thumbnail(self, page: PageRecord, rotation: int) -> None:
        scan = self.scan_path(page, self.require_document(page.document_id))
        try:
            thumbnail = await asyncio.to_thread(self._scan_images.make_thumbnail, scan, rotation)
        except (OSError, ImageRejected) as exc:
            log.warning("page %s: cannot redraw the thumbnail: %s", page.key, exc)
            return
        await asyncio.to_thread(self._thumbnails.store, page.id, thumbnail)

    def reprocess_page(self, page_id: str) -> PageRecord:
        """Queue the page for OCR again (its current outputs stay until replaced)."""
        with self._catalog.open_transaction():
            page = self.require_page(page_id)
            self._catalog.requeue_page(page_id)
            self._touch(page.document_id)
            self._refresh_layout(page.document_id)
        self._assembly.schedule(page.document_id)
        self._work_queued()
        return self.require_page(page_id)

    def reorder_pages(self, document_id: str, page_ids: Sequence[str]) -> DocumentRecord:
        """Put the pages of the reading order in the given order (PUT /api/documents/{id}/order).

        `page_ids` must be exactly the pages of the current reading order:
        otherwise the client worked on an outdated list (Conflict). Only the
        pages that moved get a position (ordering.positions_for_order).
        """
        with self._catalog.open_transaction():
            self.require_document(document_id)
            pages = {page.id: page for page in self._catalog.list_pages(document_id)}
            inputs = [page.ordering_input for page in pages.values()]
            layout = ordering.compute_layout(inputs)
            if len(set(page_ids)) != len(page_ids) or set(page_ids) != set(layout.reading_order):
                raise Conflict("page set changed")
            moved_positions = {
                page_id: position
                for page_id, position in ordering.positions_for_order(inputs, page_ids).items()
                if position != pages[page_id].position
            }
            if moved_positions:
                self._catalog.set_page_positions(moved_positions)
                self._touch(document_id)
                self._refresh_layout(document_id)
        if moved_positions:
            self._assembly.schedule(document_id)
        return self.require_document(document_id)

    def clear_page_order(self, document_id: str) -> DocumentRecord:
        """Forget the positions of the pages: back to the order of numbers and sessions."""
        with self._catalog.open_transaction():
            self.require_document(document_id)
            cleared_count = self._catalog.clear_page_positions(document_id)
            if cleared_count:
                self._touch(document_id)
                self._refresh_layout(document_id)
        if cleared_count:
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
            with self._catalog.open_transaction():
                self._catalog.remove_page(page_id)
                self._touch(page.document_id)
                self._refresh_layout(page.document_id)
            await asyncio.to_thread(self._thumbnails.remove, [page_id])
        self._assembly.schedule(page.document_id)
        return True

    # -- OCR loop interface ----------------------------------------------------

    def claim_next_page(self) -> PageClaim | None:
        with self._catalog.open_transaction():
            claim = self._catalog.claim_next_page()
            if claim is None:
                return None
            self._refresh_layout(claim.document_id)
        return claim

    def locate_claimed_scan(self, claim: PageClaim) -> PurePath:
        return self._files.locate_scan(claim.slug, claim.key, claim.scan_ext)

    def release_page(self, claim: PageClaim) -> None:
        self._end_attempt(claim, conclude_released_attempt(claim.attempts))

    def fail_page(self, claim: PageClaim, message: str, *, retry: bool) -> bool:
        """Record a failed attempt; returns True if the page will be retried."""
        outcome = conclude_failed_attempt(claim.attempts, message, is_retryable=retry)
        self._end_attempt(claim, outcome)
        return outcome.status == "queued"

    def _end_attempt(self, claim: PageClaim, outcome: AttemptOutcome) -> None:
        with self._catalog.open_transaction():
            if not self._catalog.end_attempt(claim, outcome):
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
                finished_at=self._clock.now(),
            )
            with self._catalog.open_transaction():
                if not self._catalog.complete_page(claim, output.detected_numbers, ocr):
                    return False
                self._touch(claim.document_id)
                self._refresh_layout(claim.document_id)
        self._assembly.schedule(claim.document_id)
        return True

    # -- layout and assembly ---------------------------------------------------

    def _refresh_layout(self, document_id: str) -> None:
        """Recompute numbering/order/coverage of a document and store it (in a transaction)."""
        inputs = [page.ordering_input for page in self._catalog.list_pages(document_id)]
        layout = ordering.compute_layout(inputs)
        self._catalog.store_layout(document_id, layout.placements, summarize_layout(inputs, layout))

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
