package fr.scanmylib.library

import fr.scanmylib.expectFailure
import java.io.File
import java.io.FileNotFoundException
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ImportPhotosTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val document = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
    private val importedAt = Instant.parse("2026-10-12T18:30:00Z")

    private val root get() = File(folder.root, "staging")

    private fun at(seconds: Long): Instant = Instant.parse("2026-10-12T18:00:00Z").plusSeconds(seconds)

    /** A photo chosen in the picker: its content and EXIF time, or the error its provider throws. */
    private data class Photo(val content: String, val takenAt: Instant? = null, val error: Exception? = null)

    private suspend fun import(
        staging: StagingArea,
        photos: List<Photo>,
        check: (File) -> PhotoRejection? = { null },
        onProgress: (Int) -> Unit = {},
        copy: (Photo, File) -> Unit = { photo, target ->
            photo.error?.let { throw it }
            target.writeText(photo.content)
        },
    ): PhotoImportResult = importPhotos(
        documentId = document,
        photos = photos,
        staging = staging,
        importedAt = importedAt,
        copy = copy,
        check = check,
        takenAt = { file -> photos.first { it.content == file.readText() }.takenAt },
        onProgress = onProgress,
    )

    private fun leftovers(): List<File> = File(root, "$document/incoming").listFiles().orEmpty().toList()

    @Test
    fun `an unreadable photo is left out, the others are imported in the order they were taken`() = runTest {
        val staging = StagingArea(root)
        val result = import(
            staging,
            listOf(
                Photo("page 2", at(20)),
                // Exceptions a content provider passes across the binder, not only IOException.
                Photo("cloud only", error = IllegalStateException("not downloaded")),
                Photo("page 1", at(10)),
                Photo("deleted since", error = FileNotFoundException("no such photo")),
                Photo("revoked", error = SecurityException("permission revoked")),
            ),
        )

        assertEquals(PhotoImportResult(added = 2, unreadable = 3), result)
        assertEquals(listOf("page 1", "page 2"), staging.pages(document).map { it.file.readText() })
        assertEquals(listOf(at(10), at(20)), staging.pages(document).map { it.capturedAt })
        assertEquals(emptyList<File>(), leftovers())
    }

    @Test
    fun `photos the server would refuse are left out and counted`() = runTest {
        val staging = StagingArea(root)
        val result = import(
            staging,
            listOf(Photo("heic"), Photo("page"), Photo("panorama"), Photo("gif")),
            check = { file ->
                when (file.readText()) {
                    "heic", "gif" -> PhotoRejection.UNSUPPORTED_FORMAT
                    "panorama" -> PhotoRejection.TOO_LARGE
                    else -> null
                }
            },
        )

        assertEquals(PhotoImportResult(added = 1, unsupported = 2, tooLarge = 1), result)
        // Undated: the time of the import.
        assertEquals(listOf("page" to importedAt), staging.pages(document).map { it.file.readText() to it.capturedAt })
        assertEquals(emptyList<File>(), leftovers())
    }

    @Test
    fun `when no photo can be read at all, the import fails with the cause and leaves nothing`() = runTest {
        val staging = StagingArea(root)
        val error = expectFailure<IOException> {
            import(
                staging,
                listOf(Photo("a"), Photo("b")),
                copy = { _, _ -> throw IOException("write failed: ENOSPC (No space left on device)") },
            )
        }
        assertTrue(error.message!!.contains("ENOSPC"))
        assertTrue(staging.pages(document).isEmpty())
        assertEquals(emptyList<File>(), leftovers())
    }

    @Test
    fun `the progress counts every photo, imported or not`() = runTest {
        val progress = mutableListOf<Int>()
        import(
            StagingArea(root),
            listOf(Photo("a"), Photo("unreadable", error = IOException("gone")), Photo("c")),
            onProgress = { progress += it },
        )
        assertEquals(listOf(1, 2, 3), progress)
    }

    @Test
    fun `a canceled import leaves nothing behind`() = runTest {
        val staging = StagingArea(root)
        lateinit var job: Job
        job = launch {
            import(
                staging,
                listOf(Photo("a"), Photo("b"), Photo("c")),
                copy = { photo, target ->
                    target.writeText(photo.content)
                    // The user cancels while the second photo is being copied.
                    if (photo.content == "b") job.cancel()
                },
            )
        }
        job.join()

        assertTrue(job.isCancelled)
        assertTrue(staging.pages(document).isEmpty())
        assertEquals(emptyList<File>(), leftovers())
    }
}
