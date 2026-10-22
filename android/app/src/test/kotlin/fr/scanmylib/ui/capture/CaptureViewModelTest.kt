package fr.scanmylib.ui.capture

import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.lifecycle.SavedStateHandle
import fr.scanmylib.MainDispatcherRule
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.StagingInput
import java.io.File
import java.time.Clock
import java.time.Instant
import java.time.ZoneOffset
import kotlin.properties.Delegates
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.plus
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class CaptureViewModelTest {
    @RunWith(Enclosed::class)
    class TheUiStateProperty {
        class WhenTheCameraOpensAfterPagesWereScanned {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 5
            private lateinit var state: CaptureUiState

            @Before
            fun openTheCamera() = runTest {
                val staging = createStagingArea(folder)
                scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                state = openTheCamera(staging).awaitState { it.ready }
            }

            @Test
            fun `should show none of them as photos of this visit`() {
                assertEquals(emptyList<StagedPage>(), state.pages)
            }

            @Test
            fun `should count them as waiting to be sent`() {
                assertEquals(scannedPageCount, state.waiting)
            }

            @Test
            fun `should have no photo to keep or delete, so that closing the screen asks nothing`() {
                assertEquals(0, state.photoCount)
            }
        }

        class WhenTheCameraOpens {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState

            @Before
            fun openTheCamera() = runTest {
                state = openTheCamera(createStagingArea(folder)).awaitTheStartOfTheVisit()
            }

            @Test
            fun `should leave the flash off, since on paper it mostly adds glare`() {
                assertEquals(FlashSetting.OFF, state.flash)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheShootMethod {
        class WhenTheCameraIsReady {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @Before
            fun pressTheShutter() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should take the photo`() {
                assertTrue(isPhotoTaken)
            }
        }

        class WhenAPhotoIsBeingSaved {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()
            private var captureCount by Delegates.notNull<Int>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun pressTheShutterAgain() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.takeAPhoto()
                isPhotoTaken = screen.pressTheShutter()
                advanceUntilIdle()
                captureCount = screen.captureCount
            }

            @Test
            fun `should take nothing, so that a second tap never takes the same page twice`() {
                assertFalse(isPhotoTaken)
            }

            @Test
            fun `should start no second capture`() {
                assertEquals(1, captureCount)
            }
        }

        class WhenAPhotoWasSaved {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @Before
            fun pressTheShutterAgain() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.photograph("page 1")
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should take the next photo`() {
                assertTrue(isPhotoTaken)
            }
        }

        class WhenThePhotoFailedAfterTheUserLeft {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @Before
            fun pressTheShutterAgain() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                val shot = screen.takeAPhoto()
                screen.leave()
                writeThePhoto(shot, "half a photo")
                screen.reportThePhotoFailed(shot)
                screen.awaitState { !it.shooting }
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should take the photo again`() {
                assertTrue(isPhotoTaken)
            }
        }

        class WhenTheVisitWasDiscardedWithAPhotoOnItsWay {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @Before
            fun pressTheShutterAgain() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.photograph("first page")
                val shot = screen.takeAPhoto()
                writeThePhoto(shot, "page on its way")
                screen.discardTheVisit()
                screen.reportThePhotoSaved(shot)
                screen.awaitState { !it.shooting && it.pages.isEmpty() }
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should still take photos, should the screen stay`() {
                assertTrue(isPhotoTaken)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnShotSavedMethod {
        class WhenAPhotoIsTakenAfterPagesWereScanned {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 5
            private lateinit var state: CaptureUiState
            private lateinit var lastPageContent: String

            @Before
            fun photographAPage() = runTest {
                val staging = createStagingArea(folder)
                scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                val screen = openTheCamera(staging)
                screen.photograph("photo 1")
                state = screen.awaitState { it.pages.size == 1 }
                lastPageContent = state.pages.last().file.readText()
            }

            @Test
            fun `should keep counting the pages scanned before as waiting`() {
                assertEquals(scannedPageCount, state.waiting)
            }

            @Test
            fun `should show the photo as the last page of the visit, never a page from before it`() {
                assertEquals("photo 1", lastPageContent)
            }
        }

        class WhenTheOnlyPhotoOfTheVisitWasDeletedAndIsTakenAgain {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var visitContents: List<String>

            @Before
            fun photographThePageAgain() = runTest {
                val staging = createStagingArea(folder)
                scanPagesAsGoogleScannerDoes(staging, 2)
                val screen = openTheCamera(staging)
                screen.photograph("blurred")
                screen.deleteTheOnlyPhoto()
                screen.photograph("sharp")
                visitContents = screen.awaitState { it.pages.size == 1 }.pages.map { it.file.readText() }
            }

            @Test
            fun `should show the new photo as the visit's`() {
                assertEquals(listOf("sharp"), visitContents)
            }
        }

        class WhenThePhotoIsSavedAfterTheUserLeft {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState
            private lateinit var visitContents: List<String>
            private var closingCount by Delegates.notNull<Int>()
            private lateinit var messages: List<CaptureMessage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun saveThePhoto() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                val shot = screen.takeAPhoto()
                screen.leave()
                writeThePhoto(shot, "last page")
                screen.reportThePhotoSaved(shot)
                state = screen.awaitState { it.pages.size == 1 && !it.shooting }
                visitContents = state.pages.map { it.file.readText() }
                advanceUntilIdle()
                closingCount = screen.closingCount
                messages = screen.messages
            }

            @Test
            fun `should add the photo to the run`() {
                assertEquals(listOf("last page"), visitContents)
            }

            @Test
            fun `should be done leaving`() {
                assertFalse(state.finishing)
            }

            @Test
            fun `should close the screen`() {
                assertEquals(1, closingCount)
            }

            @Test
            fun `should say nothing`() {
                assertEquals(emptyList<CaptureMessage>(), messages)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnShotFailedMethod {
        class WhenThePhotoFailsAfterTheUserLeft {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState
            private lateinit var messages: List<CaptureMessage>
            private var closingCount by Delegates.notNull<Int>()
            private var isPhotoLeftOnDisk by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun failThePhoto() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                val shot = screen.takeAPhoto()
                screen.leave()
                writeThePhoto(shot, "half a photo")
                screen.reportThePhotoFailed(shot)
                state = screen.awaitState { !it.shooting }
                advanceUntilIdle()
                messages = screen.messages
                closingCount = screen.closingCount
                isPhotoLeftOnDisk = shot.file.exists()
            }

            @Test
            fun `should keep the screen open, to say so`() {
                assertEquals(0, closingCount)
            }

            @Test
            fun `should stop leaving`() {
                assertFalse(state.finishing)
            }

            @Test
            fun `should say that the photo failed`() {
                assertEquals(listOf<CaptureMessage>(CaptureMessage.ShotFailed), messages)
            }

            @Test
            fun `should add no page`() {
                assertEquals(emptyList<StagedPage>(), state.pages)
            }

            @Test
            fun `should delete what the camera wrote of the photo`() {
                assertFalse(isPhotoLeftOnDisk)
            }
        }

        class WhenTheCameraClosesWhileWritingThePhoto {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var messages: List<CaptureMessage>

            @Before
            fun closeTheCamera() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                val shot = screen.takeAPhoto()
                screen.reportTheCameraClosed(shot)
                waitWhileTheCameraWritesThePhoto()
                messages = screen.messages
            }

            @Test
            fun `should say nothing while it waits for the photo`() {
                assertEquals(emptyList<CaptureMessage>(), messages)
            }
        }

        class WhenTheCameraClosesWhileWritingThePhotoAndThenWritesIt {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var visitContents: List<String>
            private lateinit var messages: List<CaptureMessage>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun writeThePhotoLate() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                val shot = screen.takeAPhoto()
                screen.reportTheCameraClosed(shot)
                waitWhileTheCameraWritesThePhoto()
                writeThePhoto(shot, "page")
                val state = screen.awaitState { it.pages.size == 1 && !it.shooting }
                visitContents = state.pages.map { it.file.readText() }
                advanceUntilIdle()
                messages = screen.messages
            }

            @Test
            fun `should still add the photo to the run`() {
                assertEquals(listOf("page"), visitContents)
            }

            @Test
            fun `should say nothing`() {
                assertEquals(emptyList<CaptureMessage>(), messages)
            }
        }

        class WhenTheCameraClosesAndNeverWritesThePhoto {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState
            private lateinit var messages: List<CaptureMessage>
            private var reportDelayMilliseconds by Delegates.notNull<Long>()
            private var isPhotoLeftOnDisk by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun loseThePhoto() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                val shot = screen.takeAPhoto()
                leaveThePhotoEmpty(shot)
                val closedAtMilliseconds = currentTime
                screen.reportTheCameraClosed(shot)
                state = screen.awaitState { !it.shooting }
                reportDelayMilliseconds = currentTime - closedAtMilliseconds
                messages = screen.messages
                isPhotoLeftOnDisk = shot.file.exists()
            }

            @Test
            fun `should report it lost only once the camera had its 5 s to write it`() {
                assertTrue(reportDelayMilliseconds >= 5_000)
            }

            @Test
            fun `should say that the photo failed`() {
                assertEquals(listOf<CaptureMessage>(CaptureMessage.ShotFailed), messages)
            }

            @Test
            fun `should add no page`() {
                assertEquals(emptyList<StagedPage>(), state.pages)
            }

            @Test
            fun `should delete the empty photo`() {
                assertFalse(isPhotoLeftOnDisk)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheFinishMethod {
        class WhenNoPhotoIsOnItsWay {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var closingCount by Delegates.notNull<Int>()

            @Before
            fun leave() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.leave()
                closingCount = screen.closingCount
            }

            @Test
            fun `should close the screen at once`() {
                assertEquals(1, closingCount)
            }
        }

        class WhenAPhotoWasTaken {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var closings: List<CameraClose>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun leave() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.photograph("photo 1")
                screen.leave()
                advanceUntilIdle()
                closings = screen.closings
            }

            @Test
            fun `should close keeping the photos, so that whoever opened the camera knows that it added pages`() {
                assertEquals(listOf(CameraClose(werePhotosKept = true)), closings)
            }
        }

        class WhenAPhotoIsBeingSaved {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState
            private var closingCount by Delegates.notNull<Int>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun leave() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.takeAPhoto()
                screen.leave()
                state = screen.awaitState { it.finishing }
                advanceUntilIdle()
                closingCount = screen.closingCount
            }

            @Test
            fun `should wait for the photo to join the run`() {
                assertTrue(state.shooting)
            }

            @Test
            fun `should keep the screen open meanwhile`() {
                assertEquals(0, closingCount)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDeletePageMethod {
        class WhenTheOnlyPhotoOfTheVisitIsDeleted {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 2
            private lateinit var scannedContents: List<String>
            private lateinit var state: CaptureUiState
            private lateinit var runContents: List<String>

            @Before
            fun deleteThePhoto() = runTest {
                val staging = createStagingArea(folder)
                scannedContents = scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                val screen = openTheCamera(staging)
                screen.photograph("blurred")
                state = screen.deleteTheOnlyPhoto()
                runContents = readContents(staging)
            }

            @Test
            fun `should keep counting the pages from before the visit as waiting`() {
                assertEquals(scannedPageCount, state.waiting)
            }

            @Test
            fun `should leave the pages from before the visit in the run`() {
                assertEquals(scannedContents, runContents)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDiscardMethod {
        class WhenTheVisitHasNoPhotoOfItsOwn {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scannedContents: List<String>
            private var closingCount by Delegates.notNull<Int>()
            private lateinit var runContents: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardTheVisit() = runTest {
                val staging = createStagingArea(folder)
                scannedContents = scanPagesAsGoogleScannerDoes(staging, 5)
                val screen = openTheCamera(staging)
                screen.discardTheVisit()
                advanceUntilIdle()
                closingCount = screen.closingCount
                runContents = readContents(staging)
            }

            @Test
            fun `should close the screen`() {
                assertEquals(1, closingCount)
            }

            @Test
            fun `should keep the draft`() {
                assertEquals(scannedContents, runContents)
            }
        }

        class WhenTheVisitHasAPhoto {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var scannedContents: List<String>
            private lateinit var closings: List<CameraClose>
            private lateinit var runContents: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardTheVisit() = runTest {
                val staging = createStagingArea(folder)
                scannedContents = scanPagesAsGoogleScannerDoes(staging, 5)
                val screen = openTheCamera(staging)
                screen.photograph("photo 1")
                screen.discardTheVisit()
                advanceUntilIdle()
                closings = screen.closings
                runContents = readContents(staging)
            }

            @Test
            fun `should close the screen once, without the photos`() {
                assertEquals(listOf(CameraClose(werePhotosKept = false)), closings)
            }

            @Test
            fun `should delete the photos of this visit only`() {
                assertEquals(scannedContents, runContents)
            }
        }
    }

    class WhenTheVisitIsDiscardedWithAPhotoOnItsWay {
        @get:Rule
        val mainDispatcher = MainDispatcherRule()

        @get:Rule
        val folder = TemporaryFolder()

        private lateinit var state: CaptureUiState
        private var closingCount by Delegates.notNull<Int>()
        private lateinit var messages: List<CaptureMessage>
        private var isPhotoLeftOnDisk by Delegates.notNull<Boolean>()

        @OptIn(ExperimentalCoroutinesApi::class)
        @Before
        fun discardTheVisit() = runTest {
            val screen = openTheCamera(createStagingArea(folder))
            screen.photograph("first page")
            val shot = screen.takeAPhoto()
            writeThePhoto(shot, "page on its way")
            screen.discardTheVisit()
            screen.reportThePhotoSaved(shot)
            state = screen.awaitState { !it.shooting && it.pages.isEmpty() }
            advanceUntilIdle()
            closingCount = screen.closingCount
            messages = screen.messages
            isPhotoLeftOnDisk = shot.file.exists()
        }

        @Test
        fun `should delete the photo on its way too`() {
            assertFalse(isPhotoLeftOnDisk)
        }

        @Test
        fun `should close the screen`() {
            assertEquals(1, closingCount)
        }

        @Test
        fun `should not be leaving, should the screen stay`() {
            assertFalse(state.finishing)
        }

        @Test
        fun `should say nothing`() {
            assertEquals(emptyList<CaptureMessage>(), messages)
        }
    }

    @RunWith(Enclosed::class)
    class WhenTheProcessEndsAfterAPhoto {
        class WhenTheScreenComesBack {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 5
            private lateinit var state: CaptureUiState
            private lateinit var visitContents: List<String>

            @Before
            fun comeBack() = runTest {
                val savedState = SavedStateHandle()
                val staging = createStagingArea(folder)
                scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                openTheCamera(staging, savedState).photograph("photo 1")
                state = comeBackAfterTheEndOfTheProcess(folder, savedState).awaitState { it.ready }
                visitContents = state.pages.map { it.file.readText() }
            }

            @Test
            fun `should still show the photo as the visit's`() {
                assertEquals(listOf("photo 1"), visitContents)
            }

            @Test
            fun `should still count the pages from before the visit as waiting`() {
                assertEquals(scannedPageCount, state.waiting)
            }
        }

        class WhenTheScreenComesBackAndTheCameraOpensAgain {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 5
            private lateinit var state: CaptureUiState

            @Before
            fun openTheCameraAgain() = runTest {
                val savedState = SavedStateHandle()
                val staging = createStagingArea(folder)
                scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                openTheCamera(staging, savedState).photograph("photo 1")
                comeBackAfterTheEndOfTheProcess(folder, savedState)
                state = openTheCameraAgain(folder).awaitState { it.ready }
            }

            @Test
            fun `should start a new visit after that photo`() {
                assertEquals(emptyList<StagedPage>(), state.pages)
            }

            @Test
            fun `should count that photo as waiting, with the pages from before it`() {
                assertEquals(scannedPageCount + 1, state.waiting)
            }
        }
    }
}

private const val DOCUMENT_ID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
private val CLOCK: Clock = Clock.fixed(Instant.parse("2026-10-12T18:30:00Z"), ZoneOffset.UTC)

// In the test's virtual time: a press that the shutter refused fails its hook at once.
private const val SHOT_WAIT_MILLISECONDS = 1_000L

private class CameraScreen(val viewModel: CaptureViewModel, scope: CoroutineScope) {
    private val receivedMessages = mutableListOf<CaptureMessage>()
    private val shots = Channel<Shot>(Channel.UNLIMITED)

    private val receivedClosings = mutableListOf<CameraClose>()

    /** Each close of the screen, which it handles at once while it is in front, as the nav host closes it. */
    val closings: List<CameraClose> get() = receivedClosings.toList()

    val closingCount: Int get() = receivedClosings.size

    var captureCount = 0
        private set

    val messages: List<CaptureMessage> get() = receivedMessages.toList()

    init {
        scope.launch {
            viewModel.uiState.collect { state ->
                state.closing?.let { close ->
                    receivedClosings += close
                    viewModel.onCloseHandled(close)
                }
            }
        }
        scope.launch { viewModel.messages.collect { receivedMessages += it } }
    }

    suspend fun awaitState(predicate: (CaptureUiState) -> Boolean): CaptureUiState = viewModel.uiState.first(predicate)

    suspend fun awaitTheStartOfTheVisit(): CaptureUiState = awaitState { it.ready }

    suspend fun pressTheShutter(): Boolean {
        awaitTheStartOfTheVisit()
        return viewModel.shoot { shot ->
            captureCount++
            shots.trySend(shot)
        }
    }

    suspend fun awaitTheShot(): Shot = withTimeout(SHOT_WAIT_MILLISECONDS) { shots.receive() }
}

/*
 * The disk's work, on the test's scheduler like the rest: each test runs on one thread, in a fixed
 * order, and nothing it started runs after it (on another thread, it raced the test's assertions
 * and resumed on a main dispatcher already reset).
 */
private val TestScope.io: CoroutineDispatcher get() = StandardTestDispatcher(testScheduler)

private fun TestScope.createStagingArea(folder: TemporaryFolder) = StagingArea(File(folder.root, "staging"), io)

private suspend fun readContents(staging: StagingArea): List<String> =
    staging.pages(DOCUMENT_ID).map { it.file.readText() }

private suspend fun scanPagesAsGoogleScannerDoes(staging: StagingArea, count: Int): List<String> =
    (1..count).map { number ->
        val content = "scanned page $number"
        val file = staging.incomingFile(DOCUMENT_ID).apply { writeText(content) }
        staging.add(DOCUMENT_ID, listOf(StagingInput(file, CLOCK.instant())))
        content
    }

@OptIn(ExperimentalCoroutinesApi::class)
private suspend fun TestScope.openTheCamera(
    staging: StagingArea,
    savedState: SavedStateHandle = SavedStateHandle(),
): CameraScreen {
    val viewModel = CaptureViewModel(savedState, DOCUMENT_ID, staging, CLOCK, io)
    val screen = CameraScreen(viewModel, backgroundScope + UnconfinedTestDispatcher(testScheduler))
    screen.awaitTheStartOfTheVisit()
    return screen
}

private suspend fun TestScope.comeBackAfterTheEndOfTheProcess(
    folder: TemporaryFolder,
    savedState: SavedStateHandle,
): CameraScreen = openTheCamera(
    createStagingArea(folder),
    SavedStateHandle(savedState.keys().associateWith { savedState.get<Any?>(it) }),
)

private suspend fun TestScope.openTheCameraAgain(folder: TemporaryFolder): CameraScreen =
    openTheCamera(createStagingArea(folder))

private suspend fun CameraScreen.takeAPhoto(): Shot {
    pressTheShutter()
    return awaitTheShot()
}

private suspend fun CameraScreen.photograph(content: String) {
    val shot = takeAPhoto()
    writeThePhoto(shot, content)
    reportThePhotoSaved(shot)
    awaitState { !it.shooting && it.pages.any { page -> page.file.readText() == content } }
}

private fun writeThePhoto(shot: Shot, content: String) {
    shot.file.writeText(content)
}

private fun leaveThePhotoEmpty(shot: Shot) {
    shot.file.createNewFile()
}

private fun CameraScreen.reportThePhotoSaved(shot: Shot) {
    viewModel.onShotSaved(shot)
}

private fun CameraScreen.reportThePhotoFailed(shot: Shot) {
    viewModel.onShotFailed(shot, ImageCaptureException(ImageCapture.ERROR_CAPTURE_FAILED, "failed", null))
}

private fun CameraScreen.reportTheCameraClosed(shot: Shot) {
    viewModel.onShotFailed(shot, ImageCaptureException(ImageCapture.ERROR_CAMERA_CLOSED, "Camera is closed.", null))
}

/*
 * The camera is still writing the photo: well within the screen's wait, and before its state stops
 * being shared, 5 s after its last observer.
 */
@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.waitWhileTheCameraWritesThePhoto() {
    advanceTimeBy(1_000)
}

private fun CameraScreen.leave() {
    viewModel.finish()
}

private fun CameraScreen.discardTheVisit() {
    viewModel.discard()
}

private suspend fun CameraScreen.deleteTheOnlyPhoto(): CaptureUiState {
    viewModel.deletePage(awaitState { it.pages.size == 1 }.pages.single())
    return awaitState { it.pages.isEmpty() }
}
