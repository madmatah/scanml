package fr.scanmylib.library

import fr.scanmylib.expectFailure
import java.io.File
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class StagingAreaTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val document = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
    private val otherDocument = "0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d"
    private val shotTime = Instant.parse("2026-10-12T18:15:30.123Z")

    private val root get() = File(folder.root, "staging")

    /** A staging area on the same files, as after the process was killed and started again. */
    private fun staging() = StagingArea(root)

    /** An image written in a new incoming file, as by the camera or a copy. */
    private suspend fun StagingArea.image(content: String, documentId: String = document): File =
        incomingFile(documentId).apply { writeText(content) }

    private suspend fun StagingArea.shoot(content: String, at: Instant, documentId: String = document) =
        add(documentId, listOf(StagingInput(image(content, documentId), at))).single()

    @Test
    fun `pages join the run in order, numbered from 1`() = runTest {
        val staging = staging()
        val added = staging.add(
            document,
            listOf(StagingInput(staging.image("a"), shotTime), StagingInput(staging.image("b"), shotTime.plusSeconds(4))),
        )
        assertEquals(listOf(1, 2), added.map { it.seq })
        assertEquals(3, staging.shoot("c", shotTime.plusSeconds(9)).seq)

        val run = staging.observe(document).first()
        assertEquals(listOf(1, 2, 3), run.map { it.seq })
        assertEquals(listOf("a", "b", "c"), run.map { it.file.readText() })
        assertEquals(run, staging.pages(document))
        assertTrue(staging.pages(otherDocument).isEmpty())
    }

    @Test
    fun `a run survives the process, with the capture time of each page`() = runTest {
        val staging = staging()
        staging.shoot("a", shotTime)
        staging.shoot("b", shotTime.plusMillis(1_500))

        val restarted = staging()
        val run = restarted.pages(document)
        assertEquals(listOf(1, 2), run.map { it.seq })
        assertEquals(listOf(shotTime, shotTime.plusMillis(1_500)), run.map { it.capturedAt })
        assertEquals(listOf("a", "b"), run.map { it.file.readText() })
        // The next photo comes after them.
        assertEquals(3, restarted.shoot("c", shotTime.plusSeconds(3)).seq)
    }

    @Test
    fun `an unfinished shot is not a page, and the next process deletes it`() = runTest {
        val staging = staging()
        staging.shoot("a", shotTime)
        val unfinished = staging.image("half a photo")

        val restarted = staging()
        assertEquals(listOf("a"), restarted.pages(document).map { it.file.readText() })
        assertFalse(unfinished.exists())
    }

    @Test
    fun `images cut short by the end of the previous process are reported, once`() = runTest {
        val staging = staging()
        staging.shoot("a", shotTime)
        staging.image("half a photo")
        // In the same process, an image on its way is just on its way.
        assertFalse(staging.takeInterrupted(document))

        val restarted = staging()
        assertTrue(restarted.takeInterrupted(document))
        assertFalse(restarted.takeInterrupted(document))
        assertFalse(restarted.takeInterrupted(otherDocument))
        assertFalse(staging().takeInterrupted(document))
        assertEquals(listOf("a"), staging().pages(document).map { it.file.readText() })
    }

    @Test
    fun `incoming files are new files of the document's run`() = runTest {
        val staging = staging()
        val first = staging.incomingFile(document)
        val second = staging.incomingFile(document)
        assertTrue(first != second)
        assertFalse(first.exists())
        assertEquals(File(root, "$document/incoming"), first.parentFile)
    }

    @Test
    fun `a photo deleted during the run leaves a gap until the run is sent`() = runTest {
        val staging = staging()
        staging.shoot("a", shotTime)
        val blurred = staging.shoot("b", shotTime.plusSeconds(2))
        staging.shoot("c", shotTime.plusSeconds(4))

        staging.remove(document, blurred)
        assertFalse(blurred.file.exists())
        assertEquals(listOf(1, 3), staging.pages(document).map { it.seq })
        assertEquals(4, staging.shoot("d", shotTime.plusSeconds(6)).seq)
        assertEquals(listOf("a", "c", "d"), staging().pages(document).map { it.file.readText() })
    }

    @Test
    fun `retaking the last photo keeps the order`() = runTest {
        val staging = staging()
        staging.shoot("a", shotTime)
        staging.remove(document, staging.shoot("blurred b", shotTime.plusSeconds(2)))
        staging.shoot("b", shotTime.plusSeconds(5))
        assertEquals(listOf("a", "b"), staging().pages(document).map { it.file.readText() })
    }

    @Test
    fun `removing the pages after a position keeps the earlier ones`() = runTest {
        val staging = staging()
        staging.shoot("scanned 1", shotTime)
        staging.shoot("scanned 2", shotTime.plusSeconds(1))
        staging.shoot("photo 1", shotTime.plusSeconds(2))
        staging.shoot("photo 2", shotTime.plusSeconds(3))

        staging.removeAfter(document, 2)
        assertEquals(listOf("scanned 1", "scanned 2"), staging.pages(document).map { it.file.readText() })
        assertEquals(listOf("scanned 1", "scanned 2"), staging().pages(document).map { it.file.readText() })
        // Nothing after the last page: nothing to remove.
        staging.removeAfter(document, 2)
        assertEquals(2, staging.pages(document).size)
        assertEquals(3, staging.shoot("next", shotTime.plusSeconds(4)).seq)
    }

    @Test
    fun `discarding a run deletes its photos`() = runTest {
        val staging = staging()
        val pages = listOf(staging.shoot("a", shotTime), staging.shoot("b", shotTime))
        staging.shoot("other", shotTime, otherDocument)

        staging.discard(document)
        assertTrue(staging.pages(document).isEmpty())
        assertTrue(pages.none { it.file.exists() })
        assertTrue(staging().pages(document).isEmpty())
        assertEquals(1, staging().pages(otherDocument).size)
        // A new run starts from 1.
        assertEquals(1, staging.shoot("c", shotTime).seq)
    }

    @Test
    fun `sending hands every page over, then the run is gone`() = runTest {
        val staging = staging()
        staging.shoot("a", shotTime)
        staging.shoot("b", shotTime)
        val outbox = folder.newFolder("outbox")

        val sent = staging.send(document) { run ->
            run.forEach { assertTrue(it.file.renameTo(File(outbox, it.file.name))) }
            run.size
        }
        assertEquals(2, sent)
        assertTrue(staging.pages(document).isEmpty())
        assertFalse(File(root, document).exists())
        assertTrue(staging().pages(document).isEmpty())
        assertEquals(2, outbox.list()?.size)
    }

    @Test
    fun `a failed send leaves the run as it was`() = runTest {
        val staging = staging()
        val pages = listOf(staging.shoot("a", shotTime), staging.shoot("b", shotTime))

        expectFailure<IOException> { staging.send(document) { throw IOException("database full") } }
        assertEquals(pages, staging.pages(document))
        assertTrue(pages.all { it.file.exists() })
    }

    @Test
    fun `a send that moved only some pages keeps the others in the run`() = runTest {
        val staging = staging()
        val (first, second) = listOf(staging.shoot("a", shotTime), staging.shoot("b", shotTime))
        val outbox = folder.newFolder("outbox")

        expectFailure<IOException> {
            staging.send(document) {
                assertTrue(first.file.renameTo(File(outbox, first.file.name)))
                throw IOException("interrupted")
            }
        }
        assertEquals(listOf(second), staging.pages(document))
    }

    @Test
    fun `the runs of deleted documents are dropped`() = runTest {
        val staging = staging()
        staging.shoot("kept", shotTime)
        val dropped = staging.shoot("dropped", shotTime, otherDocument)

        staging.retainRuns { setOf(document) }
        assertTrue(staging.pages(otherDocument).isEmpty())
        assertFalse(dropped.file.exists())
        assertEquals(listOf("kept"), staging.pages(document).map { it.file.readText() })
    }

    @Test
    fun `the library learns which documents have pages waiting, those of earlier processes too`() = runTest {
        staging().shoot("a", shotTime)
        staging().shoot("b", shotTime, otherDocument)
        staging().remove(otherDocument, staging().pages(otherDocument).single())

        // A new process: nothing read yet.
        val staging = staging()
        var seen = emptySet<String>()
        staging.retainRuns { withPages ->
            seen = withPages
            setOf(document, otherDocument)
        }
        assertEquals(setOf(document), seen)
        assertEquals(setOf(document), staging().documentsWithPages())
        assertEquals(mapOf(document to 1), staging().observeRunSizes().first())
    }

    @Test
    fun `run sizes follow the pages`() = runTest {
        val staging = staging()
        staging.shoot("a", shotTime)
        assertEquals(mapOf(document to 1), staging.observeRunSizes().first())
        staging.shoot("b", shotTime, otherDocument)
        staging.shoot("c", shotTime, otherDocument)
        assertEquals(mapOf(document to 1, otherDocument to 2), staging.observeRunSizes().first())
        staging.discard(otherDocument)
        assertEquals(mapOf(document to 1), staging.observeRunSizes().first())
    }

    @Test
    fun `a send left unfinished is recovered before the run is read, once per process`() = runTest {
        staging().shoot("a", shotTime)
        val journal = staging().sendJournal(document).apply { writeText("journal") }
        val recovered = mutableListOf<File>()
        val staging = StagingArea(root) { found, runDirectory ->
            assertEquals(File(root, document), runDirectory)
            recovered += found
            found.delete()
        }
        assertEquals(listOf("a"), staging.pages(document).map { it.file.readText() })
        staging.shoot("b", shotTime)
        assertEquals(listOf(journal), recovered)
        // The journal is not a page.
        assertEquals(2, staging().pages(document).size)
    }

    @Test
    fun `an empty image is not a page`() = runTest {
        val staging = staging()
        val empty = staging.incomingFile(document).apply { createNewFile() }
        expectFailure<IOException> { staging.add(document, listOf(StagingInput(empty, shotTime))) }
        assertTrue(staging.pages(document).isEmpty())
    }

    @Test
    fun `document ids cannot point outside the staging area`() = runTest {
        expectFailure<IllegalArgumentException> { staging().incomingFile("../scans") }
        expectFailure<IllegalArgumentException> { staging().pages("") }
    }

    @Test
    fun `file names hold the position and the capture time`() {
        val name = StagingArea.fileName(12, shotTime)
        assertEquals("00012_${shotTime.toEpochMilli()}.jpg", name)
        val page = StagingArea.parseFileName(File(root, name))
        assertEquals(12, page?.seq)
        assertEquals(shotTime, page?.capturedAt)

        assertNull(StagingArea.parseFileName(File("incoming")))
        assertNull(StagingArea.parseFileName(File("00000_1760293530123.jpg")))
        assertNull(StagingArea.parseFileName(File("00012_1760293530123.jpg.tmp")))
        assertNull(StagingArea.parseFileName(File("12_abc.jpg")))
    }
}
