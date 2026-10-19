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
import kotlin.properties.Delegates
import kotlin.time.Duration
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
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class AutoRefreshTest {
    @OptIn(ExperimentalCoroutinesApi::class)
    @RunWith(Enclosed::class)
    class TheAutoRefreshFunction {
        class WhenTheDocumentScreenUploadsItsPages {
            private lateinit var thumbnailUrls: List<String?>
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun uploadThePages() = runTest {
                val screen = openTheScreenOfABookWithScansToUpload()
                uploadEveryPageAndDeleteItsCopy(screen)
                thumbnailUrls = screen.local.value.map { it.serverThumbUrl() }
                refreshTimesMilliseconds = screen.refreshTimesMilliseconds.toList()
            }

            @Test
            fun `should show the PC's thumbnails of the uploaded pages until the PC lists them, not empty boxes`() {
                assertEquals(List(SCANNED_PAGE_COUNT) { "/api/pages/p$it/thumb" }, thumbnailUrls)
            }

            @Test
            fun `should refresh once, as soon as the last page is uploaded`() {
                assertEquals(listOf(2_000L), refreshTimesMilliseconds)
            }
        }

        class WhenTheDocumentScreenUploadsItsPagesAndThePcListsThem {
            private lateinit var pages: DocumentPages
            private lateinit var pcPageCount: PcPageCount

            @Before
            fun letThePcListThePages() = runTest {
                val screen = openTheScreenOfABookWithScansToUpload()
                uploadEveryPageAndDeleteItsCopy(screen)
                letThePcAnswer()
                pages = DocumentPages.merge(screen.local.value, screen.server.value)
                pcPageCount = PcPageCount(screen.document.value.server?.pages)
            }

            @Test
            fun `should no longer show a page from the phone`() {
                assertEquals(emptyList<PendingPageEntity>(), pages.local)
            }

            @Test
            fun `should show every page from the PC`() {
                assertEquals(SCANNED_PAGE_COUNT, pages.server.size)
            }

            @Test
            fun `should show the PC's count of the document's pages`() {
                assertEquals(SCANNED_PAGE_COUNT, pcPageCount.count)
            }
        }

        class WhenTheDocumentScreenUploadsItsPagesAndThePcListsThenProcessesThem {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun letThePcProcessThePages() = runTest {
                val screen = openTheScreenOfABookWithScansToUpload()
                uploadEveryPageAndDeleteItsCopy(screen)
                letThePcAnswer()
                advanceTimeBy(5_000)
                refreshTimesMilliseconds = screen.refreshTimesMilliseconds.toList()
            }

            @Test
            fun `should follow the processing every 5 seconds`() {
                assertEquals(listOf(2_000L, 7_150L), refreshTimesMilliseconds)
            }
        }

        class WhenThePcProcessesPages {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun followTheProcessing() = runTest {
                val work = MutableStateFlow(PendingWork(processing = true))
                var refreshCount = 0
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work) {
                    delay(100)
                    refreshCount++
                    work.value = PendingWork(processing = refreshCount < 3)
                    true
                }
                advanceTimeBy(10.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should refresh every 5 seconds until the processing is over`() {
                assertEquals(listOf(5_000L, 10_100L, 15_200L), refreshTimesMilliseconds)
            }
        }

        class WhenTheWorkIsOverBeforeTheFirstRefresh {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun endTheWork() = runTest {
                val work = MutableStateFlow(PendingWork(processing = true))
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work)
                advanceTimeBy(2_000)
                pullToRefreshAsThePcIsDone(work)
                advanceTimeBy(10.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should not refresh`() {
                assertEquals(emptyList<Long>(), refreshTimesMilliseconds)
            }
        }

        class WhenALongUploadIsUnderWay {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun uploadTwentyPages() = runTest {
                val work = MutableStateFlow(PendingWork(uploading = true))
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work) {
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
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should show its progress every 5 seconds, then the whole upload once over, not each page`() {
                assertEquals(listOf(5_700L, 11_300L, 14_000L), refreshTimesMilliseconds)
            }
        }

        class WhenPagesAreUploadedDuringARefresh {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun uploadDuringARefresh() = runTest {
                val work = MutableStateFlow(PendingWork(uploaded = setOf("p1")))
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work) {
                    delay(300)
                    true
                }
                advanceTimeBy(100)
                work.value = PendingWork(uploaded = setOf("p1", "p2"))
                advanceTimeBy(1.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should refresh again, since the refresh under way may have asked the PC too early`() {
                assertEquals(listOf(0L, 300L), refreshTimesMilliseconds)
            }
        }

        class WhenThePcDoesNotListUploadedPages {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun uploadMorePagesLater() = runTest {
                // Deleted on the PC: with "Keep scans on the phone", the phone keeps them as uploaded.
                val work = MutableStateFlow(PendingWork(uploaded = setOf("deleted-on-the-pc")))
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work)
                advanceTimeBy(1.minutes.inWholeMilliseconds)
                work.value = PendingWork(uploaded = setOf("deleted-on-the-pc", "new"))
                advanceTimeBy(1.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should not refresh them again and again, only for new uploads`() {
                assertEquals(listOf(0L, 60_000L), refreshTimesMilliseconds)
            }
        }

        class WhenRefreshesFail {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun failTheRefreshes() = runTest {
                refreshTimesMilliseconds = failTheRefreshesForAWhile().refreshTimesMilliseconds.toList()
            }

            @Test
            fun `should try again less and less often, up to every minute`() {
                assertEquals(listOf(5_000L, 15_000L, 35_000L, 75_000L, 135_000L, 195_000L), refreshTimesMilliseconds)
            }
        }

        class WhenRefreshesFailAndThePcIsBack {
            private lateinit var refreshTimesOnceBackMilliseconds: List<Long>

            @Before
            fun bringThePcBack() = runTest {
                val screen = failTheRefreshesForAWhile()
                val refreshCountBefore = screen.refreshTimesMilliseconds.size
                switchThePcOn(screen.pc)
                advanceTimeBy(70_000)
                refreshTimesOnceBackMilliseconds = screen.refreshTimesMilliseconds.drop(refreshCountBefore)
            }

            @Test
            fun `should refresh every 5 seconds again`() {
                assertEquals(listOf(255_000L, 260_000L, 265_000L), refreshTimesOnceBackMilliseconds)
            }
        }

        class WhenARefreshFailsAndPagesAreUploaded {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun uploadAfterAFailure() = runTest {
                val pc = Pc(isReachable = false)
                val work = MutableStateFlow(PendingWork(uploaded = setOf("p1")))
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work) { pc.isReachable }
                advanceTimeBy(1_000)
                switchThePcOn(pc)
                work.value = PendingWork(uploaded = setOf("p1", "p2"))
                advanceTimeBy(1.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should wait for the next try before refreshing the uploads`() {
                assertEquals(listOf(0L, 10_000L), refreshTimesMilliseconds)
            }
        }

        class WhenRefreshesFailedAndTheWorkIsOverMeanwhile {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun uploadOnceTheWorkIsOver() = runTest {
                val pc = Pc(isReachable = false)
                val work = MutableStateFlow(PendingWork(processing = true))
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work) { pc.isReachable }
                waitThroughThreeFailedRefreshesBeforeTheFourthTry()
                switchThePcOn(pc)
                pullToRefreshAsThePcIsDone(work)
                advanceTimeBy(1_000)
                work.value = PendingWork(uploaded = setOf("p1"))
                advanceTimeBy(1.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should refresh new uploads at once, without the wait of the failures`() {
                assertEquals(listOf(5_000L, 15_000L, 35_000L, 41_000L), refreshTimesMilliseconds)
            }
        }

        class WhenPagesWaitOnThePhoneWhileThePcIsOff {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun waitAnHour() = runTest {
                val work = MutableStateFlow(PendingWork(uploading = true))
                val observedRefreshTimesMilliseconds = followAsAVisibleScreen(work)
                advanceTimeBy(60.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should not refresh, since the PC has nothing new to show until a page is uploaded`() {
                assertEquals(emptyList<Long>(), refreshTimesMilliseconds)
            }
        }

        class WhenTheScreenCloses {
            private lateinit var refreshTimesMilliseconds: List<Long>

            @Before
            fun closeTheScreen() = runTest {
                val observedRefreshTimesMilliseconds = mutableListOf<Long>()
                val visible = backgroundScope.launch {
                    autoRefresh(MutableStateFlow(PendingWork(processing = true)), AUTO_REFRESH_INTERVAL) {
                        observedRefreshTimesMilliseconds += currentTime
                        true
                    }
                }
                advanceTimeBy(12_000)
                visible.cancel()
                advanceTimeBy(10.minutes.inWholeMilliseconds)
                refreshTimesMilliseconds = observedRefreshTimesMilliseconds.toList()
            }

            @Test
            fun `should stop refreshing`() {
                assertEquals(listOf(5_000L, 10_000L), refreshTimesMilliseconds)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheAutoRefreshDelayFunction {
        @RunWith(Parameterized::class)
        class WhenRefreshesFailedInARow(
            private val failures: String,
            private val failureCount: Int,
            private val expectedSeconds: Int,
        ) {
            private var wait by Delegates.notNull<Duration>()

            @Before
            fun computeTheWait() {
                wait = autoRefreshDelay(5.seconds, failureCount)
            }

            @Test
            fun `should wait twice as long after each failure, up to a minute`() {
                assertEquals(failures, expectedSeconds.seconds, wait)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun failures(): List<Array<Any>> = listOf(
                    arrayOf("none: the interval", 0, 5),
                    arrayOf("one: twice the interval", 1, 10),
                    arrayOf("three: eight times the interval", 3, 40),
                    arrayOf("four: a minute, not 80 seconds", 4, 60),
                    arrayOf("countless: a minute", Int.MAX_VALUE, 60),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDocumentWorkFunction {
        class WhenUploadedPagesAreNotListedYet {
            private lateinit var work: PendingWork

            @Before
            fun followTheDocument() {
                val pages = DocumentPages.merge(
                    local = listOf(
                        localPage("listed", UploadState.UPLOADED, fileName = null),
                        localPage("unlisted", UploadState.UPLOADED, fileName = null),
                        localPage("refused", UploadState.FAILED),
                    ),
                    server = listOf(serverPage("listed", 0)),
                )
                work = documentWork(book(pages = 1, done = 1), pages)
            }

            @Test
            fun `should follow only the uploaded pages the PC does not list yet`() {
                assertEquals(PendingWork(uploaded = setOf("unlisted")), work)
            }
        }

        @RunWith(Parameterized::class)
        class WhenAPageWaitsForUpload(private val page: String, private val state: UploadState) {
            private lateinit var work: PendingWork

            @Before
            fun followTheDocument() {
                val pages = DocumentPages.merge(listOf(localPage("p", state)), emptyList())
                work = documentWork(book(pages = 1, done = 1), pages)
            }

            @Test
            fun `should follow the upload`() {
                assertEquals(page, PendingWork(uploading = true), work)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun pages(): List<Array<Any>> = listOf(
                    arrayOf("a page queued", UploadState.QUEUED),
                    arrayOf("a page being uploaded", UploadState.UPLOADING),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenThePcProcessesPages(private val pages: String, private val document: DocumentEntity) {
            private var isProcessing by Delegates.notNull<Boolean>()

            @Before
            fun followTheDocument() {
                isProcessing = documentWork(document, DocumentPages.EMPTY).processing
            }

            @Test
            fun `should follow the processing`() {
                assertTrue(pages, isProcessing)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun documents(): List<Array<Any>> = listOf(
                    arrayOf("a page queued for OCR", book(pages = 2, done = 1, queued = 1)),
                    arrayOf("a page under OCR", book(pages = 2, done = 1, processing = 1)),
                )
            }
        }

        class WhenTheDocumentIsNotOnThePc {
            private var isProcessing by Delegates.notNull<Boolean>()

            @Before
            fun followTheDocument() {
                isProcessing = documentWork(book(pages = 0).copy(server = null), DocumentPages.EMPTY).processing
            }

            @Test
            fun `should follow no processing, since the PC has none of its pages yet, or no longer`() {
                assertFalse(isProcessing)
            }
        }

        class WhenTheDocumentIsGone {
            private lateinit var work: PendingWork

            @Before
            fun followNoDocument() {
                work = documentWork(null, DocumentPages.EMPTY)
            }

            @Test
            fun `should follow nothing`() {
                assertEquals(PendingWork(), work)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheLibraryWorkFunction {
        class WhenNothingIsInProgress {
            private lateinit var work: PendingWork

            @Before
            fun followTheLibrary() {
                work = libraryWork(IDLE_LIBRARY, emptyList(), QueueCounts())
            }

            @Test
            fun `should follow nothing, failed pages included`() {
                assertEquals(PendingWork(), work)
            }
        }

        class WhenPagesWereUploadedButAreNotListedYet {
            private lateinit var work: PendingWork

            @Before
            fun followTheLibrary() {
                work = libraryWork(IDLE_LIBRARY, listOf("p1"), QueueCounts())
            }

            @Test
            fun `should follow those pages`() {
                assertEquals(PendingWork(uploaded = setOf("p1")), work)
            }
        }

        class WhenPagesWaitForUpload {
            private lateinit var work: PendingWork

            @Before
            fun followTheLibrary() {
                val uploading = listOf(LibraryRow(book(pages = 3, done = 3), pagesToUpload = 2, failedPages = 0))
                work = libraryWork(uploading, emptyList(), QueueCounts())
            }

            @Test
            fun `should follow the upload`() {
                assertEquals(PendingWork(uploading = true), work)
            }
        }

        @RunWith(Parameterized::class)
        class WhenThePcsQueueHasPages(private val queue: String, private val queueCounts: QueueCounts) {
            private var isProcessing by Delegates.notNull<Boolean>()

            @Before
            fun followTheLibrary() {
                isProcessing = libraryWork(IDLE_LIBRARY, emptyList(), queueCounts).processing
            }

            @Test
            fun `should follow the processing, even of a document not cached yet or processed again from the web UI`() {
                assertTrue(queue, isProcessing)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun queues(): List<Array<Any>> = listOf(
                    arrayOf("a page queued for OCR", QueueCounts(queued = 1)),
                    arrayOf("a page under OCR", QueueCounts(processing = 1)),
                )
            }
        }

        class WhenThePcsQueueIsUnknownAndADocumentIsProcessed {
            private var isProcessing by Delegates.notNull<Boolean>()

            @Before
            fun followTheLibrary() {
                val processing = listOf(LibraryRow(book(pages = 3, done = 2, processing = 1), 0, 0))
                isProcessing = libraryWork(processing, emptyList(), queue = null).processing
            }

            @Test
            fun `should follow the processing the documents tell, the PC unreachable when last asked`() {
                assertTrue(isProcessing)
            }
        }

        class WhenThePcsQueueIsUnknownAndNoDocumentIsProcessed {
            private var isProcessing by Delegates.notNull<Boolean>()

            @Before
            fun followTheLibrary() {
                isProcessing = libraryWork(IDLE_LIBRARY, emptyList(), queue = null).processing
            }

            @Test
            fun `should follow no processing`() {
                assertFalse(isProcessing)
            }
        }
    }
}

private const val DOCUMENT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
private const val SCANNED_PAGE_COUNT = 25
private const val UPLOAD_INTERVAL_MILLISECONDS = 80L
private const val PC_ANSWER_MILLISECONDS = 150L

private val IDLE_LIBRARY = listOf(LibraryRow(book(pages = 3, done = 3), pagesToUpload = 0, failedPages = 1))

private class Pc(var isReachable: Boolean)

/** A page count that may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class PcPageCount(val count: Int?)

private class DocumentScreen(
    val document: MutableStateFlow<DocumentEntity>,
    val local: MutableStateFlow<List<PendingPageEntity>>,
    val server: MutableStateFlow<List<ServerPageEntity>>,
    val refreshTimesMilliseconds: List<Long>,
)

private class ScreenWithAnUnreachablePc(val pc: Pc, val refreshTimesMilliseconds: List<Long>)

@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.followAsAVisibleScreen(
    work: Flow<PendingWork>,
    refresh: suspend () -> Boolean = { true },
): List<Long> {
    val refreshTimesMilliseconds = mutableListOf<Long>()
    backgroundScope.launch {
        autoRefresh(work, AUTO_REFRESH_INTERVAL) {
            refreshTimesMilliseconds += currentTime
            refresh()
        }
    }
    return refreshTimesMilliseconds
}

private fun TestScope.openTheScreenOfABookWithScansToUpload(): DocumentScreen {
    val document = MutableStateFlow(book(pages = 0))
    val local = MutableStateFlow(List(SCANNED_PAGE_COUNT) { localPage("p$it") })
    val server = MutableStateFlow(emptyList<ServerPageEntity>())
    val work = combine(document, local, server) { document, local, server ->
        documentWork(document, DocumentPages.merge(local, server))
    }
    val refreshTimesMilliseconds = followAsAVisibleScreen(work) {
        // As LibraryRepository.refreshDocument: the PC lists the pages uploaded before the
        // request, queued for OCR, and the phone forgets them.
        val uploaded = local.value.filter { it.state == UploadState.UPLOADED }
        delay(PC_ANSWER_MILLISECONDS)
        server.value += uploaded.mapIndexed { position, page -> serverPage(page.id, position) }
        document.value = book(pages = server.value.size, queued = server.value.size)
        local.value -= uploaded.toSet()
        true
    }
    return DocumentScreen(document, local, server, refreshTimesMilliseconds)
}

@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.uploadEveryPageAndDeleteItsCopy(screen: DocumentScreen) {
    for (page in screen.local.value.map { it.id }) {
        advanceTimeBy(UPLOAD_INTERVAL_MILLISECONDS)
        screen.local.value = screen.local.value.map {
            if (it.id == page) it.copy(state = UploadState.UPLOADED, fileName = null) else it
        }
    }
    runCurrent()
}

@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.letThePcAnswer() {
    advanceTimeBy(PC_ANSWER_MILLISECONDS + 1)
}

@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.failTheRefreshesForAWhile(): ScreenWithAnUnreachablePc {
    val pc = Pc(isReachable = false)
    val refreshTimesMilliseconds = followAsAVisibleScreen(MutableStateFlow(PendingWork(processing = true))) {
        pc.isReachable
    }
    advanceTimeBy(200_000)
    return ScreenWithAnUnreachablePc(pc, refreshTimesMilliseconds)
}

@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.waitThroughThreeFailedRefreshesBeforeTheFourthTry() {
    advanceTimeBy(40_000)
}

private fun switchThePcOn(pc: Pc) {
    pc.isReachable = true
}

private fun pullToRefreshAsThePcIsDone(work: MutableStateFlow<PendingWork>) {
    work.value = PendingWork()
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
