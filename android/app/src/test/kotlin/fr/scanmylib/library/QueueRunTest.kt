package fr.scanmylib.library

import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.UploadState
import fr.scanmylib.expectFailure
import java.io.File
import java.time.Clock
import java.time.Instant
import java.time.ZoneId
import java.util.UUID
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class QueueRunTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val document = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
    private val clock = Clock.fixed(Instant.parse("2026-10-12T18:30:00Z"), ZoneId.of("+02:00"))

    private suspend fun run(staging: StagingArea, vararg shots: Pair<String, Instant>): List<StagedPage> = staging.add(
        document,
        shots.map { (content, at) ->
            StagingInput(staging.incomingFile(document).apply { writeText(content) }, at)
        },
    )

    @Test
    fun `a run becomes one session, in order, with capture times and page numbers`() = runTest {
        val staging = StagingArea(folder.newFolder("staging"))
        val scans = ScanFileStore(folder.newFolder("scans"))
        val pages = run(
            staging,
            "p1" to Instant.parse("2026-10-12T18:15:30.900Z"),
            "p2" to Instant.parse("2026-10-12T18:16:02Z"),
            "p3" to Instant.parse("2026-10-12T18:16:40Z"),
        )

        var queued = emptyList<PendingPageEntity>()
        val journal = staging.sendJournal(document)
        queueRun(document, pages, PageNumbering(firstPage = 12, consecutive = true), scans, clock, journal) {
            // The moves are on record until the pages are.
            assertTrue(journal.isFile)
            queued = it
        }

        assertEquals(listOf(1, 2, 3), queued.map { it.seq })
        assertEquals(1, queued.map { it.sessionId }.distinct().size)
        assertEquals(
            listOf("2026-10-12T20:15:30+02:00", "2026-10-12T20:16:02+02:00", "2026-10-12T20:16:40+02:00"),
            queued.map { it.capturedAt },
        )
        assertEquals(listOf(12, 13, 14), queued.map { it.pageNumberHint })
        assertTrue(queued.all { it.documentId == document && it.state == UploadState.QUEUED })
        assertTrue(queued.all { it.queuedAt == clock.millis() && it.attempts == 0 && it.failure == null })
        // The images moved to the scan store, untouched.
        assertEquals(queued.map { "${it.id}.jpg" }, queued.map { it.fileName })
        assertEquals(listOf("p1", "p2", "p3"), queued.map { scans.file(it.fileName!!).readText() })
        assertTrue(pages.none { it.file.exists() })
        assertFalse(journal.exists())
    }

    @Test
    fun `pages are numbered again without the gaps left by deleted photos`() = runTest {
        val staging = StagingArea(folder.newFolder("staging"))
        val shots = run(staging, "a" to clock.instant(), "deleted" to clock.instant(), "b" to clock.instant())
        staging.remove(document, shots[1])

        var queued = emptyList<PendingPageEntity>()
        val scans = ScanFileStore(folder.newFolder("scans"))
        val numbering = PageNumbering(null, consecutive = true)
        queueRun(document, staging.pages(document), numbering, scans, clock, staging.sendJournal(document)) {
            queued = it
        }
        assertEquals(listOf(1, 2), queued.map { it.seq })
        assertEquals(listOf(null, null), queued.map { it.pageNumberHint })
        assertEquals(listOf("a", "b"), queued.map { scans.file(it.fileName!!).readText() })
    }

    @Test
    fun `if the pages cannot be recorded, their images go back to the run`() = runTest {
        val staging = StagingArea(folder.newFolder("staging"))
        val scansDirectory = folder.newFolder("scans")
        val pages = run(staging, "p1" to clock.instant(), "p2" to clock.instant())
        val journal = staging.sendJournal(document)

        expectFailure<IllegalStateException> {
            queueRun(
                document,
                pages,
                PageNumbering(1, consecutive = true),
                ScanFileStore(scansDirectory),
                clock,
                journal,
            ) {
                throw IllegalStateException("database closed")
            }
        }
        assertEquals(listOf("p1", "p2"), pages.map { it.file.readText() })
        assertEquals(emptyList<File>(), scansDirectory.listFiles()?.toList())
        assertFalse(journal.exists())
    }

    /**
     * The state a process leaves when it dies while sending: the journal written, the first
     * [moved] pages in the scan store, nothing recorded yet.
     */
    private suspend fun interruptedSend(staging: StagingArea, scans: ScanFileStore, moved: Int): List<SentPage> {
        val pages = run(
            staging,
            "p1" to clock.instant(),
            "p2" to clock.instant().plusSeconds(2),
            "p3" to clock.instant(),
        )
        val sent = pages.map { SentPage(UUID.randomUUID().toString(), it.file.name) }
        writeSendJournal(staging.sendJournal(document), sent)
        pages.zip(sent).take(moved).forEach { (page, entry) -> scans.adopt(entry.pageId, page.file) }
        return sent
    }

    @Test
    fun `pages moved out of the run but never recorded go back to it`() = runTest {
        val root = folder.newFolder("staging")
        val scans = ScanFileStore(folder.newFolder("scans"))
        interruptedSend(StagingArea(root), scans, moved = 2)

        // The next process: reading the run first recovers the send.
        val recovered = StagingArea(root) { journal, runDirectory ->
            recoverInterruptedSend(journal, runDirectory, scans) { false }
        }
        assertEquals(listOf("p1", "p2", "p3"), recovered.pages(document).map { it.file.readText() })
        assertEquals(listOf(1, 2, 3), recovered.pages(document).map { it.seq })
        assertFalse(recovered.sendJournal(document).exists())
        assertEquals(emptyList<File>(), scans.file("x").parentFile?.listFiles()?.toList())
    }

    @Test
    fun `pages recorded before the process died stay in the upload queue`() = runTest {
        val root = folder.newFolder("staging")
        val scans = ScanFileStore(folder.newFolder("scans"))
        val sent = interruptedSend(StagingArea(root), scans, moved = 3)
        val recorded = sent.mapTo(HashSet()) { it.pageId }

        val recovered = StagingArea(root) { journal, runDirectory ->
            recoverInterruptedSend(journal, runDirectory, scans) { it in recorded }
        }
        assertTrue(recovered.pages(document).isEmpty())
        assertEquals(listOf("p1", "p2", "p3"), sent.map { scans.file(ScanFileStore.fileName(it.pageId)).readText() })
        assertFalse(recovered.sendJournal(document).exists())
    }

    @Test
    fun `the journal names files of the run, never paths`() {
        val journal = folder.newFile("sending")
        val pages = listOf(SentPage("a1b2", "00001_1760293530123.jpg"), SentPage("c3d4", "00002_1760293532000.jpg"))
        writeSendJournal(journal, pages)
        assertEquals(pages, readSendJournal(journal))

        journal.writeText("a1b2\t../../scans/x.jpg\n\tmissing\nonly-one-field\n..\t00001_1.jpg\n")
        assertEquals(emptyList<SentPage>(), readSendJournal(journal))
    }
}
