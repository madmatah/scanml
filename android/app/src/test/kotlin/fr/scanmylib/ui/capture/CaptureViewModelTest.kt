package fr.scanmylib.ui.capture

import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.lifecycle.SavedStateHandle
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.StagingInput
import java.io.File
import java.time.Clock
import java.time.Instant
import java.time.ZoneOffset
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
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
        val closingCount = MutableStateFlow(0)
        val messages = mutableListOf<CaptureMessage>()

        /** Waits for the screen to be told to close: deleting photos takes the disk's time. */
        suspend fun awaitClosed() {
            closingCount.first { it > 0 }
        }

        /** Takes a photo and returns it once its file is chosen, as the camera receives it. */
        suspend fun shoot(): Shot {
            // The shutter waits for the start of the visit, as on the screen.
            awaitState { it.ready }
            val shot = CompletableDeferred<Shot>()
            assertTrue(viewModel.shoot { shot.complete(it) })
            return shot.await()
        }

        suspend fun awaitState(predicate: (CaptureUiState) -> Boolean): CaptureUiState =
            viewModel.uiState.first(predicate)
    }

    private val stagingRoot get() = File(folder.root, "staging")

    /**
     * The camera screen, on the document's run in [staging], restored from [savedState] if given,
     * once it knows where its visit starts: that read runs on the IO dispatcher, and must not
     * resume on the main dispatcher after the test has reset it.
     */
    private suspend fun TestScope.screen(
        staging: StagingArea = StagingArea(stagingRoot),
        savedState: SavedStateHandle = SavedStateHandle(),
    ): Screen {
        val screen = Screen(CaptureViewModel(savedState, document, staging, clock))
        val collector = UnconfinedTestDispatcher(testScheduler)
        backgroundScope.launch(collector) {
            screen.viewModel.closed.collect {
                screen.closings += it
                screen.closingCount.value++
            }
        }
        backgroundScope.launch(collector) { screen.viewModel.messages.collect { screen.messages += it } }
        screen.awaitState { it.ready }
        return screen
    }

    /** A run of [count] pages scanned before the camera opens, as with Google's scanner. */
    private suspend fun StagingArea.scanned(count: Int): List<String> = (1..count).map { n ->
        val content = "scanned page $n"
        val file = incomingFile(document).apply { writeText(content) }
        add(document, listOf(StagingInput(file, clock.instant())))
        content
    }

    private suspend fun StagingArea.contents(): List<String> = pages(document).map { it.file.readText() }

    /** Takes a photo of [content] and waits for it to join the visit. */
    private suspend fun Screen.photograph(content: String) {
        val shot = shoot()
        shot.file.writeText(content)
        viewModel.onShotSaved(shot)
        awaitState { !it.shooting && it.pages.any { page -> page.file.readText() == content } }
    }

    @Test
    fun `with no photo of its own, the visit has nothing to keep or delete, and the draft stays`() = runTest {
        val staging = StagingArea(stagingRoot)
        val scanned = staging.scanned(5)
        val screen = screen(staging)

        val state = screen.awaitState { it.ready }
        assertEquals(emptyList<Any>(), state.pages)
        assertEquals(5, state.waiting)
        // Closing does not ask: the screen closes at once.
        assertEquals(0, state.photoCount)

        screen.viewModel.discard()
        screen.awaitClosed()
        assertEquals(listOf(Unit), screen.closings)
        assertEquals(scanned, staging.contents())
    }

    @Test
    fun `discarding deletes this visit's photos only`() = runTest {
        val staging = StagingArea(stagingRoot)
        val scanned = staging.scanned(5)
        val screen = screen(staging)
        screen.photograph("photo 1")

        val state = screen.awaitState { it.pages.size == 1 }
        assertEquals(5, state.waiting)
        // The last photo is this visit's, never a page from before it.
        assertEquals("photo 1", state.pages.last().file.readText())

        screen.viewModel.discard()
        screen.awaitClosed()
        assertEquals(listOf(Unit), screen.closings)
        assertEquals(scanned, staging.contents())
    }

    @Test
    fun `deleting the last photo leaves the pages from before the visit`() = runTest {
        val staging = StagingArea(stagingRoot)
        val scanned = staging.scanned(2)
        val screen = screen(staging)
        screen.photograph("blurred")

        screen.viewModel.deletePage(screen.awaitState { it.pages.size == 1 }.pages.single())
        val state = screen.awaitState { it.pages.isEmpty() }
        assertEquals(2, state.waiting)
        assertEquals(scanned, staging.contents())
        // The photo taken again is this visit's.
        screen.photograph("sharp")
        assertEquals(listOf("sharp"), screen.awaitState { it.pages.size == 1 }.pages.map { it.file.readText() })
    }

    @Test
    fun `the start of the visit survives the end of the process`() = runTest {
        val staging = StagingArea(stagingRoot)
        staging.scanned(5)
        val savedState = SavedStateHandle()
        screen(staging, savedState).photograph("photo 1")

        // The process ends; the screen comes back with its saved state, on the files left on disk.
        val restored = SavedStateHandle(savedState.keys().associateWith { savedState.get<Any?>(it) })
        val state = screen(StagingArea(stagingRoot), restored).awaitState { it.ready }
        assertEquals(listOf("photo 1"), state.pages.map { it.file.readText() })
        assertEquals(5, state.waiting)

        // A new visit to the camera starts after that photo.
        val newVisit = screen(StagingArea(stagingRoot)).awaitState { it.ready }
        assertEquals(emptyList<Any>(), newVisit.pages)
        assertEquals(6, newVisit.waiting)
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
    fun `discarding the visit discards the photo on its way too`() = runTest {
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
