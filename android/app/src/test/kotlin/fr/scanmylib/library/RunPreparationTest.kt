package fr.scanmylib.library

import java.io.File
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class RunPreparationTest {
    @RunWith(Enclosed::class)
    class TheStartMethod {
        class WhenACopyIsStarted {
            @get:Rule
            val folder = TemporaryFolder()

            private val imageCount = 3
            private lateinit var state: PreparationState

            @Before
            fun startACopy() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, imageCount) {
                    gate.await()
                    null
                }
                state = run.preparation.observe(DOCUMENT_ID).first()
                gate.complete(Unit)
            }

            @Test
            fun `should show it before it runs, so that the run never reads as complete meanwhile`() {
                assertEquals(imageCount, state.preparation?.total)
            }
        }

        class WhenTwoOfFourImagesAreCopied {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun copyTwoImages() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 4) { onProgress ->
                    run.copyPages(listOf("a", "b"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
                gate.complete(Unit)
            }

            @Test
            fun `should show the progress of the copy`() {
                assertEquals(Preparation(done = 2, total = 4, isCancellable = false), state.preparation)
            }
        }

        class WhenTheCopyEnds {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun copyTheImages() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { onProgress ->
                    run.copyPages(listOf("a", "b"), onProgress)
                    null
                }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should show no progress any more`() {
                assertEquals(PreparationState(), state)
            }
        }

        class WhenAnImportStartsWhileAScannerCopyRuns {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stateWhileTheFirstWaits: PreparationState
            private lateinit var pagesInTheRun: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun startTwoCopies() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { onProgress ->
                    run.copyPages(listOf("scan-a", "scan-b"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 1) { onProgress ->
                    run.copyPages(listOf("photo-a"), onProgress)
                    null
                }
                advanceUntilIdle()
                stateWhileTheFirstWaits = run.preparation.observe(DOCUMENT_ID).first()
                gate.complete(Unit)
                advanceUntilIdle()
                pagesInTheRun = run.readPages()
            }

            @Test
            fun `should add the photos after the scanned pages, even when the import is quicker`() {
                assertEquals(listOf("scan-a", "scan-b", "photo-a"), pagesInTheRun)
            }

            @Test
            fun `should count the images of both copies, and let the import be canceled`() {
                assertEquals(
                    Preparation(done = 2, total = 3, isCancellable = true),
                    stateWhileTheFirstWaits.preparation,
                )
            }
        }

        class WhenAScannerCopyStartsWhileAnImportRuns {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesWhileTheImportRuns: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun scanWhileImporting() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 1) { onProgress ->
                    run.copyPages(listOf("photo-a"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { onProgress ->
                    run.copyPages(listOf("scan-a", "scan-b"), onProgress)
                    null
                }
                advanceUntilIdle()
                pagesWhileTheImportRuns = run.readPages()
                gate.complete(Unit)
            }

            @Test
            fun `should add the scanned pages without waiting for the import, since they exist nowhere else`() {
                assertEquals(listOf("scan-a", "scan-b"), pagesWhileTheImportRuns)
            }
        }

        class WhenTwoImportsAreStartedOneAfterTheOther {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun importTwice() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 2) { onProgress ->
                    run.copyPages(listOf("first-a", "first-b"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 1) { onProgress ->
                    run.copyPages(listOf("second-a"), onProgress)
                    null
                }
                advanceUntilIdle()
                gate.complete(Unit)
                advanceUntilIdle()
                pagesInTheRun = run.readPages()
            }

            @Test
            fun `should add the photos of the first import first, even when the second is quicker`() {
                assertEquals(listOf("first-a", "first-b", "second-a"), pagesInTheRun)
            }
        }

        class WhenTwoScannerCopiesAreStartedOneAfterTheOther {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun scanTwice() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { onProgress ->
                    run.copyPages(listOf("first-a", "first-b"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 1) { onProgress ->
                    run.copyPages(listOf("second-a"), onProgress)
                    null
                }
                advanceUntilIdle()
                gate.complete(Unit)
                advanceUntilIdle()
                pagesInTheRun = run.readPages()
            }

            @Test
            fun `should add the pages of the first scan first, even when the second is quicker`() {
                assertEquals(listOf("first-a", "first-b", "second-a"), pagesInTheRun)
            }
        }

        class WhenAnImportSkipsPhotos {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun importThePhotos() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 3) { SKIPPED_PHOTOS }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should keep what was skipped, until it is dismissed`() {
                assertEquals(SKIPPED_PHOTOS, state.outcome)
            }

            companion object {
                private val SKIPPED_PHOTOS = PreparationOutcome.PhotosSkipped(
                    unsupported = 1,
                    tooLarge = 0,
                    unreadable = 2,
                )
            }
        }

        class WhenTwoImportsSkipPhotos {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun importThePhotos() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 3) {
                    PreparationOutcome.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 2)
                }
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 4) {
                    PreparationOutcome.PhotosSkipped(unsupported = 0, tooLarge = 3, unreadable = 1)
                }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should add up what both skipped, since one banner says it all`() {
                assertEquals(
                    PreparationOutcome.PhotosSkipped(unsupported = 1, tooLarge = 3, unreadable = 3),
                    state.outcome,
                )
            }
        }

        class WhenTheStorageIsFullAfterAnImportSkippedPhotos {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun importThePhotos() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 3) {
                    PreparationOutcome.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 0)
                }
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { throw NO_SPACE_LEFT }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should say that the storage is full, the more severe`() {
                assertEquals(PreparationOutcome.StorageFull, state.outcome)
            }
        }

        class WhenALessSevereOutcomeFollowsAMoreSevereOne {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun importTwice() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 2) { throw NO_SPACE_LEFT }
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 3) {
                    PreparationOutcome.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 0)
                }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should keep saying that the storage is full, the more severe`() {
                assertEquals(PreparationOutcome.StorageFull, state.outcome)
            }
        }

        class WhenTheCopyFailsForLackOfSpace {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun copyTheImages() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { throw NO_SPACE_LEFT }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should say that the storage is full`() {
                assertEquals(PreparationOutcome.StorageFull, state.outcome)
            }
        }

        class WhenTheCopyFailsForAnotherReason {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun copyTheImages() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 2) { throw SecurityException() }
                advanceUntilIdle()
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should say that the images could not be copied, rather than end the app`() {
                assertEquals(PreparationOutcome.ImportFailed, state.outcome)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheCancelMethod {
        class WhenAnImportIsCanceled {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>
            private lateinit var copiesLeft: List<File>

            @Before
            fun cancelTheImport() = runTest {
                val run = makeRun(folder)
                val secondPhotoReached = CompletableDeferred<Unit>()
                val importEnded = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 3) { onProgress ->
                    try {
                        importPhotos(
                            documentId = DOCUMENT_ID,
                            photos = listOf("photo-a", "photo-b", "photo-c"),
                            staging = run.staging,
                            importedAt = COPY_TIME,
                            copy = { photo, target ->
                                target.writeText(photo)
                                if (photo == "photo-b") {
                                    secondPhotoReached.complete(Unit)
                                    awaitCancellation()
                                }
                            },
                            check = { null },
                            takenAt = { null },
                            onProgress = onProgress,
                        )
                    } finally {
                        importEnded.complete(Unit)
                    }
                    null
                }
                secondPhotoReached.await()
                run.preparation.cancel(DOCUMENT_ID)
                importEnded.await()
                pagesInTheRun = run.readPages()
                copiesLeft = run.listIncomingFiles()
            }

            @Test
            fun `should add none of its photos`() {
                assertEquals(emptyList<String>(), pagesInTheRun)
            }

            @Test
            fun `should leave no copy behind`() {
                assertEquals(emptyList<File>(), copiesLeft)
            }
        }

        class WhenTheOnlyImportIsCanceled {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun cancelTheImport() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 2) { onProgress ->
                    run.copyPages(listOf("photo-a", "photo-b"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                advanceUntilIdle()
                run.preparation.cancel(DOCUMENT_ID)
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should show no progress at once, while the import gives up`() {
                assertEquals(PreparationState(), state)
            }
        }

        class WhenAnImportIsCanceledBeforeItStarts {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun cancelThenImportAgain() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 1) { onProgress ->
                    run.copyPages(listOf("canceled-a"), onProgress)
                    null
                }
                run.preparation.cancel(DOCUMENT_ID)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 1) { onProgress ->
                    run.copyPages(listOf("later-a"), onProgress)
                    null
                }
                advanceUntilIdle()
                pagesInTheRun = run.readPages()
            }

            @Test
            fun `should let a later import join`() {
                assertEquals(listOf("later-a"), pagesInTheRun)
            }
        }

        class WhenAScannerCopyIsAskedToCancel {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun cancelTheCopy() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { onProgress ->
                    run.copyPages(listOf("scan-a", "scan-b"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                advanceUntilIdle()
                run.preparation.cancel(DOCUMENT_ID)
                gate.complete(Unit)
                advanceUntilIdle()
                pagesInTheRun = run.readPages()
            }

            @Test
            fun `should add every page all the same, since they exist nowhere else`() {
                assertEquals(listOf("scan-a", "scan-b"), pagesInTheRun)
            }
        }

        class WhenAnImportWaitsBehindAScannerCopy {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun cancelTheImport() = runTest {
                val run = makeRun(folder)
                val gate = CompletableDeferred<Unit>()
                run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) { onProgress ->
                    run.copyPages(listOf("scan-a", "scan-b"), onProgress, beforeAdding = { gate.await() })
                    null
                }
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 1) { onProgress ->
                    run.copyPages(listOf("photo-a"), onProgress)
                    null
                }
                advanceUntilIdle()
                run.preparation.cancel(DOCUMENT_ID)
                gate.complete(Unit)
                advanceUntilIdle()
                pagesInTheRun = run.readPages()
            }

            @Test
            fun `should drop the import and finish the scanner's copy`() {
                assertEquals(listOf("scan-a", "scan-b"), pagesInTheRun)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDismissOutcomeMethod {
        class WhenPhotosWereSkipped {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: PreparationState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun dismissTheOutcome() = runTest {
                val run = makeRun(folder)
                run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 3) {
                    PreparationOutcome.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 0)
                }
                advanceUntilIdle()
                run.preparation.dismissOutcome(DOCUMENT_ID)
                state = run.preparation.observe(DOCUMENT_ID).first()
            }

            @Test
            fun `should leave no outcome`() {
                assertEquals(PreparationState(), state)
            }
        }
    }
}

private const val DOCUMENT_ID = "7c6b5a49-3827-4f16-a5e4-d3c2b1a09f8e"
private val COPY_TIME = Instant.parse("2026-10-12T08:00:00Z")
private val NO_SPACE_LEFT = IOException("write failed: ENOSPC (No space left on device)")

/** A document's run and the copies into it, on the test's scheduler. */
private class RunUnderTest(private val root: File, val staging: StagingArea, val preparation: RunPreparation) {
    /**
     * Copies images named [names], one after the other, then adds them to the run once
     * [beforeAdding] returns, as the copy of Google's scanner's pages does.
     */
    suspend fun copyPages(names: List<String>, onProgress: (Int) -> Unit, beforeAdding: suspend () -> Unit = {}) {
        val copies = names.mapIndexed { index, name ->
            val copy = staging.incomingFile(DOCUMENT_ID)
            copy.writeText(name)
            onProgress(index + 1)
            StagingInput(copy, COPY_TIME)
        }
        beforeAdding()
        staging.add(DOCUMENT_ID, copies)
    }

    /** The images of the run, in order, by what they hold. */
    suspend fun readPages(): List<String> = staging.pages(DOCUMENT_ID).map { it.file.readText() }

    fun listIncomingFiles(): List<File> = File(root, "$DOCUMENT_ID/incoming").listFiles().orEmpty().toList()
}

@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.makeRun(folder: TemporaryFolder): RunUnderTest {
    val root = File(folder.root, "staging")
    return RunUnderTest(root, StagingArea(root, StandardTestDispatcher(testScheduler)), RunPreparation(this))
}
