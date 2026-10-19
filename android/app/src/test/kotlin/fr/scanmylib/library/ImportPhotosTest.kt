package fr.scanmylib.library

import java.io.File
import java.io.FileNotFoundException
import java.io.IOException
import java.time.Instant
import kotlin.properties.Delegates
import kotlinx.coroutines.job
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class ImportPhotosTest {
    @RunWith(Enclosed::class)
    class TheImportPhotosFunction {
        class WhenSomePhotosCannotBeRead {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var importCounts: PhotoImportResult
            private lateinit var pageContents: List<String>
            private lateinit var captureTimes: List<Instant>
            private lateinit var leftovers: Leftovers

            @Before
            fun importThePhotos() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                importCounts = importInto(
                    staging,
                    listOf(
                        PickedPhoto("page 2", at(20)),
                        // Exceptions a content provider passes across the binder, not only IOException.
                        PickedPhoto("cloud only", providerError = IllegalStateException("not downloaded")),
                        PickedPhoto("page 1", at(10)),
                        PickedPhoto("deleted since", providerError = FileNotFoundException("no such photo")),
                        PickedPhoto("revoked", providerError = SecurityException("permission revoked")),
                    ),
                )
                val pages = staging.pages(DOCUMENT)
                pageContents = pages.map { it.file.readText() }
                captureTimes = pages.map { it.capturedAt }
                leftovers = listLeftovers(resolveStagingRoot(folder))
            }

            @Test
            fun `should import the others, and count the photos left out`() {
                assertEquals(PhotoImportResult(added = 2, unreadable = 3), importCounts)
            }

            @Test
            fun `should add the photos it imports in the order they were taken`() {
                assertEquals(listOf("page 1", "page 2"), pageContents)
            }

            @Test
            fun `should date each page at the time its photo was taken`() {
                assertEquals(listOf(at(10), at(20)), captureTimes)
            }

            @Test
            fun `should leave no copy behind`() {
                assertEquals(emptyList<File>(), leftovers.copies)
            }
        }

        class WhenTheServerWouldRefuseSomePhotos {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var importCounts: PhotoImportResult
            private lateinit var pageContents: List<String>
            private lateinit var captureTimes: List<Instant>
            private lateinit var leftovers: Leftovers

            @Before
            fun importThePhotos() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val rejections = mapOf(
                    "heic" to PhotoRejection.UNSUPPORTED_FORMAT,
                    "gif" to PhotoRejection.UNSUPPORTED_FORMAT,
                    "panorama" to PhotoRejection.TOO_LARGE,
                )
                importCounts = importInto(
                    staging,
                    listOf(PickedPhoto("heic"), PickedPhoto("page"), PickedPhoto("panorama"), PickedPhoto("gif")),
                    check = { file -> rejections[file.readText()] },
                )
                val pages = staging.pages(DOCUMENT)
                pageContents = pages.map { it.file.readText() }
                captureTimes = pages.map { it.capturedAt }
                leftovers = listLeftovers(resolveStagingRoot(folder))
            }

            @Test
            fun `should leave them out, and count them by reason`() {
                assertEquals(PhotoImportResult(added = 1, unsupported = 2, tooLarge = 1), importCounts)
            }

            @Test
            fun `should add only the photo the server accepts`() {
                assertEquals(listOf("page"), pageContents)
            }

            @Test
            fun `should date a photo without a time at the time of the import`() {
                assertEquals(listOf(IMPORTED_AT), captureTimes)
            }

            @Test
            fun `should leave no copy behind`() {
                assertEquals(emptyList<File>(), leftovers.copies)
            }
        }

        class WhenNoPhotoCanBeRead {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var importThePhotos: suspend () -> PhotoImportResult

            @Before
            fun keepTheImport() {
                val staging = StagingArea(resolveStagingRoot(folder))
                val photos = listOf(PickedPhoto("a"), PickedPhoto("b"))
                importThePhotos = { importInto(staging, photos, copy = failForWantOfSpace) }
            }

            @Test
            fun `should fail with the cause, such as a full storage, rather than leave every photo out`() = runTest {
                val failure = runCatching { importThePhotos() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertEquals(NO_SPACE_LEFT, failure?.message)
            }
        }

        class WhenNoPhotoCanBeReadAndTheImportIsOver {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var leftovers: Leftovers

            @Before
            fun importThePhotos() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val photos = listOf(PickedPhoto("a"), PickedPhoto("b"))
                runCatching { importInto(staging, photos, copy = failForWantOfSpace) }
                stagedPages = staging.pages(DOCUMENT)
                leftovers = listLeftovers(resolveStagingRoot(folder))
            }

            @Test
            fun `should add no page`() {
                assertEquals(emptyList<StagedPage>(), stagedPages)
            }

            @Test
            fun `should leave no copy behind`() {
                assertEquals(emptyList<File>(), leftovers.copies)
            }
        }

        class WhenOnePhotoOfThreeCannotBeRead {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var progress: List<Int>

            @Before
            fun importThePhotos() = runTest {
                val reported = mutableListOf<Int>()
                importInto(
                    StagingArea(resolveStagingRoot(folder)),
                    listOf(
                        PickedPhoto("a"),
                        PickedPhoto("unreadable", providerError = IOException("gone")),
                        PickedPhoto("c"),
                    ),
                    onProgress = { reported += it },
                )
                progress = reported.toList()
            }

            @Test
            fun `should count every photo in the progress, imported or not`() {
                assertEquals(listOf(1, 2, 3), progress)
            }
        }

        class WhenTheImportIsCanceled {
            @get:Rule
            val folder = TemporaryFolder()

            private var isCanceled by Delegates.notNull<Boolean>()
            private lateinit var stagedPages: List<StagedPage>
            private lateinit var leftovers: Leftovers

            @Before
            fun cancelTheImport() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val photoCopiedAsTheUserCancels = "b"
                val importing = launch {
                    val importJob = coroutineContext.job
                    importInto(
                        staging,
                        listOf(PickedPhoto("a"), PickedPhoto(photoCopiedAsTheUserCancels), PickedPhoto("c")),
                        copy = { photo, target ->
                            target.writeText(photo.content)
                            if (photo.content == photoCopiedAsTheUserCancels) importJob.cancel()
                        },
                    )
                }
                importing.join()
                isCanceled = importing.isCancelled
                stagedPages = staging.pages(DOCUMENT)
                leftovers = listLeftovers(resolveStagingRoot(folder))
            }

            @Test
            fun `should end as canceled`() {
                assertTrue(isCanceled)
            }

            @Test
            fun `should add no page`() {
                assertEquals(emptyList<StagedPage>(), stagedPages)
            }

            @Test
            fun `should leave no copy behind`() {
                assertEquals(emptyList<File>(), leftovers.copies)
            }
        }
    }
}

private const val DOCUMENT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
private const val NO_SPACE_LEFT = "write failed: ENOSPC (No space left on device)"
private val IMPORTED_AT: Instant = Instant.parse("2026-10-12T18:30:00Z")

/** A listing that may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class Leftovers(val copies: List<File>?)

private data class PickedPhoto(val content: String, val takenAt: Instant? = null, val providerError: Exception? = null)

private fun at(seconds: Long): Instant = Instant.parse("2026-10-12T18:00:00Z").plusSeconds(seconds)

private fun resolveStagingRoot(folder: TemporaryFolder) = File(folder.root, "staging")

private fun listLeftovers(stagingRoot: File): Leftovers =
    Leftovers(File(stagingRoot, "$DOCUMENT/incoming").listFiles()?.toList())

private fun copyPhoto(photo: PickedPhoto, target: File) {
    photo.providerError?.let { throw it }
    target.writeText(photo.content)
}

private val failForWantOfSpace: suspend (PickedPhoto, File) -> Unit = { _, _ -> throw IOException(NO_SPACE_LEFT) }

private suspend fun importInto(
    staging: StagingArea,
    photos: List<PickedPhoto>,
    check: (File) -> PhotoRejection? = { null },
    onProgress: (Int) -> Unit = {},
    copy: suspend (PickedPhoto, File) -> Unit = ::copyPhoto,
): PhotoImportResult = importPhotos(
    documentId = DOCUMENT,
    photos = photos,
    staging = staging,
    importedAt = IMPORTED_AT,
    copy = copy,
    check = check,
    takenAt = { file -> photos.first { it.content == file.readText() }.takenAt },
    onProgress = onProgress,
)
