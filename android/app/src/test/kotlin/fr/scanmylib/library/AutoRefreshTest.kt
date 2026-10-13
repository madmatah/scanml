package fr.scanmylib.library

import fr.scanmylib.api.PageStatus
import fr.scanmylib.api.QueueCounts
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadState
import fr.scanmylib.model.DocumentKind
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AutoRefreshTest {

    /** Follows [work] as a visible screen does; returns the (virtual) times of the refreshes. */
    private fun TestScope.follow(work: Flow<PendingWork>, refresh: suspend () -> Boolean = { true }): List<Long> {
        val refreshes = mutableListOf<Long>()
        backgroundScope.launch {
            autoRefresh(work, AUTO_REFRESH_INTERVAL) {
                refreshes += currentTime
                refresh()
            }
        }
        return refreshes
    }

    @Test
    fun `pages sent from the document screen are shown from the PC as soon as they are uploaded`() = runTest {
        // The report: a book without pages yet, 25 pages from Google's scanner sent from its screen,
        // uploaded within 2 seconds and deleted from the phone once uploaded.
        val document = MutableStateFlow(book(pages = 0))
        val local = MutableStateFlow(List(25) { localPage("p$it") })
        val server = MutableStateFlow(emptyList<ServerPageEntity>())
        val work = combine(document, local, server) { document, local, server ->
            documentWork(document, DocumentPages.merge(local, server))
        }
        val refreshes = follow(work) {
            // As LibraryRepository.refreshDocument: the PC lists the pages uploaded before the
            // request, queued for OCR, and the phone forgets them.
            val uploaded = local.value.filter { it.state == UploadState.UPLOADED }
            delay(150)
            server.value += uploaded.mapIndexed { position, page -> serverPage(page.id, position) }
            document.value = book(pages = server.value.size, queued = server.value.size)
            local.value -= uploaded.toSet()
            true
        }

        for (page in local.value.map { it.id }) {
            advanceTimeBy(80)
            local.value = local.value.map {
                if (it.id == page) it.copy(state = UploadState.UPLOADED, fileName = null) else it
            }
        }
        // Until the PC lists them, the uploaded pages show the PC's thumbnails, not empty boxes.
        assertTrue(local.value.all { it.serverThumbUrl() == "/api/pages/${it.id}/thumb" })

        runCurrent()
        assertEquals("one refresh, once the last page is uploaded", listOf(2_000L), refreshes)
        advanceTimeBy(151)
        val pages = DocumentPages.merge(local.value, server.value)
        assertEquals(emptyList<PendingPageEntity>(), pages.local)
        assertEquals(25, pages.server.size)
        assertEquals(25, document.value.server?.pages)

        // The PC processes them: followed every 5 seconds.
        advanceTimeBy(5_000)
        assertEquals(listOf(2_000L, 7_150L), refreshes)
    }

    @Test
    fun `the processing on the PC is followed every 5 seconds until it is over`() = runTest {
        val work = MutableStateFlow(PendingWork(processing = true))
        var refreshesLeft = 3
        val refreshes = follow(work) {
            delay(100)
            if (--refreshesLeft == 0) work.value = PendingWork(processing = false)
            true
        }
        advanceTimeBy(10.minutes.inWholeMilliseconds)
        assertEquals(listOf(5_000L, 10_100L, 15_200L), refreshes)
    }

    @Test
    fun `work over meanwhile is not refreshed`() = runTest {
        // The user pulled to refresh as the PC was done.
        val work = MutableStateFlow(PendingWork(processing = true))
        val refreshes = follow(work)
        advanceTimeBy(2_000)
        work.value = PendingWork()
        advanceTimeBy(10.minutes.inWholeMilliseconds)
        assertEquals(emptyList<Long>(), refreshes)
    }

    @Test
    fun `a long upload is refreshed every 5 seconds, and once over`() = runTest {
        val work = MutableStateFlow(PendingWork(uploading = true))
        val refreshes = follow(work) {
            delay(100)
            true
        }
        val uploaded = mutableSetOf<String>()
        for (page in 1..20) {
            advanceTimeBy(700)
            uploaded += "p$page"
            work.value = PendingWork(uploaded.toSet(), uploading = page < 20)
        }
        runCurrent()
        // Not a refresh per page: the progress every 5 seconds, then the whole upload.
        assertEquals(listOf(5_700L, 11_300L, 14_000L), refreshes)
    }

    @Test
    fun `pages uploaded while a refresh is under way get another one`() = runTest {
        val work = MutableStateFlow(PendingWork(uploaded = setOf("p1")))
        val refreshes = follow(work) {
            delay(300)
            true
        }
        advanceTimeBy(100)
        // Maybe too late for the PC's answer.
        work.value = PendingWork(uploaded = setOf("p1", "p2"))
        advanceTimeBy(1.minutes.inWholeMilliseconds)
        assertEquals(listOf(0L, 300L), refreshes)
    }

    @Test
    fun `uploaded pages that the PC does not list are not refreshed again and again`() = runTest {
        // Deleted on the PC: with "Keep scans on the phone", the phone keeps them as uploaded.
        val work = MutableStateFlow(PendingWork(uploaded = setOf("deleted-on-the-pc")))
        val refreshes = follow(work)
        advanceTimeBy(1.minutes.inWholeMilliseconds)
        work.value = PendingWork(uploaded = setOf("deleted-on-the-pc", "new"))
        advanceTimeBy(1.minutes.inWholeMilliseconds)
        assertEquals(listOf(0L, 60_000L), refreshes)
    }

    @Test
    fun `failed refreshes are tried again less and less often, up to every minute`() = runTest {
        val work = MutableStateFlow(PendingWork(processing = true))
        var reachable = false
        val refreshes = follow(work) { reachable }
        advanceTimeBy(200_000)
        assertEquals(listOf(5_000L, 15_000L, 35_000L, 75_000L, 135_000L, 195_000L), refreshes)

        // The PC is back: every 5 seconds again.
        reachable = true
        advanceTimeBy(70_000)
        assertEquals(listOf(255_000L, 260_000L, 265_000L), refreshes.drop(6))
    }

    @Test
    fun `after a failure, uploads wait for the next try`() = runTest {
        val work = MutableStateFlow(PendingWork(uploaded = setOf("p1")))
        var reachable = false
        val refreshes = follow(work) { reachable }
        advanceTimeBy(1_000)
        reachable = true
        work.value = PendingWork(uploaded = setOf("p1", "p2"))
        advanceTimeBy(1.minutes.inWholeMilliseconds)
        assertEquals(listOf(0L, 10_000L), refreshes)
    }

    @Test
    fun `after failures, work over meanwhile starts afresh`() = runTest {
        val work = MutableStateFlow(PendingWork(processing = true))
        var reachable = false
        val refreshes = follow(work) { reachable }
        advanceTimeBy(40_000) // failed at 5, 15 and 35 s: the next try would be at 75 s
        // The PC is on again: the user pulls to refresh, and the PC is done.
        reachable = true
        work.value = PendingWork()
        advanceTimeBy(1_000)
        // Pages uploaded: refreshed right away, without the wait of the failures.
        work.value = PendingWork(uploaded = setOf("p1"))
        advanceTimeBy(1.minutes.inWholeMilliseconds)
        assertEquals(listOf(5_000L, 15_000L, 35_000L, 41_000L), refreshes)
    }

    @Test
    fun `nothing is refreshed while nothing is in progress`() = runTest {
        // Pages waiting on the phone (PC switched off): nothing new to show until one is uploaded.
        val refreshes = follow(MutableStateFlow(PendingWork(uploading = true)))
        advanceTimeBy(60.minutes.inWholeMilliseconds)
        assertEquals(emptyList<Long>(), refreshes)
    }

    @Test
    fun `refreshes stop with the screen`() = runTest {
        val refreshes = mutableListOf<Long>()
        val visible = backgroundScope.launch {
            autoRefresh(MutableStateFlow(PendingWork(processing = true)), AUTO_REFRESH_INTERVAL) {
                refreshes += currentTime
                true
            }
        }
        advanceTimeBy(12_000)
        visible.cancel()
        advanceTimeBy(10.minutes.inWholeMilliseconds)
        assertEquals(listOf(5_000L, 10_000L), refreshes)
    }

    @Test
    fun `waits double after each failure, up to a minute`() {
        assertEquals(5.seconds, autoRefreshDelay(5.seconds, failures = 0))
        assertEquals(10.seconds, autoRefreshDelay(5.seconds, failures = 1))
        assertEquals(40.seconds, autoRefreshDelay(5.seconds, failures = 3))
        assertEquals(1.minutes, autoRefreshDelay(5.seconds, failures = 4))
        assertEquals(1.minutes, autoRefreshDelay(5.seconds, failures = Int.MAX_VALUE))
    }

    @Test
    fun `the document screen follows its uploads and the processing of its pages`() {
        val pages = DocumentPages.merge(
            local = listOf(
                localPage("listed", UploadState.UPLOADED, fileName = null),
                localPage("unlisted", UploadState.UPLOADED, fileName = null),
                localPage("refused", UploadState.FAILED),
            ),
            server = listOf(serverPage("listed", 0)),
        )
        assertEquals(PendingWork(uploaded = setOf("unlisted")), documentWork(book(pages = 1, done = 1), pages))

        for (state in listOf(UploadState.QUEUED, UploadState.UPLOADING)) {
            val uploading = DocumentPages.merge(listOf(localPage("p", state)), emptyList())
            assertEquals(PendingWork(uploading = true), documentWork(book(pages = 1, done = 1), uploading))
        }
        assertTrue(documentWork(book(pages = 2, done = 1, queued = 1), DocumentPages.EMPTY).processing)
        assertTrue(documentWork(book(pages = 2, done = 1, processing = 1), DocumentPages.EMPTY).processing)
        // Not on the PC yet, or deleted: nothing to follow there.
        assertFalse(documentWork(book(pages = 0).copy(server = null), DocumentPages.EMPTY).processing)
        assertEquals(PendingWork(), documentWork(null, DocumentPages.EMPTY))
    }

    @Test
    fun `the library follows every upload, its documents and the PC's queue`() {
        val idle = listOf(LibraryRow(book(pages = 3, done = 3), pagesToUpload = 0, failedPages = 1))
        assertEquals(PendingWork(), libraryWork(idle, emptyList(), QueueCounts()))
        assertEquals(PendingWork(uploaded = setOf("p1")), libraryWork(idle, listOf("p1"), QueueCounts()))

        val uploading = listOf(LibraryRow(book(pages = 3, done = 3), pagesToUpload = 2, failedPages = 0))
        assertEquals(PendingWork(uploading = true), libraryWork(uploading, emptyList(), QueueCounts()))

        // Pages of a document not cached yet, or processed again from the web UI.
        assertTrue(libraryWork(idle, emptyList(), QueueCounts(queued = 1)).processing)
        assertTrue(libraryWork(idle, emptyList(), QueueCounts(processing = 1)).processing)
        // The PC's queue unknown (unreachable when last asked): the documents still tell.
        val processing = listOf(LibraryRow(book(pages = 3, done = 2, processing = 1), 0, 0))
        assertTrue(libraryWork(processing, emptyList(), queue = null).processing)
        assertFalse(libraryWork(idle, emptyList(), queue = null).processing)
    }

    private fun book(pages: Int, done: Int = 0, queued: Int = 0, processing: Int = 0) = DocumentEntity(
        id = DOCUMENT,
        title = "Example Book",
        author = "",
        kind = DocumentKind.BOOK,
        unwarp = true,
        updatedAt = 0,
        needsUpload = false,
        uploadError = null,
        confirmedAt = 0,
        server = ServerDocumentState(
            pages = pages, done = done, queued = queued, processing = processing, errors = 0, excluded = 0,
            duplicates = 0, coverage = "", missing = "", unnumbered = 0, coverThumbUrl = null, folder = "",
        ),
    )

    private fun localPage(id: String, state: UploadState = UploadState.QUEUED, fileName: String? = "$id.jpg") =
        PendingPageEntity(
            id = id,
            documentId = DOCUMENT,
            sessionId = "session",
            seq = 1,
            capturedAt = "2026-10-13T12:28:30+02:00",
            pageNumberHint = null,
            fileName = fileName,
            state = state,
            failure = null,
            lastError = null,
            attempts = 0,
            queuedAt = 0,
        )

    private fun serverPage(id: String, position: Int) = ServerPageEntity(
        id = id,
        documentId = DOCUMENT,
        position = position,
        status = PageStatus.QUEUED,
        error = null,
        pageLabel = null,
        numberSource = null,
        excluded = false,
        duplicate = false,
        thumbUrl = "/api/pages/$id/thumb",
    )

    private companion object {
        const val DOCUMENT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
    }
}
