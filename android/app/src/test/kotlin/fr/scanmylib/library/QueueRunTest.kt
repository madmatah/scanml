package fr.scanmylib.library

import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.UploadState
import java.io.File
import java.time.Clock
import java.time.Instant
import java.time.ZoneId
import kotlin.properties.Delegates
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class QueueRunTest {
    @RunWith(Enclosed::class)
    class TheQueueRunFunction {
        class WhenARunIsSent {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var queued: List<PendingPageEntity>
            private lateinit var scanContents: List<String?>
            private lateinit var pagesLeftInTheRun: List<StagedPage>
            private var hadTheJournalWhileRecording by Delegates.notNull<Boolean>()
            private var hasTheJournal by Delegates.notNull<Boolean>()

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(folder.newFolder("staging"))
                val scans = ScanFileStore(folder.newFolder("scans"))
                val pages = stageRun(
                    staging,
                    "p1" to Instant.parse("2026-10-12T18:15:30.900Z"),
                    "p2" to Instant.parse("2026-10-12T18:16:02Z"),
                    "p3" to Instant.parse("2026-10-12T18:16:40Z"),
                )
                staging.numberPage(DOCUMENT, pages[0], FIRST_PAGE, nextPagesFollowOn = true)
                val numberedPages = staging.pages(DOCUMENT)
                val journal = staging.sendJournal(DOCUMENT)
                queueRun(DOCUMENT, numberedPages, scans, CLOCK, journal) {
                    hadTheJournalWhileRecording = journal.isFile
                    queued = it
                }
                scanContents = queued.map { page -> page.fileName?.let { scans.file(it).readText() } }
                pagesLeftInTheRun = numberedPages.filter { it.file.exists() }
                hasTheJournal = journal.exists()
            }

            @Test
            fun `should number the pages from 1, in the order of the run`() {
                assertEquals(listOf(1, 2, 3), queued.map { it.seq })
            }

            @Test
            fun `should record them as one session`() {
                assertEquals(1, queued.map { it.sessionId }.distinct().size)
            }

            @Test
            fun `should date them at their capture time, to the second, in the phone's time zone`() {
                assertEquals(
                    listOf("2026-10-12T20:15:30+02:00", "2026-10-12T20:16:02+02:00", "2026-10-12T20:16:40+02:00"),
                    queued.map { it.capturedAt },
                )
            }

            @Test
            fun `should hint their page numbers on from the first page's`() {
                assertEquals(listOf(12, 13, 14), queued.map { it.pageNumberHint })
            }

            @Test
            fun `should queue them for upload to their document`() {
                assertEquals(List(3) { DOCUMENT to UploadState.QUEUED }, queued.map { it.documentId to it.state })
            }

            @Test
            fun `should queue them at the time of the send`() {
                assertEquals(List(3) { CLOCK.millis() }, queued.map { it.queuedAt })
            }

            @Test
            fun `should queue them as never tried`() {
                assertEquals(List(3) { 0 }, queued.map { it.attempts })
                assertEquals(List(3) { null }, queued.map { it.failure })
            }

            @Test
            fun `should name each image after its page`() {
                assertEquals(queued.map { "${it.id}.jpg" }, queued.map { it.fileName })
            }

            @Test
            fun `should move the images to the scan store, untouched`() {
                assertEquals(listOf("p1", "p2", "p3"), scanContents)
            }

            @Test
            fun `should leave no image in the run`() {
                assertEquals(emptyList<StagedPage>(), pagesLeftInTheRun)
            }

            @Test
            fun `should keep the moves on record until the pages are recorded`() {
                assertTrue(hadTheJournalWhileRecording)
            }

            @Test
            fun `should delete the record of the moves once the pages are recorded`() {
                assertFalse(hasTheJournal)
            }
        }

        class WhenAPhotoWasDeletedFromTheRun {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var queued: List<PendingPageEntity>
            private lateinit var scanContents: List<String?>

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(folder.newFolder("staging"))
                val shots = stageRun(
                    staging,
                    "a" to CLOCK.instant(),
                    "deleted" to CLOCK.instant(),
                    "b" to CLOCK.instant(),
                )
                staging.delete(DOCUMENT, shots[1])
                val scans = ScanFileStore(folder.newFolder("scans"))
                queueRun(DOCUMENT, staging.pages(DOCUMENT), scans, CLOCK, staging.sendJournal(DOCUMENT)) {
                    queued = it
                }
                scanContents = queued.map { page -> page.fileName?.let { scans.file(it).readText() } }
            }

            @Test
            fun `should number the pages again, without the gap the photo left`() {
                assertEquals(listOf(1, 2), queued.map { it.seq })
            }

            @Test
            fun `should hint no page number, since none was given`() {
                assertEquals(listOf(null, null), queued.map { it.pageNumberHint })
            }

            @Test
            fun `should move the images of the pages left`() {
                assertEquals(listOf("a", "b"), scanContents)
            }
        }

        class WhenARunNumberedPageByPageIsSent {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var queued: List<PendingPageEntity>

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(folder.newFolder("staging"))
                val scans = ScanFileStore(folder.newFolder("scans"))
                val pages = stageRun(
                    staging,
                    "p1" to CLOCK.instant(),
                    "p2" to CLOCK.instant(),
                    "p3" to CLOCK.instant(),
                    "p4" to CLOCK.instant(),
                )
                staging.numberPage(DOCUMENT, pages[0], NUMBER_GIVEN_WITH_THE_NEXT_PAGES, nextPagesFollowOn = true)
                staging.numberPage(DOCUMENT, pages[2], null, nextPagesFollowOn = true)
                staging.numberPage(DOCUMENT, pages[3], NUMBER_GIVEN_ALONE, nextPagesFollowOn = false)
                queueRun(DOCUMENT, staging.pages(DOCUMENT), scans, CLOCK, staging.sendJournal(DOCUMENT)) {
                    queued = it
                }
            }

            @Test
            fun `should hint each page with the number given, following on, or none`() {
                assertEquals(listOf(32, 33, null, 40), queued.map { it.pageNumberHint })
            }

            companion object {
                private const val NUMBER_GIVEN_WITH_THE_NEXT_PAGES = 32
                private const val NUMBER_GIVEN_ALONE = 40
            }
        }

        class WhenThePagesCannotBeRecorded {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var sendTheRun: suspend () -> Unit

            @Before
            fun keepTheSend() = runTest {
                val staging = StagingArea(folder.newFolder("staging"))
                val scans = ScanFileStore(folder.newFolder("scans"))
                val pages = stageRun(staging, "p1" to CLOCK.instant(), "p2" to CLOCK.instant())
                val journal = staging.sendJournal(DOCUMENT)
                sendTheRun = { queueRun(DOCUMENT, pages, scans, CLOCK, journal, recordInAClosedDatabase) }
            }

            @Test
            fun `should fail with the error of the database`() = runTest {
                val failure = runCatching { sendTheRun() }.exceptionOrNull()
                assertTrue("$failure", failure is IllegalStateException)
                assertEquals(DATABASE_CLOSED, failure?.message)
            }
        }

        class WhenThePagesCannotBeRecordedAndTheSendIsOver {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var runContents: List<String>
            private lateinit var scanStoreListing: ScanStoreListing
            private var hasTheJournal by Delegates.notNull<Boolean>()

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(folder.newFolder("staging"))
                val scansDirectory = folder.newFolder("scans")
                val pages = stageRun(staging, "p1" to CLOCK.instant(), "p2" to CLOCK.instant())
                val journal = staging.sendJournal(DOCUMENT)
                runCatching {
                    val scans = ScanFileStore(scansDirectory)
                    queueRun(DOCUMENT, pages, scans, CLOCK, journal, recordInAClosedDatabase)
                }
                runContents = pages.map { it.file.readText() }
                scanStoreListing = ScanStoreListing(scansDirectory.listFiles()?.toList())
                hasTheJournal = journal.exists()
            }

            @Test
            fun `should put their images back in the run`() {
                assertEquals(listOf("p1", "p2"), runContents)
            }

            @Test
            fun `should leave no image in the scan store`() {
                assertEquals(emptyList<File>(), scanStoreListing.files)
            }

            @Test
            fun `should delete the record of the moves`() {
                assertFalse(hasTheJournal)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheRecoverInterruptedSendFunction {
        class WhenTheProcessDiedBeforeThePagesWereRecorded {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var runContents: List<String>
            private lateinit var positions: List<Int>
            private lateinit var scanStoreListing: ScanStoreListing
            private var hasTheJournal by Delegates.notNull<Boolean>()

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val root = folder.newFolder("staging")
                val scansDirectory = folder.newFolder("scans")
                val scans = ScanFileStore(scansDirectory)
                dieWhileSendingAfterMoving(StagingArea(root), scans, movedCount = 2)
                val recovered = startANextProcessThatRecoversSends(root, scans) { false }
                val pages = recovered.pages(DOCUMENT)
                runContents = pages.map { it.file.readText() }
                positions = pages.map { it.seq }
                scanStoreListing = ScanStoreListing(scansDirectory.listFiles()?.toList())
                hasTheJournal = recovered.sendJournal(DOCUMENT).exists()
            }

            @Test
            fun `should put the pages moved out of the run back in it`() {
                assertEquals(listOf("p1", "p2", "p3"), runContents)
            }

            @Test
            fun `should put them back at their positions`() {
                assertEquals(listOf(1, 2, 3), positions)
            }

            @Test
            fun `should leave no image in the scan store`() {
                assertEquals(emptyList<File>(), scanStoreListing.files)
            }

            @Test
            fun `should delete the record of the moves`() {
                assertFalse(hasTheJournal)
            }
        }

        class WhenTheProcessDiedBeforeNumberedPagesWereRecorded {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var numberings: List<PageNumbering>

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val root = folder.newFolder("staging")
                val scans = ScanFileStore(folder.newFolder("scans"))
                dieWhileSendingNumberedPages(StagingArea(root), scans)
                val recovered = startANextProcessThatRecoversSends(root, scans) { false }
                numberings = recovered.pages(DOCUMENT).map { it.numbering }
            }

            @Test
            fun `should put them back with their numbers`() {
                val expected = listOf(
                    PageNumbering.Given(FIRST_PAGE, nextPagesFollowOn = true),
                    PageNumbering.NotGiven,
                    PageNumbering.Cleared,
                )
                assertEquals(expected, numberings)
            }
        }

        class WhenThePagesWereRecordedBeforeTheProcessDied {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var scanContents: List<String>
            private var hasTheJournal by Delegates.notNull<Boolean>()

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val root = folder.newFolder("staging")
                val scans = ScanFileStore(folder.newFolder("scans"))
                val sent = dieWhileSendingAfterMoving(StagingArea(root), scans, movedCount = 3)
                val recorded = sent.mapTo(HashSet()) { it.pageId }
                val recovered = startANextProcessThatRecoversSends(root, scans) { it in recorded }
                stagedPages = recovered.pages(DOCUMENT)
                scanContents = sent.map { scans.file(ScanFileStore.fileName(it.pageId)).readText() }
                hasTheJournal = recovered.sendJournal(DOCUMENT).exists()
            }

            @Test
            fun `should leave them in the upload queue, out of the run`() {
                assertEquals(emptyList<StagedPage>(), stagedPages)
            }

            @Test
            fun `should keep their images in the scan store`() {
                assertEquals(listOf("p1", "p2", "p3"), scanContents)
            }

            @Test
            fun `should delete the record of the moves`() {
                assertFalse(hasTheJournal)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheReadSendJournalFunction {
        class WhenTheJournalWasWritten {
            @get:Rule
            val folder = TemporaryFolder()

            private val sentPages = listOf(
                SentPage("a1b2", "00001_1760293530123.jpg"),
                SentPage("c3d4", "00002_1760293532000.jpg"),
            )

            private lateinit var journalPages: List<SentPage>

            @Before
            fun writeAndReadTheJournal() {
                val journal = folder.newFile("sending")
                writeSendJournal(journal, sentPages)
                journalPages = readSendJournal(journal)
            }

            @Test
            fun `should read the pages it names`() {
                assertEquals(sentPages, journalPages)
            }
        }

        class WhenTheJournalNamesNumberedPages {
            @get:Rule
            val folder = TemporaryFolder()

            private val sentPages = listOf(
                SentPage("a1b2", "00001_1760293530123_h12c.jpg"),
                SentPage("c3d4", "00002_1760293532000_n.jpg"),
            )

            private lateinit var journalPages: List<SentPage>

            @Before
            fun writeAndReadTheJournal() {
                val journal = folder.newFile("sending")
                writeSendJournal(journal, sentPages)
                journalPages = readSendJournal(journal)
            }

            @Test
            fun `should read their names whole, so that a page sent back to the run keeps its number`() {
                assertEquals(sentPages, journalPages)
            }
        }

        @RunWith(Parameterized::class)
        class WhenALineNamesAPathOrIsCutShort(private val line: String, private val content: String) {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var journalPages: List<SentPage>

            @Before
            fun readTheJournal() {
                val journal = folder.newFile("sending").apply { writeText(content) }
                journalPages = readSendJournal(journal)
            }

            @Test
            fun `should skip it, so that the journal names files of the run, never paths`() {
                assertEquals(line, emptyList<SentPage>(), journalPages)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun lines(): List<Array<Any>> = listOf(
                    arrayOf("a staged name that is a path", "a1b2\t../../scans/x.jpg\n"),
                    arrayOf("a line without a page id", "\tmissing\n"),
                    arrayOf("a line of one field", "only-one-field\n"),
                    arrayOf("a page id that is a path", "..\t00001_1.jpg\n"),
                )
            }
        }
    }
}

private const val DOCUMENT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
private const val DATABASE_CLOSED = "database closed"
private const val FIRST_PAGE = 12
private val CLOCK: Clock = Clock.fixed(Instant.parse("2026-10-12T18:30:00Z"), ZoneId.of("+02:00"))

private suspend fun stageRun(staging: StagingArea, vararg shots: Pair<String, Instant>): List<StagedPage> = staging.add(
    DOCUMENT,
    shots.map { (content, at) -> StagingInput(staging.incomingFile(DOCUMENT).apply { writeText(content) }, at) },
)

/** A listing that may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class ScanStoreListing(val files: List<File>?)

private val recordInAClosedDatabase: suspend (List<PendingPageEntity>) -> Unit = {
    throw IllegalStateException(DATABASE_CLOSED)
}

private suspend fun stageThreeShots(staging: StagingArea): List<StagedPage> = stageRun(
    staging,
    "p1" to CLOCK.instant(),
    "p2" to CLOCK.instant().plusSeconds(2),
    "p3" to CLOCK.instant(),
)

private suspend fun dieWhileSendingAfterMoving(
    staging: StagingArea,
    scans: ScanFileStore,
    movedCount: Int,
): List<SentPage> = dieWhileSending(staging, scans, stageThreeShots(staging), movedCount)

private suspend fun dieWhileSendingNumberedPages(staging: StagingArea, scans: ScanFileStore): List<SentPage> {
    val shots = stageThreeShots(staging)
    staging.numberPage(DOCUMENT, shots[0], FIRST_PAGE, nextPagesFollowOn = true)
    staging.numberPage(DOCUMENT, shots[2], null, nextPagesFollowOn = true)
    return dieWhileSending(staging, scans, staging.pages(DOCUMENT), movedCount = shots.size)
}

private fun dieWhileSending(
    staging: StagingArea,
    scans: ScanFileStore,
    pages: List<StagedPage>,
    movedCount: Int,
): List<SentPage> {
    val sent = pages.mapIndexed { index, page -> SentPage("page-${index + 1}", page.file.name) }
    writeSendJournal(staging.sendJournal(DOCUMENT), sent)
    pages.zip(sent).take(movedCount).forEach { (page, entry) -> scans.adopt(entry.pageId, page.file) }
    return sent
}

private fun startANextProcessThatRecoversSends(
    root: File,
    scans: ScanFileStore,
    isRecorded: suspend (pageId: String) -> Boolean,
) = StagingArea(root) { journal, runDirectory -> recoverInterruptedSend(journal, runDirectory, scans, isRecorded) }
