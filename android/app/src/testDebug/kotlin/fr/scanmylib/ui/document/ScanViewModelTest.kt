package fr.scanmylib.ui.document

import android.net.Uri
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.MainDispatcherRule
import fr.scanmylib.library.CopySource
import fr.scanmylib.library.PhotoImportResult
import fr.scanmylib.library.PreparationOutcome
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import java.io.File
import java.io.IOException
import kotlin.properties.Delegates
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
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
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class ScanViewModelTest {
    @RunWith(Enclosed::class)
    class TheSendMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThreePagesWaitWithoutNumbers {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var queuedPages: List<QueuedPage>
            private lateinit var pagesLeft: List<StagedPage>

            @Before
            fun sendThePages() = runTest {
                val scan = stageThreePages(folder)
                scan.viewModel.send()
                scan.viewModel.scanState.first { it.reviewEnd != null }
                stagedPages = scan.stagedPages
                queuedPages = scan.queue.pages.toList()
                pagesLeft = scan.staging.pages(DOCUMENT_ID)
            }

            @Test
            fun `should queue the three pages in their order, without numbers`() {
                assertEquals(stagedPages.map { QueuedPage(it.file.name, hint = null) }, queuedPages)
            }

            @Test
            fun `should empty the run`() {
                assertEquals(emptyList<StagedPage>(), pagesLeft)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheFirstPageIs12AndThePagesAreConsecutive {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var nextFirstPage: String

            @Before
            fun sendThePages() = runTest {
                val scan = stageThreePages(folder)
                typeTheFirstPage(scan.viewModel, FIRST_PAGE)
                scan.viewModel.send()
                scan.viewModel.scanState.first { it.reviewEnd != null }
                nextFirstPage = scan.viewModel.scanState.first { !it.sending }.firstPage
            }

            @Test
            fun `should start the next run after them, at page 15, as a book is scanned in order`() {
                assertEquals("15", nextFirstPage)
            }

            companion object {
                private const val FIRST_PAGE = "12"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheFirstPageIsInvalid {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var queuedPages: List<QueuedPage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun sendThePages() = runTest {
                val scan = stageThreePages(folder)
                typeTheFirstPage(scan.viewModel, INVALID_FIRST_PAGE)
                scan.viewModel.send()
                advanceUntilIdle()
                queuedPages = scan.queue.pages.toList()
            }

            @Test
            fun `should send nothing, so that no page is numbered wrong`() {
                assertEquals(emptyList<QueuedPage>(), queuedPages)
            }

            companion object {
                private const val INVALID_FIRST_PAGE = "0"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheSendFails {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var pagesLeft: List<StagedPage>
            private lateinit var message: ScanMessage

            @Before
            fun sendThePages() = runTest {
                val scan = stageThreePages(folder, sendRefusal = IOException("database closed"))
                scan.viewModel.send()
                message = scan.viewModel.messages.first()
                stagedPages = scan.stagedPages
                pagesLeft = scan.staging.pages(DOCUMENT_ID)
            }

            @Test
            fun `should keep the pages in the run, to send them again`() {
                assertEquals(stagedPages, pagesLeft)
            }

            @Test
            fun `should say that they could not be sent`() {
                assertEquals(ScanMessage.SendFailed, message)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThreePagesWaitAndPhotosWereSkipped {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun sendThePages() = runTest {
                val run = stageThreePages(folder)
                skipAPhoto(run)
                run.viewModel.send()
                scan = run.viewModel.scanState.first { it.reviewEnd != null }
            }

            @Test
            fun `should end the review, telling that the three pages are sent`() {
                assertEquals(ReviewEnd.PagesSent(PAGE_COUNT), scan.reviewEnd)
            }

            @Test
            fun `should dismiss how the last copies ended, which the review showed`() {
                assertEquals(null, scan.outcome)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenACopyRuns {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var queuedPages: List<QueuedPage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun sendThePages() = runTest {
                val run = stageThreePages(folder)
                val gate = startACopy(run)
                run.viewModel.send()
                advanceUntilIdle()
                queuedPages = run.queue.pages.toList()
                gate.complete(Unit)
            }

            @Test
            fun `should send nothing, so that the pages on their way are not left out`() {
                assertEquals(emptyList<QueuedPage>(), queuedPages)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenASourceIsOpen {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var queuedPages: List<QueuedPage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun sendThePages() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.onAddingPages()
                run.viewModel.send()
                advanceUntilIdle()
                queuedPages = run.queue.pages.toList()
            }

            @Test
            fun `should send nothing, so that the review stays for the source's pages`() {
                assertEquals(emptyList<QueuedPage>(), queuedPages)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAPageAwaitsItsUndo {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var queuedPages: List<QueuedPage>
            private var isRemovedImageKept by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun sendThePages() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.viewModel.send()
                run.viewModel.scanState.first { it.reviewEnd != null }
                advanceUntilIdle()
                stagedPages = run.stagedPages
                queuedPages = run.queue.pages.toList()
                isRemovedImageKept = isOnDisk(folder, run.stagedPages[1])
            }

            @Test
            fun `should send only the pages left in the run`() {
                assertEquals(
                    listOf(stagedPages[0], stagedPages[2]).map { QueuedPage(it.file.name, hint = null) },
                    queuedPages,
                )
            }

            @Test
            fun `should delete the removed page for good, since the review ends`() {
                assertFalse(isRemovedImageKept)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnPagesScannedMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheViewModelIsClearedWhileThePagesAreCopied {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun clearTheViewModelMidCopy() = runTest {
                val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
                val gate = CompletableDeferred<Unit>()
                val scanner = FakeScanner(staging, gate)
                val store = ViewModelStore()
                val factory = viewModelFactory {
                    initializer { makeViewModel(folder, staging, addScannedPages = scanner::copy) }
                }
                val viewModel = ViewModelProvider.create(store, factory)[ScanViewModel::class]
                viewModel.onPagesScanned(SCANNED_PAGES.map(Uri::parse))
                scanner.firstPageCopied.await()
                store.clear()
                gate.complete(Unit)
                advanceUntilIdle()
                pagesInTheRun = staging.pages(DOCUMENT_ID).map { it.file.readText() }
            }

            @Test
            fun `should add every page to the run, since they exist nowhere else`() {
                assertEquals(SCANNED_PAGES, pagesInTheRun)
            }

            companion object {
                private val SCANNED_PAGES = (1..3).map { "file:///scanner/page-$it.jpg" }
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenPagesAreScannedWhileAnImportRuns {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesWhileTheImportRuns: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun scanWhileImporting() = runTest {
                val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
                val importGate = CompletableDeferred<Unit>()
                val scanner = FakeScanner(staging, gate = CompletableDeferred(Unit))
                val viewModel = makeViewModel(
                    folder,
                    staging,
                    addScannedPages = scanner::copy,
                    addPhotos = { _, _ ->
                        importGate.await()
                        PhotoImportResult(added = 0)
                    },
                )
                viewModel.onPhotosPicked(listOf(Uri.parse(PICKED_PHOTO)))
                viewModel.onPagesScanned(SCANNED_PAGES.map(Uri::parse))
                advanceUntilIdle()
                pagesWhileTheImportRuns = staging.pages(DOCUMENT_ID).map { it.file.readText() }
                importGate.complete(Unit)
            }

            @Test
            fun `should add them to the run before the import ends, since they exist nowhere else`() {
                assertEquals(SCANNED_PAGES, pagesWhileTheImportRuns)
            }

            companion object {
                private const val PICKED_PHOTO = "content://media/picker/photo-1"
                private val SCANNED_PAGES = (1..2).map { "file:///scanner/page-$it.jpg" }
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnPhotosPickedMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenSomePhotosAreSkipped {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun pickThePhotos() = runTest {
                val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
                val viewModel = makeViewModel(folder, staging, addPhotos = { _, _ -> IMPORT_COUNTS })
                backgroundScope.launch { viewModel.scanState.collect {} }
                viewModel.onPhotosPicked(PICKED_PHOTOS.map(Uri::parse))
                advanceUntilIdle()
                scan = viewModel.scanState.first { it.outcome != null }
            }

            @Test
            fun `should say which photos were left out, and why`() {
                assertEquals(
                    PreparationOutcome.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 2),
                    scan.outcome,
                )
            }

            companion object {
                private val PICKED_PHOTOS = (1..4).map { "content://media/picker/photo-$it" }
                private val IMPORT_COUNTS = PhotoImportResult(added = 1, unsupported = 1, unreadable = 2)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheImportSharedPhotosMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheSameShareIsAskedForTwice {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var starts: List<Boolean>
            private var importCount by Delegates.notNull<Int>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun importTwice() = runTest {
                val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
                var imports = 0
                val viewModel = makeViewModel(
                    folder,
                    staging,
                    addPhotos = { _, _ ->
                        imports++
                        PhotoImportResult(added = 0)
                    },
                )
                val photos = SHARED_PHOTOS.map(Uri::parse)
                starts = listOf(viewModel.importSharedPhotos(photos), viewModel.importSharedPhotos(photos))
                advanceUntilIdle()
                importCount = imports
            }

            @Test
            fun `should say that only the first one started, so that the review opens once`() {
                assertEquals(listOf(true, false), starts)
            }

            @Test
            fun `should import the photos once, even when the screen is recreated with the same share`() {
                assertEquals(1, importCount)
            }

            companion object {
                private val SHARED_PHOTOS = (1..2).map { "content://media/shared/photo-$it" }
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenNoPhotoIsShared {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isStarted by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun importNothing() = runTest {
                val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
                isStarted = makeViewModel(folder, staging).importSharedPhotos(emptyList())
            }

            @Test
            fun `should start nothing, so that no review opens empty`() {
                assertFalse(isStarted)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDiscardMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThreePagesWaitAndPhotosWereSkipped {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesLeft: List<StagedPage>
            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardThePages() = runTest {
                val run = stageThreePages(folder)
                skipAPhoto(run)
                run.viewModel.discard()
                advanceUntilIdle()
                pagesLeft = run.staging.pages(DOCUMENT_ID)
                scan = run.viewModel.scanState.value
            }

            @Test
            fun `should delete the run`() {
                assertEquals(emptyList<StagedPage>(), pagesLeft)
            }

            @Test
            fun `should end the review, telling that the three pages are deleted`() {
                assertEquals(ReviewEnd.PagesDeleted(PAGE_COUNT), scan.reviewEnd)
            }

            @Test
            fun `should dismiss how the last copies ended, which the review showed`() {
                assertEquals(null, scan.outcome)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenACopyRuns {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var pagesLeft: List<StagedPage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardThePages() = runTest {
                val run = stageThreePages(folder)
                val gate = startACopy(run)
                run.viewModel.discard()
                advanceUntilIdle()
                stagedPages = run.stagedPages
                pagesLeft = run.staging.pages(DOCUMENT_ID)
                gate.complete(Unit)
            }

            @Test
            fun `should delete nothing, since the pages on their way would join the run afterwards`() {
                assertEquals(stagedPages, pagesLeft)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenASourceIsOpen {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var pagesLeft: List<StagedPage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardThePages() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.onAddingPages()
                run.viewModel.discard()
                advanceUntilIdle()
                stagedPages = run.stagedPages
                pagesLeft = run.staging.pages(DOCUMENT_ID)
            }

            @Test
            fun `should delete nothing, so that the review stays for the source's pages`() {
                assertEquals(stagedPages, pagesLeft)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAPageAwaitsItsUndo {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isRemovedImageKept by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardThePages() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.viewModel.discard()
                advanceUntilIdle()
                isRemovedImageKept = isOnDisk(folder, run.stagedPages[1])
            }

            @Test
            fun `should delete the removed page too, since the review ends`() {
                assertFalse(isRemovedImageKept)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheCloseReviewMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenPagesWait {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var scan: ScanUiState

            @Before
            fun closeTheReview() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.closeReview()
                stagedPages = run.stagedPages
                scan = run.viewModel.scanState.first { it.reviewEnd != null }
            }

            @Test
            fun `should end the review, telling that the pages are kept`() {
                assertEquals(ReviewEnd.PagesKept, scan.reviewEnd)
            }

            @Test
            fun `should keep the pages on the phone`() {
                assertEquals(stagedPages, scan.stagedPages)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenPagesAreBeingCopiedIntoAnEmptyRun {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @Before
            fun closeTheReview() = runTest {
                val run = makeEmptyRun(folder)
                val gate = startACopy(run)
                run.viewModel.closeReview()
                scan = run.viewModel.scanState.first { it.reviewEnd != null }
                gate.complete(Unit)
            }

            @Test
            fun `should tell that the pages are kept, since they are on their way`() {
                assertEquals(ReviewEnd.PagesKept, scan.reviewEnd)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheRunIsEmpty {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @Before
            fun closeTheReview() = runTest {
                val run = makeEmptyRun(folder)
                run.viewModel.closeReview()
                scan = run.viewModel.scanState.first { it.reviewEnd != null }
            }

            @Test
            fun `should end the review with nothing to tell`() {
                assertEquals(ReviewEnd.Emptied, scan.reviewEnd)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenPagesAreBeingSent {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun closeTheReview() = runTest {
                val sendGate = CompletableDeferred<Unit>()
                val run = stageThreePages(folder, sendGate)
                run.viewModel.send()
                run.viewModel.closeReview()
                advanceUntilIdle()
                scan = run.viewModel.scanState.value
                sendGate.complete(Unit)
            }

            @Test
            fun `should not end the review, which the send ends`() {
                assertEquals(null, scan.reviewEnd)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenASourceIsOpen {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var reviewEnds: List<ReviewEnd?>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun closeTheReview() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.onAddingPages()
                run.viewModel.closeReview()
                advanceUntilIdle()
                reviewEnds = listOf(run.viewModel.scanState.value.reviewEnd)
            }

            @Test
            fun `should keep the review open, so that the source's pages reach it`() {
                assertEquals(listOf(null), reviewEnds)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheReviewHasEndedAlready {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun closeTheReviewAfterTheDeletion() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.discard()
                run.viewModel.closeReview()
                advanceUntilIdle()
                scan = run.viewModel.scanState.first { it.stagedPages.isEmpty() }
            }

            @Test
            fun `should keep how it ended, which the document then tells`() {
                assertEquals(ReviewEnd.PagesDeleted(PAGE_COUNT), scan.reviewEnd)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAPageAwaitsItsUndo {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isRemovedImageKept by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun closeTheReview() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.viewModel.closeReview()
                advanceUntilIdle()
                isRemovedImageKept = isOnDisk(folder, run.stagedPages[1])
            }

            @Test
            fun `should delete the removed page for good, as the snackbar that undoes it closes too`() {
                assertFalse(isRemovedImageKept)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnReviewEndShownMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThePagesWereKept {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun showTheEnd() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.closeReview()
                run.viewModel.scanState.first { it.reviewEnd != null }
                run.viewModel.onReviewEndShown()
                advanceUntilIdle()
                scan = run.viewModel.scanState.value
            }

            @Test
            fun `should forget the end, so that it is told once`() {
                assertEquals(null, scan.reviewEnd)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnReviewOpenedMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAnEndIsLeftOver {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun openAReview() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.closeReview()
                run.viewModel.scanState.first { it.reviewEnd != null }
                run.viewModel.onReviewOpened()
                advanceUntilIdle()
                scan = run.viewModel.scanState.value
            }

            @Test
            fun `should forget it, so that a review opened after an end stays open`() {
                assertEquals(null, scan.reviewEnd)
            }
        }
    }

    @RunWith(RobolectricTestRunner::class)
    @Config(sdk = [36])
    class WhenTheProcessEndedWhileAddingPages {
        @get:Rule
        val mainDispatcher = MainDispatcherRule()

        @get:Rule
        val folder = TemporaryFolder()

        private var isAddingInterrupted by Delegates.notNull<Boolean>()

        @OptIn(ExperimentalCoroutinesApi::class)
        @Before
        fun openTheDocument() = runTest {
            val run = makeRunCutShort(folder)
            advanceUntilIdle()
            isAddingInterrupted = run.viewModel.scanState.value.wasAddingInterrupted
        }

        @Test
        fun `should say so until it is dismissed`() {
            assertTrue(isAddingInterrupted)
        }
    }

    @RunWith(RobolectricTestRunner::class)
    @Config(sdk = [36])
    class WhenTheProcessEndedWhileAddingPagesAndItIsDismissed {
        @get:Rule
        val mainDispatcher = MainDispatcherRule()

        @get:Rule
        val folder = TemporaryFolder()

        private var isAddingInterrupted by Delegates.notNull<Boolean>()

        @OptIn(ExperimentalCoroutinesApi::class)
        @Before
        fun dismissIt() = runTest {
            val run = makeRunCutShort(folder)
            advanceUntilIdle()
            run.viewModel.dismissAddingInterrupted()
            advanceUntilIdle()
            isAddingInterrupted = run.viewModel.scanState.value.wasAddingInterrupted
        }

        @Test
        fun `should no longer say so`() {
            assertFalse(isAddingInterrupted)
        }
    }

    @RunWith(Enclosed::class)
    class TheRemovePageMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThreePagesWait {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var pagesLeft: List<StagedPage>
            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun removeIt() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                advanceUntilIdle()
                stagedPages = run.stagedPages
                pagesLeft = run.staging.pages(DOCUMENT_ID)
                scan = run.viewModel.scanState.value
            }

            @Test
            fun `should take that page out of the run, and keep the others`() {
                assertEquals(listOf(stagedPages[0], stagedPages[2]), pagesLeft)
            }

            @Test
            fun `should let the removal be undone`() {
                assertEquals(stagedPages[1], scan.removedPage)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAnotherPageAwaitsItsUndo {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isEarlierImageKept by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun removeTheFirstPage() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                removeTheFirstPage(run)
                advanceUntilIdle()
                isEarlierImageKept = isOnDisk(folder, run.stagedPages[1])
            }

            @Test
            fun `should delete the earlier page for good, since one removal waits at a time`() {
                assertFalse(isEarlierImageKept)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheSamePageIsRemovedTwice {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun removeItTwiceThenUndo() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.viewModel.removePage(run.stagedPages[1])
                advanceUntilIdle()
                run.viewModel.restorePage(run.stagedPages[1])
                stagedPages = run.stagedPages
                scan = run.viewModel.scanState.first { it.removedPage == null }
            }

            @Test
            fun `should keep it restorable, as a second tap on Remove changes nothing`() {
                assertEquals(stagedPages, scan.stagedPages)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheRestorePageMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheSecondOfThreePagesWasRemoved {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var scan: ScanUiState

            @Before
            fun restoreIt() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.viewModel.restorePage(run.stagedPages[1])
                stagedPages = run.stagedPages
                scan = run.viewModel.scanState.first { it.removedPage == null && it.stagedPages.size == PAGE_COUNT }
            }

            @Test
            fun `should put the page back in its place`() {
                assertEquals(stagedPages, scan.stagedPages)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAPageOfTheSameNameIsInTheRun {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var message: ScanMessage

            @Before
            fun restoreIt() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.stagedPages[1].file.writeBytes(byteArrayOf(0))
                run.viewModel.restorePage(run.stagedPages[1])
                message = run.viewModel.messages.first()
            }

            @Test
            fun `should say that the page could not be put back`() {
                assertEquals(ScanMessage.PageNotRestored, message)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenASecondPageIsRemovedAndUndoneWhileTheRunIsBusy {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var pagesLeft: List<StagedPage>
            private lateinit var messages: List<ScanMessage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun removeAndUndo() = runTest {
                val run = stageThreePages(folder)
                val receivedMessages = mutableListOf<ScanMessage>()
                backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
                    run.viewModel.messages.toList(receivedMessages)
                }
                removeTheSecondPage(run)
                val release = holdTheStagingAreaLock(run.staging)
                run.viewModel.removePage(run.stagedPages[0])
                run.viewModel.restorePage(run.stagedPages[0])
                release()
                advanceUntilIdle()
                stagedPages = run.stagedPages
                pagesLeft = run.staging.pages(DOCUMENT_ID)
                messages = receivedMessages.toList()
            }

            @Test
            fun `should put the page back`() {
                assertEquals(listOf(stagedPages[0], stagedPages[2]), pagesLeft)
            }

            @Test
            fun `should say nothing, since nothing failed`() {
                assertEquals(emptyList<ScanMessage>(), messages)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDeleteRemovedPageMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheSecondOfThreePagesWasRemoved {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isImageKept by Delegates.notNull<Boolean>()
            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun deleteIt() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.viewModel.deleteRemovedPage(run.stagedPages[1])
                advanceUntilIdle()
                isImageKept = isOnDisk(folder, run.stagedPages[1])
                scan = run.viewModel.scanState.value
            }

            @Test
            fun `should delete the page for good`() {
                assertFalse(isImageKept)
            }

            @Test
            fun `should leave nothing to undo`() {
                assertEquals(null, scan.removedPage)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenASecondPageIsRemovedAndTheFirstSnackbarEnds {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var scan: ScanUiState

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun endTheFirstSnackbar() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                removeTheFirstPage(run)
                run.viewModel.deleteRemovedPage(run.stagedPages[1])
                advanceUntilIdle()
                stagedPages = run.stagedPages
                scan = run.viewModel.scanState.value
            }

            @Test
            fun `should leave the second page restorable`() {
                assertEquals(stagedPages[0], scan.removedPage)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnAddingPagesMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAPageAwaitsItsUndo {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isRemovedImageKept by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun openASource() = runTest {
                val run = stageThreePages(folder)
                removeTheSecondPage(run)
                run.viewModel.onAddingPages()
                advanceUntilIdle()
                isRemovedImageKept = isOnDisk(folder, run.stagedPages[1])
            }

            @Test
            fun `should delete it for good, as the new pages follow the run as it is`() {
                assertFalse(isRemovedImageKept)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheOnlyPageAwaitsItsUndo {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var hasNothingToReview by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun openASource() = runTest {
                val run = stagePages(folder, pageCount = 1)
                run.viewModel.removePage(run.stagedPages.single())
                run.viewModel.scanState.first { it.stagedPages.isEmpty() }
                run.viewModel.onAddingPages()
                advanceUntilIdle()
                hasNothingToReview = run.viewModel.scanState.value.hasNothingToReview
            }

            @Test
            fun `should keep the review open until the source returns`() {
                assertFalse(hasNothingToReview)
            }
        }
    }

    @RunWith(RobolectricTestRunner::class)
    @Config(sdk = [36])
    class WhenTheViewModelIsClearedWithAPageAwaitingItsUndo {
        @get:Rule
        val mainDispatcher = MainDispatcherRule()

        @get:Rule
        val folder = TemporaryFolder()

        private var isRemovedImageKept by Delegates.notNull<Boolean>()

        @OptIn(ExperimentalCoroutinesApi::class)
        @Before
        fun clearTheViewModel() = runTest {
            val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
            val stagedPages = staging.add(DOCUMENT_ID, writeImages(staging, PAGE_COUNT))
            val store = ViewModelStore()
            val factory = viewModelFactory { initializer { makeViewModel(folder, staging) } }
            val viewModel = ViewModelProvider.create(store, factory)[ScanViewModel::class]
            viewModel.scanState.first { it.stagedPages == stagedPages }
            viewModel.removePage(stagedPages[1])
            viewModel.scanState.first { it.stagedPages.size == PAGE_COUNT - 1 }
            store.clear()
            advanceUntilIdle()
            isRemovedImageKept = isOnDisk(folder, stagedPages[1])
        }

        @Test
        fun `should delete the removed page for good, since nothing can undo it any more`() {
            assertFalse(isRemovedImageKept)
        }
    }
}

private suspend fun typeTheFirstPage(viewModel: ScanViewModel, firstPage: String) {
    viewModel.onFirstPageChange(firstPage)
    viewModel.scanState.first { it.firstPage == firstPage }
}

private const val PAGE_COUNT = 3
private const val OTHER_DOCUMENT_ID = "0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d"

/** An import that skipped a photo, whose outcome the view model shows. */
@OptIn(ExperimentalCoroutinesApi::class)
private suspend fun TestScope.skipAPhoto(run: RunUnderReview) {
    run.preparation.start(DOCUMENT_ID, CopySource.GALLERY_PHOTOS, total = 1) {
        PreparationOutcome.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 0)
    }
    advanceUntilIdle()
    run.viewModel.scanState.first { it.outcome != null }
}

/** A copy into the run that goes on until the returned gate opens. */
private suspend fun startACopy(run: RunUnderReview): CompletableDeferred<Unit> {
    val gate = CompletableDeferred<Unit>()
    run.preparation.start(DOCUMENT_ID, CopySource.SCANNED_PAGES, total = 2) {
        gate.await()
        null
    }
    run.viewModel.scanState.first { it.preparing }
    return gate
}

/** The second page out of the run, its removal waiting to be undone. */
private suspend fun removeTheSecondPage(run: RunUnderReview) {
    run.viewModel.removePage(run.stagedPages[1])
    run.viewModel.scanState.first { run.stagedPages[1] !in it.stagedPages }
}

/** The first page out of the run too, after the second one. */
private suspend fun removeTheFirstPage(run: RunUnderReview) {
    run.viewModel.removePage(run.stagedPages[0])
    run.viewModel.scanState.first { run.stagedPages[0] !in it.stagedPages }
}

// The sending of another document's run holds the staging area's one lock, and touches nothing of
// this document's run.
private suspend fun TestScope.holdTheStagingAreaLock(staging: StagingArea): () -> Unit {
    val isHeld = CompletableDeferred<Unit>()
    val gate = CompletableDeferred<Unit>()
    launch {
        staging.send(OTHER_DOCUMENT_ID) {
            isHeld.complete(Unit)
            gate.await()
        }
    }
    isHeld.await()
    return { gate.complete(Unit) }
}

/** Whether [page]'s image is anywhere in the staging area, in the run or out of it. */
private fun isOnDisk(folder: TemporaryFolder, page: StagedPage): Boolean =
    File(folder.root, "staging").walk().any { it.isFile && it.name == page.file.name }
