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
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
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

data class CameraClose(val werePhotosKept: Boolean)

data class CaptureUiState(
    /**
     * The photos of this visit to the camera, those of a visit interrupted by the end of the
     * process included: the only pages this screen shows or deletes.
     */
    val pages: List<StagedPage> = emptyList(),
    /**
     * Pages of the run that this visit did not take (scanned, imported, or photographed in an
     * earlier visit, before this one or during it): they wait to be sent, and this screen never
     * touches them.
     */
    val waiting: Int = 0,
    /** Off by default: on paper, the flash mostly adds glare. */
    val flash: FlashSetting = FlashSetting.OFF,
    /** A photo is being taken and saved: the shutter waits for it. */
    val shooting: Boolean = false,
    /** The user is done: the screen closes once the photo being saved has joined the run. */
    val finishing: Boolean = false,
    /**
     * The user chose to discard the visit: its photos are being deleted, and the screen closes
     * once they are. Nothing the screen offers may cancel that choice meanwhile.
     */
    val isDiscarding: Boolean = false,
    /** The run is read: until then, the screen cannot tell what the user may lose. */
    val ready: Boolean = false,
    /**
     * The screen must close. Kept until the screen has closed, so that a close set while the
     * screen is not in front waits for it.
     */
    val closing: CameraClose? = null,
) {
    /** Photos of this visit, saved or on their way: leaving the screen must not lose them. */
    val photoCount: Int get() = pages.size + if (shooting) 1 else 0

    val canLeave: Boolean get() = isStaying(isDiscarding, closing)

    val canFinish: Boolean get() = photoCount > 0 && !finishing && isStaying(isDiscarding, closing)

    val canShoot: Boolean get() = ready && isShutterFree(shooting, finishing, isDiscarding, closing)

    /** Not while the visit is discarded: another source would close the screen with its photos. */
    val canSwitchSource: Boolean get() = !isDiscarding
}

/** One-off messages shown in a snackbar. */
sealed interface CaptureMessage {
    data object ShotFailed : CaptureMessage

    /** The photo could not be written: the phone may be out of storage. */
    data object ShotNotSaved : CaptureMessage

    /** Some photos of the visit could not be deleted: they stay, and the screen with them. */
    data object PhotosNotDeleted : CaptureMessage
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
    /** The dispatcher of the disk's work; tests give their own, to run it in a fixed order. */
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : ViewModel() {

    private val shooting = MutableStateFlow(false)
    private val finishing = MutableStateFlow(false)
    private val isDiscarding = MutableStateFlow(false)
    private val closing = MutableStateFlow<CameraClose?>(null)
    private val messageChannel = Channel<CaptureMessage>(Channel.BUFFERED)

    /**
     * The file names of the photos this visit added to the run: scanned pages or photos imported
     * meanwhile join the run too, and this screen must never show or delete them. Saved with the
     * screen, so that it survives the end of the process.
     */
    private val visitPhotoNames: StateFlow<List<String>> = savedState.getStateFlow(KEY_VISIT_PHOTOS, emptyList())

    val messages: Flow<CaptureMessage> = messageChannel.receiveAsFlow()

    private val progress: Flow<Progress> = combine(shooting, finishing, isDiscarding, closing, ::Progress)

    val uiState: StateFlow<CaptureUiState> = combine(
        staging.observe(documentId),
        visitPhotoNames,
        savedState.getStateFlow(KEY_FLASH, FlashSetting.OFF.name),
        progress,
    ) { run, photoNameList, flashName, visitProgress ->
        val photoNames = photoNameList.toSet()
        val visit = run.filter { it.file.name in photoNames }
        CaptureUiState(
            pages = visit,
            waiting = run.size - visit.size,
            flash = storedEnum(flashName, FlashSetting.OFF),
            shooting = visitProgress.shooting,
            finishing = visitProgress.finishing,
            isDiscarding = visitProgress.isDiscarding,
            ready = true,
            closing = visitProgress.closing,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), CaptureUiState())

    fun cycleFlash() {
        savedState[KEY_FLASH] = uiState.value.flash.next.name
    }

    /**
     * Takes a photo: [capture] must start writing it to the shot's file, then report the outcome
     * with [onShotSaved] or [onShotFailed]. Does nothing and returns false while the previous
     * photo is still being taken, so that a double tap does not take the same page twice, and once
     * the user is done or discards the visit, or the screen closes.
     */
    fun shoot(capture: (Shot) -> Unit): Boolean {
        if (!isShutterFree(shooting.value, finishing.value, isDiscarding.value, closing.value)) return false
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
            if (error.isCameraClosed() && awaitPhoto(shot.file)) {
                Log.i(TAG, "photo written after the camera closed")
                keep(shot)
                return@launch
            }
            deleteQuietly(shot.file)
            val notWritten = error is ImageCaptureException && error.imageCaptureError == ImageCapture.ERROR_FILE_IO
            fail(error, if (notWritten) CaptureMessage.ShotNotSaved else CaptureMessage.ShotFailed)
        }
    }

    /** Adds the photo written for [shot] to the run, then closes the screen if the user is done. */
    private suspend fun keep(shot: Shot) {
        try {
            val added = staging.add(documentId, listOf(StagingInput(shot.file, shot.takenAt)))
            savedState[KEY_VISIT_PHOTOS] = ArrayList(visitPhotoNames.value + added.map { it.file.name })
            shooting.value = false
            if (finishing.value) close(werePhotosKept = true)
        } catch (e: IOException) {
            deleteQuietly(shot.file)
            fail(e, CaptureMessage.ShotNotSaved)
        }
    }

    private suspend fun fail(error: Exception, message: CaptureMessage) {
        Log.w(TAG, "photo not taken", error)
        shooting.value = false
        // The user stays to see what happened, and to take the photo again.
        finishing.value = false
        // A photo of a discarded visit goes nowhere: its loss is no news.
        if (!isDiscarding.value) messageChannel.send(message)
    }

    /**
     * Closes the screen, keeping the photos: right away, or once the photo being taken has joined
     * the run. If that photo fails instead, the screen stays, to say so. Does nothing while the
     * visit is discarded, or the screen closes already.
     */
    fun finish() {
        if (!isStaying(isDiscarding.value, closing.value)) return
        if (shooting.value) finishing.value = true else close(werePhotosKept = true)
    }

    private fun close(werePhotosKept: Boolean) {
        finishing.value = false
        closing.value = CameraClose(werePhotosKept)
    }

    /** The screen closed for [close]: a close set since then still waits. */
    fun onCloseHandled(close: CameraClose) {
        closing.compareAndSet(close, null)
    }

    /** Deletes a photo of this visit, e.g. a blurred one, to take it again. */
    fun deletePage(page: StagedPage) {
        viewModelScope.launch {
            try {
                staging.remove(documentId, page)
            } catch (e: IOException) {
                Log.w(TAG, "photo not deleted", e)
            }
        }
    }

    /**
     * Deletes the photos of this visit, the one on its way included, then closes the screen, once. If
     * a photo cannot be deleted, the screen stays to say so, with the photos left.
     */
    fun discard() {
        if (isDiscarding.value) return
        finishing.value = false
        isDiscarding.value = true
        viewModelScope.launch {
            // Once the photo on its way has joined the run, or failed, the visit names all its photos.
            shooting.first { !it }
            if (!withContext(NonCancellable) { deleteTheVisitPhotos() }) {
                isDiscarding.value = false
                messageChannel.send(CaptureMessage.PhotosNotDeleted)
                return@launch
            }
            close(werePhotosKept = false)
        }
    }

    /** Whether every photo of this visit is deleted: a photo that resists leaves the others deleted. */
    private suspend fun deleteTheVisitPhotos(): Boolean {
        val photoNames = visitPhotoNames.value.toSet()
        var isEveryPhotoDeleted = true
        for (photo in staging.pages(documentId).filter { it.file.name in photoNames }) {
            try {
                staging.remove(documentId, photo)
            } catch (e: IOException) {
                Log.w(TAG, "photo not deleted", e)
                isEveryPhotoDeleted = false
            }
        }
        return isEveryPhotoDeleted
    }

    /** Whether CameraX's [photo] file appears complete within [LATE_PHOTO_WAIT_MS]. */
    private suspend fun awaitPhoto(photo: File): Boolean {
        // CameraX writes a temporary file, then renames it: once there, the photo is complete.
        repeat(LATE_PHOTO_WAIT_MS / LATE_PHOTO_POLL_MS) {
            if (withContext(io) { photo.length() > 0 }) return true
            delay(LATE_PHOTO_POLL_MS.toLong())
        }
        return withContext(io) { photo.length() > 0 }
    }

    private suspend fun deleteQuietly(file: File) {
        withContext(NonCancellable + io) { file.delete() }
    }

    companion object {
        private const val TAG = "Capture"
        private const val KEY_FLASH = "capture_flash"
        private const val KEY_VISIT_PHOTOS = "capture_visit_photos"

        /** How long a photo whose camera closed may take to appear: its JPEG and EXIF writing. */
        internal const val LATE_PHOTO_WAIT_MS = 5_000
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

private data class Progress(
    val shooting: Boolean,
    val finishing: Boolean,
    val isDiscarding: Boolean,
    val closing: CameraClose?,
)

private fun isShutterFree(shooting: Boolean, finishing: Boolean, isDiscarding: Boolean, closing: CameraClose?) =
    !shooting && !finishing && isStaying(isDiscarding, closing)

/**
 * Not while the visit is discarded, which leaving or keeping its photos would cancel, nor once a
 * close waits for the screen, which closes it already.
 */
private fun isStaying(isDiscarding: Boolean, closing: CameraClose?) = !isDiscarding && closing == null

/** CameraX closed the camera before the photo was saved: the screen left, the phone locked... */
private fun Exception.isCameraClosed(): Boolean =
    this is ImageCaptureException && imageCaptureError == ImageCapture.ERROR_CAMERA_CLOSED
