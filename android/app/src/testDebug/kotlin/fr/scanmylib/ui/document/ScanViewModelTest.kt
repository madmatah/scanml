package fr.scanmylib.ui.document

import fr.scanmylib.MainDispatcherRule
import fr.scanmylib.library.StagedPage
import java.io.IOException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
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
