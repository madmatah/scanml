package fr.scanmylib.ui.capture

import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.MainDispatcherRule
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.StagingInput
import java.io.File
import java.time.Clock
import java.time.Instant
import java.time.ZoneOffset
import kotlin.properties.Delegates
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
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
import org.junit.runners.Parameterized

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

        class WhenPagesJoinTheRunDuringTheVisit {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 2
            private lateinit var visitContents: List<String>

            @Before
            fun scanDuringTheVisit() = runTest {
                val staging = createStagingArea(folder)
                val screen = openTheCamera(staging)
                screen.photograph("photo 1")
                scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                val state = screen.awaitState { it.waiting == scannedPageCount }
                visitContents = state.pages.map { it.file.readText() }
            }

            @Test
            fun `should not show them as this visit's photos`() {
                assertEquals(listOf("photo 1"), visitContents)
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

            @Test
            fun `should let the shutter take a photo`() {
                assertTrue(state.canShoot)
            }

            @Test
            fun `should not offer Done, with no photo to keep`() {
                assertFalse(state.canFinish)
            }

            @Test
            fun `should let the user leave`() {
                assertTrue(state.canLeave)
            }

            @Test
            fun `should let the user switch to another source`() {
                assertTrue(state.canSwitchSource)
            }
        }

        class WhenAPhotoIsBeingSaved {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState

            @Before
            fun takeAPhoto() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.takeAPhoto()
                state = screen.awaitState { it.shooting }
            }

            @Test
            fun `should not let the shutter take another photo, so that a page is never taken twice`() {
                assertFalse(state.canShoot)
            }

            @Test
            fun `should offer Done, which waits for the photo`() {
                assertTrue(state.canFinish)
            }
        }

        class WhenTheUserIsDoneWhileAPhotoIsBeingSaved {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState

            @Before
            fun leave() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.takeAPhoto()
                screen.leave()
                state = screen.awaitState { it.finishing }
            }

            @Test
            fun `should not let the shutter take a photo, since the screen closes`() {
                assertFalse(state.canShoot)
            }

            @Test
            fun `should not offer Done again`() {
                assertFalse(state.canFinish)
            }
        }

        class WhenTheRunIsNotReadYet {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState

            @Before
            fun createTheScreen() = runTest {
                state = createTheCameraViewModel(createStagingArea(folder), SavedStateHandle(), ViewModelStore())
                    .uiState.value
            }

            @Test
            fun `should not let the shutter take a photo, since the visit's photos are not known yet`() {
                assertFalse(state.canShoot)
            }
        }

        class WhenTheStateIsTheOneTheScreenStartsFrom {
            private val state = CaptureUiState()

            @Test
            fun `should not let the shutter take a photo, since the run is not read yet`() {
                assertFalse(state.canShoot)
            }
        }

        class WhenACloseWaitsForTheScreen {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState

            @Before
            fun leaveWhileTheScreenIsStopped() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.photograph("photo 1")
                screen.stop()
                screen.leave()
                state = screen.awaitState { it.closing != null }
            }

            @Test
            fun `should offer neither leaving, Done nor the shutter, since the screen closes`() {
                val offers = with(state) { listOf(canLeave, canFinish, canShoot) }
                assertEquals(listOf(false, false, false), offers)
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

        class WhenTheVisitIsBeingDiscarded {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @Before
            fun pressTheShutterAgain() = runTest {
                val staging = createStagingArea(folder)
                val screen = openTheCamera(staging)
                screen.photograph("first page")
                val release = holdTheStagingAreaLock(staging)
                screen.discardTheVisit()
                isPhotoTaken = screen.pressTheShutter()
                release()
            }

            @Test
            fun `should take no photo, since the visit's photos are being deleted`() {
                assertFalse(isPhotoTaken)
            }
        }

        class WhenTheVisitWasDiscardedWithAPhotoOnItsWay {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun pressTheShutterAgain() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.photograph("first page")
                val shot = screen.takeAPhoto()
                writeThePhoto(shot, "page on its way")
                screen.discardTheVisit()
                screen.reportThePhotoSaved(shot)
                advanceUntilIdle()
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should take no more photos, since the screen closes without them`() {
                assertFalse(isPhotoTaken)
            }
        }

        class WhenAPhotoOfTheDiscardedVisitResistedItsDeletion {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun pressTheShutterAgain() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.photograph("first page")
                makeUndeletable(screen.awaitState { it.pages.size == 1 }.pages.single())
                screen.discardTheVisit()
                advanceUntilIdle()
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should take photos again, since the screen stays with them`() {
                assertTrue(isPhotoTaken)
            }
        }

        class WhenACloseWaitsForTheScreen {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @Before
            fun pressTheShutterWhileTheScreenCloses() = runTest {
                val screen = openTheCamera(createStagingArea(folder))
                screen.photograph("photo 1")
                screen.stop()
                screen.leave()
                screen.awaitState { it.closing != null }
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should take no photo, since the screen closes`() {
                assertFalse(isPhotoTaken)
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
                assertTrue(reportDelayMilliseconds >= CaptureViewModel.LATE_PHOTO_WAIT_MS)
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

        class WhenAPhotoIsBeingAddedAsTheVisitIsDiscarded {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 2
            private lateinit var scannedContents: List<String>
            private lateinit var runContents: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardTheVisit() = runTest {
                val staging = createStagingArea(folder)
                scannedContents = scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                val screen = openTheCamera(staging)
                val shot = screen.takeAPhoto()
                writeThePhoto(shot, "page being added")
                val release = holdTheStagingAreaLock(staging)
                screen.reportThePhotoSaved(shot)
                screen.discardTheVisit()
                release()
                advanceUntilIdle()
                runContents = readContents(staging)
            }

            @Test
            fun `should delete it too`() {
                assertEquals(scannedContents, runContents)
            }
        }

        class WhenScannedPagesJoinedTheRunDuringTheVisit {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 2
            private lateinit var scannedContents: List<String>
            private lateinit var runContents: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun discardTheVisit() = runTest {
                val staging = createStagingArea(folder)
                val screen = openTheCamera(staging)
                screen.photograph("photo 1")
                scannedContents = scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                screen.discardTheVisit()
                advanceUntilIdle()
                runContents = readContents(staging)
            }

            @Test
            fun `should keep them, since they exist nowhere else`() {
                assertEquals(scannedContents, runContents)
            }
        }

        @RunWith(Parameterized::class)
        class WhenSomethingHappensWhileTheDiscardWaits(
            private val row: String,
            private val wait: Wait,
            private val action: Action,
        ) {
            enum class Wait(
                val phrase: String,
                val endPhrase: String,
                val ownActions: List<Action>,
                private val start: suspend TestScope.(Visit) -> WaitingDiscard,
            ) {
                NO_PHOTO_ON_ITS_WAY("with no photo on its way", "the deletion ends", emptyList(), { visit ->
                    val release = holdTheStagingAreaLock(visit.staging)
                    visit.screen.discardTheVisit()
                    WaitingDiscard(visit, shotOnItsWay = null) { release() }
                }),
                PHOTO_BEING_WRITTEN(
                    "while a photo is being written",
                    "the photo is saved",
                    listOf(Action.PHOTO_FAILED, Action.CAMERA_CLOSED_THEN_PHOTO_WRITTEN_LATE),
                    { visit ->
                        val shot = visit.screen.takeAPhoto()
                        visit.screen.discardTheVisit()
                        WaitingDiscard(visit, shot) {
                            writeThePhoto(shot, "page on its way")
                            visit.screen.reportThePhotoSaved(shot)
                        }
                    },
                ),
                PHOTO_BEING_ADDED(
                    "while a photo is being added",
                    "the photo joins the run",
                    listOf(Action.PHOTO_NEVER_ENTERS_THE_RUN),
                    { visit ->
                        val shot = visit.screen.takeAPhoto()
                        writeThePhoto(shot, "page being added")
                        val release = holdTheStagingAreaLock(visit.staging)
                        visit.screen.reportThePhotoSaved(shot)
                        visit.screen.discardTheVisit()
                        WaitingDiscard(visit, shot) { release() }
                    },
                ),
                LATE_PHOTO(
                    "while a photo is written after the camera closed",
                    "the photo is written",
                    listOf(Action.PHOTO_NEVER_WRITTEN),
                    { visit ->
                        val shot = visit.screen.takeAPhoto()
                        visit.screen.reportTheCameraClosed(shot)
                        waitWhileTheCameraWritesThePhoto()
                        visit.screen.discardTheVisit()
                        WaitingDiscard(visit, shot) { writeThePhoto(shot, "late page") }
                    },
                ),
                ;

                internal suspend fun startTheDiscard(scope: TestScope, visit: Visit): WaitingDiscard =
                    scope.start(visit)
            }

            enum class Action(
                val phrase: String?,
                private val step: suspend TestScope.(WaitingDiscard) -> CameraScreen,
            ) {
                NOTHING(null, { discard ->
                    discard.endTheWait()
                    discard.visit.screen
                }),
                SHUTTER("the shutter is pressed", { discard ->
                    discard.visit.screen.pressTheShutter()
                    discard.endTheWait()
                    discard.visit.screen
                }),
                DONE_OR_KEEP("Done, or Keep in the leave dialog, is tapped", { discard ->
                    discard.visit.screen.leave()
                    discard.endTheWait()
                    discard.visit.screen
                }),
                DISCARD_AGAIN("the visit is discarded again", { discard ->
                    discard.visit.screen.discardTheVisit()
                    discard.endTheWait()
                    discard.visit.screen
                }),
                PHOTO_FAILED("the photo fails", { discard ->
                    val shot = requireNotNull(discard.shotOnItsWay) { "a photo fails only on its way" }
                    writeThePhoto(shot, "half a photo")
                    discard.visit.screen.reportThePhotoFailed(shot)
                    discard.visit.screen
                }),
                CAMERA_CLOSED_THEN_PHOTO_WRITTEN_LATE("the camera closes, then writes the photo late", { discard ->
                    val shot = requireNotNull(discard.shotOnItsWay) { "a camera closes only under a photo" }
                    discard.visit.screen.reportTheCameraClosed(shot)
                    waitWhileTheCameraWritesThePhoto()
                    writeThePhoto(shot, "late page")
                    discard.visit.screen
                }),
                PHOTO_NEVER_WRITTEN("the photo is never written", { discard ->
                    waitLongerThanTheCameraMayTakeToWriteThePhoto()
                    discard.visit.screen
                }),
                PHOTO_NEVER_ENTERS_THE_RUN("the photo never enters the run", { discard ->
                    val shot = requireNotNull(discard.shotOnItsWay) { "only a photo on its way can fail to join" }
                    leaveThePhotoEmpty(shot)
                    discard.endTheWait()
                    discard.visit.screen
                }),

                @OptIn(ExperimentalCoroutinesApi::class)
                SCREEN_STOPPED_THEN_RESUMED("the screen is stopped, then resumed", { discard ->
                    discard.visit.screen.stop()
                    discard.endTheWait()
                    advanceUntilIdle()
                    discard.visit.screen.resume()
                    discard.visit.screen
                }),
                PROCESS_ENDED("the process ends", { discard ->
                    discard.visit.screen.endTheProcess()
                    comeBackAfterTheEndOfTheProcess(discard.visit.folder, discard.visit.savedState)
                        .apply { discardTheVisit() }
                }),
                ;

                internal suspend fun takeItsStep(scope: TestScope, discard: WaitingDiscard): CameraScreen =
                    scope.step(discard)
            }

            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private val scannedPageCount = 2
            private lateinit var scannedContents: List<String>
            private lateinit var stateWhileItWaits: CaptureUiState
            private lateinit var stateAtTheEnd: CaptureUiState
            private var capturesWhileDiscarding by Delegates.notNull<Int>()
            private lateinit var closings: List<CameraClose>
            private lateinit var messages: List<CaptureMessage>
            private lateinit var runContents: List<String>

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun actWhileTheDiscardWaits() = runTest {
                val savedState = SavedStateHandle()
                val staging = createStagingArea(folder)
                scannedContents = scanPagesAsGoogleScannerDoes(staging, scannedPageCount)
                val screen = openTheCamera(staging, savedState)
                screen.photograph("first page")
                val discard = wait.startTheDiscard(this, Visit(screen, staging, folder, savedState))
                stateWhileItWaits = screen.awaitState { it.ready }
                val capturesBefore = screen.captureCount
                val screenAtTheEnd = action.takeItsStep(this, discard)
                advanceUntilIdle()
                capturesWhileDiscarding = screen.captureCount - capturesBefore
                stateAtTheEnd = screenAtTheEnd.state
                closings = screenAtTheEnd.closings
                messages = screenAtTheEnd.messages
                runContents = readContents(createStagingArea(folder))
            }

            @Test
            fun `should show the visit as being discarded, so that the screen offers nothing that would cancel it`() {
                assertTrue(row, stateWhileItWaits.isDiscarding)
            }

            @Test
            fun `should offer neither leaving, Done, the shutter nor another source while it waits`() {
                val offers = with(stateWhileItWaits) { listOf(canLeave, canFinish, canShoot, canSwitchSource) }
                assertEquals(row, listOf(false, false, false, false), offers)
            }

            @Test
            fun `should still show the visit as being discarded once its photos are deleted`() {
                assertTrue(row, stateAtTheEnd.isDiscarding)
            }

            @Test
            fun `should take no photo, since the visit's photos are being deleted`() {
                assertEquals(row, 0, capturesWhileDiscarding)
            }

            @Test
            fun `should delete the visit's photos only, keeping the scanned pages, which exist nowhere else`() {
                assertEquals(row, scannedContents, runContents)
            }

            @Test
            fun `should close the screen once, without the photos, since discarding was the user's last choice`() {
                assertEquals(row, listOf(CameraClose(werePhotosKept = false)), closings)
            }

            @Test
            fun `should say nothing, since a photo of a discarded visit is no loss`() {
                assertEquals(row, emptyList<CaptureMessage>(), messages)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun rows(): List<Array<Any>> = Wait.entries.flatMap { wait ->
                    val actions = listOf(
                        Action.NOTHING,
                        Action.SHUTTER,
                        Action.DONE_OR_KEEP,
                        Action.DISCARD_AGAIN,
                        Action.SCREEN_STOPPED_THEN_RESUMED,
                        Action.PROCESS_ENDED,
                    ) + wait.ownActions
                    actions.map { action ->
                        arrayOf<Any>("${wait.phrase}, ${action.phrase ?: wait.endPhrase}", wait, action)
                    }
                }
            }
        }

        @RunWith(Parameterized::class)
        class WhenAPhotoResistsItsDeletionWhileTheDiscardWaits(
            private val row: String,
            private val wait: WhenSomethingHappensWhileTheDiscardWaits.Wait,
        ) {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var state: CaptureUiState
            private lateinit var closings: List<CameraClose>
            private lateinit var messages: List<CaptureMessage>
            private var isPhotoTaken by Delegates.notNull<Boolean>()

            @OptIn(ExperimentalCoroutinesApi::class)
            @Before
            fun endTheWait() = runTest {
                val savedState = SavedStateHandle()
                val staging = createStagingArea(folder)
                val screen = openTheCamera(staging, savedState)
                screen.photograph("first page")
                makeUndeletable(screen.awaitState { it.pages.size == 1 }.pages.single())
                wait.startTheDiscard(this, Visit(screen, staging, folder, savedState)).endTheWait()
                advanceUntilIdle()
                state = screen.state
                closings = screen.closings
                messages = screen.messages
                isPhotoTaken = screen.pressTheShutter()
            }

            @Test
            fun `should say that photos were not deleted`() {
                assertEquals(row, listOf<CaptureMessage>(CaptureMessage.PhotosNotDeleted), messages)
            }

            @Test
            fun `should not close the screen, so that the user sees the photos left`() {
                assertEquals(row, emptyList<CameraClose>(), closings)
            }

            @Test
            fun `should no longer be discarding, so that the user can leave or discard again`() {
                assertFalse(row, state.isDiscarding)
            }

            @Test
            fun `should take photos again`() {
                assertTrue(row, isPhotoTaken)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun rows(): List<Array<Any>> = WhenSomethingHappensWhileTheDiscardWaits.Wait.entries.map { wait ->
                    arrayOf<Any>(wait.phrase, wait)
                }
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
        private lateinit var runContents: List<String>

        @OptIn(ExperimentalCoroutinesApi::class)
        @Before
        fun discardTheVisit() = runTest {
            val staging = createStagingArea(folder)
            val screen = openTheCamera(staging)
            screen.photograph("first page")
            val shot = screen.takeAPhoto()
            writeThePhoto(shot, "page on its way")
            screen.discardTheVisit()
            screen.reportThePhotoSaved(shot)
            state = screen.awaitState { !it.shooting && it.pages.isEmpty() }
            advanceUntilIdle()
            closingCount = screen.closingCount
            messages = screen.messages
            runContents = readContents(staging)
        }

        @Test
        fun `should delete the photo on its way too`() {
            assertEquals(emptyList<String>(), runContents)
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
private const val OTHER_DOCUMENT_ID = "0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d"
private val CLOCK: Clock = Clock.fixed(Instant.parse("2026-10-12T18:30:00Z"), ZoneOffset.UTC)

// In the test's virtual time: a press that the shutter refused fails its hook at once.
private const val SHOT_WAIT_MILLISECONDS = 1_000L

private const val WAIT_MARGIN_MILLISECONDS = 1_000L

// Internal, not private: the public discard table's rows take and return them in the members its group calls.
internal class Visit(
    val screen: CameraScreen,
    val staging: StagingArea,
    val folder: TemporaryFolder,
    val savedState: SavedStateHandle,
)

internal class WaitingDiscard(val visit: Visit, val shotOnItsWay: Shot?, val endTheWait: suspend () -> Unit)

internal class CameraScreen(
    val viewModel: CaptureViewModel,
    private val viewModels: ViewModelStore,
    private val scope: CoroutineScope,
) {
    private val receivedMessages = mutableListOf<CaptureMessage>()
    private val shots = Channel<Shot>(Channel.UNLIMITED)

    private val receivedClosings = mutableListOf<CameraClose>()

    /** Each close of the screen, which it handles at once while it is in front, as the nav host closes it. */
    val closings: List<CameraClose> get() = receivedClosings.toList()

    val closingCount: Int get() = receivedClosings.size

    var captureCount = 0
        private set

    val messages: List<CaptureMessage> get() = receivedMessages.toList()

    val state: CaptureUiState get() = viewModel.uiState.value

    private var closingsCollection: Job = closeWhenAsked()

    init {
        scope.launch { viewModel.messages.collect { receivedMessages += it } }
    }

    private fun closeWhenAsked(): Job = scope.launch {
        viewModel.uiState.collect { uiState ->
            uiState.closing?.let { close ->
                receivedClosings += close
                viewModel.onCloseHandled(close)
            }
        }
    }

    fun stop() {
        closingsCollection.cancel()
    }

    fun resume() {
        closingsCollection = closeWhenAsked()
    }

    // Only the view model's cancellable work stops: what it runs NonCancellable goes on, as it would
    // not in a process that ends.
    fun endTheProcess() {
        viewModels.clear()
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

/*
 * The sending of another document's run holds the staging area's one lock, and touches nothing of
 * this document's run. In the background: a lock that a test never releases ends with it. Its
 * release waits for the lock to be free, since advanceUntilIdle() does not wait for background work.
 */
private suspend fun TestScope.holdTheStagingAreaLock(staging: StagingArea): suspend () -> Unit {
    val isHeld = CompletableDeferred<Unit>()
    val gate = CompletableDeferred<Unit>()
    val sending = backgroundScope.launch {
        staging.send(OTHER_DOCUMENT_ID) {
            isHeld.complete(Unit)
            gate.await()
        }
    }
    isHeld.await()
    return {
        gate.complete(Unit)
        sending.join()
    }
}

private suspend fun readContents(staging: StagingArea): List<String> =
    staging.pages(DOCUMENT_ID).map { it.file.readText() }

private suspend fun scanPagesAsGoogleScannerDoes(staging: StagingArea, count: Int): List<String> =
    (1..count).map { number ->
        val content = "scanned page $number"
        val file = staging.incomingFile(DOCUMENT_ID).apply { writeText(content) }
        staging.add(DOCUMENT_ID, listOf(StagingInput(file, CLOCK.instant())))
        content
    }

private fun TestScope.createTheCameraViewModel(
    staging: StagingArea,
    savedState: SavedStateHandle,
    viewModels: ViewModelStore,
): CaptureViewModel {
    val dispatcher = io
    val factory =
        viewModelFactory { initializer { CaptureViewModel(savedState, DOCUMENT_ID, staging, CLOCK, dispatcher) } }
    return ViewModelProvider.create(viewModels, factory)[CaptureViewModel::class]
}

@OptIn(ExperimentalCoroutinesApi::class)
private suspend fun TestScope.openTheCamera(
    staging: StagingArea,
    savedState: SavedStateHandle = SavedStateHandle(),
): CameraScreen {
    val viewModels = ViewModelStore()
    val viewModel = createTheCameraViewModel(staging, savedState, viewModels)
    val screen = CameraScreen(viewModel, viewModels, backgroundScope + UnconfinedTestDispatcher(testScheduler))
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

/* As a file the system holds, which the app cannot delete. */
private fun makeUndeletable(page: StagedPage) {
    page.file.delete()
    File(page.file, "held").apply { parentFile?.mkdirs() }.writeText("held")
}

private fun writeThePhoto(shot: Shot, content: String) {
    shot.file.writeText(content)
}

private fun leaveThePhotoEmpty(shot: Shot) {
    shot.file.writeText("")
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

@OptIn(ExperimentalCoroutinesApi::class)
private fun TestScope.waitLongerThanTheCameraMayTakeToWriteThePhoto() {
    advanceTimeBy(CaptureViewModel.LATE_PHOTO_WAIT_MS + WAIT_MARGIN_MILLISECONDS)
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
