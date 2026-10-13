package fr.scanmylib.ui.capture

import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.lifecycle.SavedStateHandle
import fr.scanmylib.library.StagingArea
import java.io.File
import java.time.Clock
import java.time.Instant
import java.time.ZoneOffset
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class CaptureViewModelTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val document = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
    private val clock = Clock.fixed(Instant.parse("2026-10-12T18:30:00Z"), ZoneOffset.UTC)
    private val cameraClosed = ImageCaptureException(ImageCapture.ERROR_CAMERA_CLOSED, "Camera is closed.", null)

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    /** The view model, with what it tells the screen: closings and messages. */
    private class Screen(val viewModel: CaptureViewModel) {
        val closings = mutableListOf<Unit>()
        val messages = mutableListOf<CaptureMessage>()

        /** Takes a photo and returns it once its file is chosen, as the camera receives it. */
        suspend fun shoot(): Shot {
            val shot = CompletableDeferred<Shot>()
            assertTrue(viewModel.shoot { shot.complete(it) })
            return shot.await()
        }

        suspend fun awaitState(predicate: (CaptureUiState) -> Boolean): CaptureUiState =
            viewModel.uiState.first(predicate)
    }

    private fun TestScope.screen(): Screen {
        val screen = Screen(CaptureViewModel(SavedStateHandle(), document, StagingArea(File(folder.root, "staging")), clock))
        val collector = UnconfinedTestDispatcher(testScheduler)
        backgroundScope.launch(collector) { screen.viewModel.closed.collect { screen.closings += it } }
        backgroundScope.launch(collector) { screen.viewModel.messages.collect { screen.messages += it } }
        return screen
    }

    @Test
    fun `leaving while a photo is being saved waits for it to join the run`() = runTest {
        val screen = screen()
        val shot = screen.shoot()
        // A second tap while the photo is being saved takes nothing.
        assertFalse(screen.viewModel.shoot { error("second photo") })

        screen.viewModel.finish()
        assertTrue(screen.awaitState { it.finishing }.shooting)
        assertEquals(emptyList<Unit>(), screen.closings)

        shot.file.writeText("last page") // written by the camera
        screen.viewModel.onShotSaved(shot)
        val state = screen.awaitState { it.pages.size == 1 && !it.shooting }
        assertEquals("last page", state.pages.single().file.readText())
        assertFalse(state.finishing)
        assertEquals(listOf(Unit), screen.closings)
        assertEquals(emptyList<CaptureMessage>(), screen.messages)
    }

    @Test
    fun `with no photo on its way, leaving is immediate`() = runTest {
        val screen = screen()
        screen.viewModel.finish()
        assertEquals(listOf(Unit), screen.closings)
    }

    @Test
    fun `a photo that fails while leaving keeps the screen open, to say so`() = runTest {
        val screen = screen()
        val shot = screen.shoot()
        screen.viewModel.finish()

        screen.viewModel.onShotFailed(shot, ImageCaptureException(ImageCapture.ERROR_CAPTURE_FAILED, "failed", null))
        val state = screen.awaitState { !it.shooting }
        assertFalse(state.finishing)
        assertTrue(state.pages.isEmpty())
        assertEquals(listOf<CaptureMessage>(CaptureMessage.ShotFailed), screen.messages)
        assertEquals(emptyList<Unit>(), screen.closings)
        assertFalse(shot.file.exists())
        // The photo can be taken again.
        screen.shoot()
    }

    @Test
    fun `a photo the camera writes after closing still joins the run`() = runTest {
        val screen = screen()
        val shot = screen.shoot()

        // The phone was locked during the save: CameraX reports the camera closed, then finishes
        // writing the photo all the same.
        screen.viewModel.onShotFailed(shot, cameraClosed)
        shot.file.writeText("page")

        val state = screen.awaitState { it.pages.size == 1 && !it.shooting }
        assertEquals("page", state.pages.single().file.readText())
        assertEquals(emptyList<CaptureMessage>(), screen.messages)
    }

    @Test
    fun `a photo the camera never writes is reported lost`() = runTest {
        val screen = screen()
        val shot = screen.shoot()

        screen.viewModel.onShotFailed(shot, cameraClosed)
        val state = screen.awaitState { !it.shooting }
        assertTrue(state.pages.isEmpty())
        assertEquals(listOf<CaptureMessage>(CaptureMessage.ShotFailed), screen.messages)
        assertFalse(shot.file.exists())
    }

    @Test
    fun `discarding the run discards the photo on its way too`() = runTest {
        val screen = screen()
        val first = screen.shoot()
        first.file.writeText("first page")
        screen.viewModel.onShotSaved(first)
        screen.awaitState { it.pages.size == 1 && !it.shooting }

        // The camera has written the next photo, but not reported it yet.
        val shot = screen.shoot()
        shot.file.writeText("page on its way")
        screen.viewModel.discard()
        screen.viewModel.onShotSaved(shot)

        val state = screen.awaitState { !it.shooting && it.pages.isEmpty() }
        assertFalse(state.finishing)
        assertFalse(shot.file.exists())
        assertEquals(listOf(Unit), screen.closings)
        assertEquals(emptyList<CaptureMessage>(), screen.messages)
        // Should the screen stay (closing it was dropped), photos can still be taken.
        screen.shoot()
    }
}
