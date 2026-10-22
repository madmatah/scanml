package fr.scanmylib.ui.document

import android.net.Uri
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.MainDispatcherRule
import fr.scanmylib.library.PhotoImportResult
import fr.scanmylib.library.PreparationOutcome
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import java.io.File
import java.io.IOException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
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
                scan.viewModel.messages.first { it is ScanMessage.PagesQueued }
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
                scan.viewModel.messages.first { it is ScanMessage.PagesQueued }
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
    class TheDiscardMethod {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThreePagesWait {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesLeft: List<StagedPage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardThePages() = runTest {
                val scan = stageThreePages(folder)
                scan.viewModel.discard()
                advanceUntilIdle()
                pagesLeft = scan.staging.pages(DOCUMENT_ID)
            }

            @Test
            fun `should delete the run`() {
                assertEquals(emptyList<StagedPage>(), pagesLeft)
            }
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

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun removeTheSecondPage() = runTest {
                val scan = stageThreePages(folder)
                scan.viewModel.removePage(scan.stagedPages[1])
                advanceUntilIdle()
                stagedPages = scan.stagedPages
                pagesLeft = scan.staging.pages(DOCUMENT_ID)
            }

            @Test
            fun `should take that page out of the run, and keep the others`() {
                assertEquals(listOf(stagedPages[0], stagedPages[2]), pagesLeft)
            }
        }
    }
}

private suspend fun typeTheFirstPage(viewModel: ScanViewModel, firstPage: String) {
    viewModel.onFirstPageChange(firstPage)
    viewModel.scanState.first { it.firstPage == firstPage }
}
