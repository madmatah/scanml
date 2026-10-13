package fr.scanmylib.ui.capture

import android.util.Log
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.toRoute
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.StagingInput
import fr.scanmylib.settings.storedEnum
import fr.scanmylib.ui.CaptureRoute
import fr.scanmylib.ui.container
import java.io.File
import java.io.IOException
import java.time.Clock
import java.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Flash setting of the camera screen, cycled by its button. */
enum class FlashSetting(val imageCaptureMode: Int) {
    OFF(ImageCapture.FLASH_MODE_OFF),
    AUTO(ImageCapture.FLASH_MODE_AUTO),
    ON(ImageCapture.FLASH_MODE_ON),
    ;

    val next: FlashSetting get() = entries[(ordinal + 1) % entries.size]
}

/** A photo being taken: the camera writes it to [file]. */
data class Shot(val file: File, val takenAt: Instant)

data class CaptureUiState(
    /** The photos of the run so far, those of an interrupted visit included. */
    val pages: List<StagedPage> = emptyList(),
    /** Off by default: on paper, the flash mostly adds glare. */
    val flash: FlashSetting = FlashSetting.OFF,
    /** A photo is being taken and saved: the shutter waits for it. */
    val shooting: Boolean = false,
    /** The user is done: the screen closes once the photo being saved has joined the run. */
    val finishing: Boolean = false,
) {
    /** Photos of the run, saved or on their way: leaving the screen must not lose them. */
    val photoCount: Int get() = pages.size + if (shooting) 1 else 0
}

/** One-off messages shown in a snackbar. */
sealed interface CaptureMessage {
    data object ShotFailed : CaptureMessage

    /** The photo could not be written: the phone may be out of storage. */
    data object ShotNotSaved : CaptureMessage
}

/**
 * The camera screen: photos taken one after the other, each saved at full resolution, untouched,
 * straight into the document's run ([StagingArea]), where it waits for the user to send it.
 */
class CaptureViewModel(
    private val savedState: SavedStateHandle,
    private val documentId: String,
    private val staging: StagingArea,
    private val clock: Clock,
) : ViewModel() {

    private val shooting = MutableStateFlow(false)
    private val finishing = MutableStateFlow(false)
    private val messageChannel = Channel<CaptureMessage>(Channel.BUFFERED)
    private val closedChannel = Channel<Unit>(Channel.CONFLATED)

    /** The photo being taken, once its file is chosen. */
    private var currentShot: Shot? = null

    /** Photos still on their way when the run was discarded: they go nowhere. */
    private val abandonedShots = mutableSetOf<Shot>()

    val messages: Flow<CaptureMessage> = messageChannel.receiveAsFlow()

    /** Emits when the screen must close: the run is kept ([finish]) or discarded ([discard]). */
    val closed: Flow<Unit> = closedChannel.receiveAsFlow()

    val uiState: StateFlow<CaptureUiState> = combine(
        staging.observe(documentId),
        savedState.getStateFlow(KEY_FLASH, FlashSetting.OFF.name),
        shooting,
        finishing,
    ) { pages, flash, shooting, finishing ->
        CaptureUiState(pages, storedEnum(flash, FlashSetting.OFF), shooting, finishing)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), CaptureUiState())

    fun cycleFlash() {
        savedState[KEY_FLASH] = uiState.value.flash.next.name
    }

    /**
     * Takes a photo: [capture] must start writing it to the shot's file, then report the outcome
     * with [onShotSaved] or [onShotFailed]. Does nothing and returns false while the previous
     * photo is still being taken, so that a double tap does not take the same page twice, and once
     * the user is done.
     */
    fun shoot(capture: (Shot) -> Unit): Boolean {
        if (shooting.value || finishing.value) return false
        shooting.value = true
        val takenAt = clock.instant()
        viewModelScope.launch {
            val file = try {
                staging.incomingFile(documentId)
            } catch (e: IOException) {
                fail(e, CaptureMessage.ShotNotSaved)
                return@launch
            }
            val shot = Shot(file, takenAt)
            currentShot = shot
            try {
                capture(shot)
            } catch (e: IllegalStateException) {
                // The camera is not ready, or no longer.
                onShotFailed(shot, e)
            }
        }
        return true
    }

    fun onShotSaved(shot: Shot) {
        viewModelScope.launch { keep(shot) }
    }

    fun onShotFailed(shot: Shot, error: Exception) {
        viewModelScope.launch {
            // The camera closed under the photo (the phone locked, the app left...): CameraX does
            // not report a photo it was already writing, but finishes writing it all the same.
            if (shot !in abandonedShots && error.isCameraClosed() && awaitPhoto(shot.file)) {
                Log.i(TAG, "photo written after the camera closed")
                keep(shot)
                return@launch
            }
            deleteQuietly(shot.file)
            if (abandon(shot)) return@launch
            val notWritten = error is ImageCaptureException && error.imageCaptureError == ImageCapture.ERROR_FILE_IO
            fail(error, if (notWritten) CaptureMessage.ShotNotSaved else CaptureMessage.ShotFailed)
        }
    }

    /** Adds the photo written for [shot] to the run, then closes the screen if the user is done. */
    private suspend fun keep(shot: Shot) {
        if (abandon(shot)) {
            deleteQuietly(shot.file)
            return
        }
        try {
            staging.add(documentId, listOf(StagingInput(shot.file, shot.takenAt)))
            shotDone(shot)
            if (finishing.value) close()
        } catch (e: IOException) {
            deleteQuietly(shot.file)
            fail(e, CaptureMessage.ShotNotSaved)
        }
    }

    /** True if [shot] belongs to a discarded run: it is then done with, silently. */
    private fun abandon(shot: Shot): Boolean {
        if (!abandonedShots.remove(shot)) return false
        shotDone(shot)
        return true
    }

    private fun shotDone(shot: Shot) {
        if (currentShot == shot) currentShot = null
        shooting.value = false
    }

    private suspend fun fail(error: Exception, message: CaptureMessage) {
        Log.w(TAG, "photo not taken", error)
        currentShot = null
        shooting.value = false
        // The user stays to see what happened, and to take the photo again.
        finishing.value = false
        messageChannel.send(message)
    }

    /**
     * Closes the screen, keeping the photos: right away, or once the photo being taken has joined
     * the run. If that photo fails instead, the screen stays, to say so.
     */
    fun finish() {
        if (shooting.value) finishing.value = true else close()
    }

    private fun close() {
        finishing.value = false
        closedChannel.trySend(Unit)
    }

    /** Deletes a photo of the run, e.g. a blurred one, to take it again. */
    fun deletePage(page: StagedPage) {
        viewModelScope.launch {
            try {
                staging.remove(documentId, page)
            } catch (e: IOException) {
                Log.w(TAG, "photo not deleted", e)
            }
        }
    }

    /** Deletes all the photos of the run, the one on its way included, then emits [closed]. */
    fun discard() {
        currentShot?.let(abandonedShots::add)
        finishing.value = false
        viewModelScope.launch {
            withContext(NonCancellable) { staging.discard(documentId) }
            closedChannel.send(Unit)
        }
    }

    /** Whether CameraX's [photo] file appears complete within [LATE_PHOTO_WAIT_MS]. */
    private suspend fun awaitPhoto(photo: File): Boolean {
        // CameraX writes a temporary file, then renames it: once there, the photo is complete.
        repeat(LATE_PHOTO_WAIT_MS / LATE_PHOTO_POLL_MS) {
            if (withContext(Dispatchers.IO) { photo.length() > 0 }) return true
            delay(LATE_PHOTO_POLL_MS.toLong())
        }
        return withContext(Dispatchers.IO) { photo.length() > 0 }
    }

    private suspend fun deleteQuietly(file: File) {
        withContext(NonCancellable + Dispatchers.IO) { file.delete() }
    }

    companion object {
        private const val TAG = "Capture"
        private const val KEY_FLASH = "capture_flash"

        /** How long a photo whose camera closed may take to appear: its JPEG and EXIF writing. */
        private const val LATE_PHOTO_WAIT_MS = 5_000
        private const val LATE_PHOTO_POLL_MS = 100

        val Factory = viewModelFactory {
            initializer {
                val container = this.container
                val savedState = createSavedStateHandle()
                val documentId = savedState.toRoute<CaptureRoute>().documentId
                CaptureViewModel(savedState, documentId, container.staging, container.clock)
            }
        }
    }
}

/** CameraX closed the camera before the photo was saved: the screen left, the phone locked... */
private fun Exception.isCameraClosed(): Boolean =
    this is ImageCaptureException && imageCaptureError == ImageCapture.ERROR_CAMERA_CLOSED
