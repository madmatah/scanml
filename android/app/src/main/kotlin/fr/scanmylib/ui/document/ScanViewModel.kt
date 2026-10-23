package fr.scanmylib.ui.document

import android.net.Uri
import android.util.Log
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.toRoute
import fr.scanmylib.library.CopySource
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.library.PhotoImportResult
import fr.scanmylib.library.Preparation
import fr.scanmylib.library.PreparationOutcome
import fr.scanmylib.library.RunPreparation
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.isStorageFull
import fr.scanmylib.library.isStorageLow
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.ui.DocumentRoute
import fr.scanmylib.ui.container
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Adding pages: "Scan" opens a camera at once and "Import" the photo picker, with no question
 * before; the pages of the run then wait on the phone, with their optional numbering, until the
 * user confirms them for upload (or discards them).
 */
data class ScanUiState(
    /** The camera chosen by the user: Google's scanner or the app's camera. */
    val defaultCamera: ScanSource = ScanSource.DEFAULT,
    /** Google's scanner failed to start on this phone, and has not started since. */
    val googleScannerUnavailable: Boolean = false,
    /** The phone has a camera, for the app's own camera screen. */
    val hasCamera: Boolean = true,
    /** The settings are read: until then, the default camera is not known. */
    val loaded: Boolean = false,
    val scannerMode: ScannerMode = ScannerMode.DEFAULT,
    val firstPage: String = "",
    val consecutive: Boolean = true,
    /** Pages captured, scanned or imported, waiting for the user's confirmation. */
    val stagedPages: List<StagedPage> = emptyList(),
    /** Scanned or imported images being copied to the run. */
    val preparation: Preparation? = null,
    val outcome: PreparationOutcome? = null,
    /** The run is being queued for upload. */
    val sending: Boolean = false,
    /** The pages of the run are known: until then, an empty [stagedPages] says nothing. */
    val isRunRead: Boolean = false,
    val wasAddingInterrupted: Boolean = false,
    val reviewEnd: ReviewEnd? = null,
) {
    /** Null while the first page field is invalid. */
    val numbering: PageNumbering? get() = PageNumbering.fromInput(firstPage, consecutive)

    val preparing: Boolean get() = preparation != null

    val pageCount: Int get() = stagedPages.size + (preparation?.imagesToAdd ?: 0)

    val canSend: Boolean get() = numbering != null && stagedPages.isNotEmpty() && !preparing && !sending

    val hasNothingToReview: Boolean
        get() = isRunRead && stagedPages.isEmpty() && !preparing && outcome == null && !sending && reviewEnd == null

    /**
     * The camera "Scan" opens: the default one; the app's camera while Google's scanner is known
     * not to start on this phone; Google's scanner on a phone without a camera.
     */
    val camera: ScanSource get() = when {
        defaultCamera == ScanSource.CAMERA && !hasCamera -> ScanSource.GOOGLE_SCANNER
        defaultCamera == ScanSource.GOOGLE_SCANNER && googleScannerUnavailable && hasCamera -> ScanSource.CAMERA
        else -> defaultCamera
    }
}

sealed interface ReviewEnd {
    data object PagesKept : ReviewEnd

    data class PagesSent(val count: Int) : ReviewEnd

    data class PagesDeleted(val count: Int) : ReviewEnd

    data object Emptied : ReviewEnd
}

/** One-off messages about the pages to send, shown in a snackbar. */
sealed interface ScanMessage {
    /** The run could not be queued for upload; it stays as it was. */
    data object SendFailed : ScanMessage

    data object StorageFull : ScanMessage

    data object SettingNotSaved : ScanMessage

    data object ScannerUnavailable : ScanMessage

    /** Google's scanner stopped without handing pages over, for another reason than the phone. */
    data object ScannerFailed : ScanMessage

    data object PhotoPickerUnavailable : ScanMessage
}

class ScanViewModel(
    private val savedState: SavedStateHandle,
    private val documentId: String,
    private val staging: StagingArea,
    private val runPreparation: RunPreparation,
    private val settings: SettingsRepository,
    private val addScannedPages: suspend (pages: List<Uri>, onProgress: (Int) -> Unit) -> Unit,
    private val addPhotos: suspend (photos: List<Uri>, onProgress: (Int) -> Unit) -> PhotoImportResult,
    private val sendRun: suspend (PageNumbering) -> Int,
    /** Free bytes on the storage that holds the runs; a binder call, run off the main thread. */
    private val freeStorage: () -> Long,
    private val hasCamera: Boolean,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : ViewModel() {

    private val sending = MutableStateFlow(false)
    private val reviewEnd = MutableStateFlow<ReviewEnd?>(null)
    private val messageChannel = Channel<ScanMessage>(Channel.BUFFERED)

    val messages: Flow<ScanMessage> = messageChannel.receiveAsFlow()

    // The form is kept in the saved state, as the process may be killed while the scanner or the
    // camera is in front; the pages of the run are files (StagingArea).
    private val scanForm: Flow<ScanUiState> = combine(
        savedState.getStateFlow(KEY_FIRST_PAGE, ""),
        savedState.getStateFlow(KEY_CONSECUTIVE, true),
        savedState.getStateFlow(KEY_ADDING_INTERRUPTED, false),
        settings.settings,
    ) { firstPage, consecutive, wasAddingInterrupted, settings ->
        ScanUiState(
            defaultCamera = settings.defaultCamera,
            googleScannerUnavailable = settings.googleScannerUnavailable,
            hasCamera = hasCamera,
            loaded = true,
            scannerMode = settings.scannerMode,
            firstPage = firstPage,
            consecutive = consecutive,
            wasAddingInterrupted = wasAddingInterrupted,
        )
    }

    val scanState: StateFlow<ScanUiState> = combine(
        scanForm,
        staging.observe(documentId),
        runPreparation.observe(documentId),
        sending,
        reviewEnd,
    ) { form, stagedPages, preparation, sending, reviewEnd ->
        form.copy(
            stagedPages = stagedPages,
            preparation = preparation.preparation,
            outcome = preparation.outcome,
            sending = sending,
            isRunRead = true,
            reviewEnd = reviewEnd,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ScanUiState())

    init {
        viewModelScope.launch {
            // The app was closed (or killed in the background) while pages were being added.
            // Saved, so that the banner stays until dismissed, even once the process is killed again.
            if (staging.takeInterrupted(documentId)) savedState[KEY_ADDING_INTERRUPTED] = true
        }
    }

    fun onFirstPageChange(text: String) {
        savedState[KEY_FIRST_PAGE] = text.filter(Char::isDigit).take(MAX_FIRST_PAGE_DIGITS)
    }

    fun onConsecutiveChange(consecutive: Boolean) {
        savedState[KEY_CONSECUTIVE] = consecutive
    }

    /** Makes [camera] the one "Scan" opens from now on. */
    fun makeDefaultCamera(camera: ScanSource) {
        viewModelScope.launch {
            try {
                settings.setDefaultCamera(camera)
            } catch (e: IOException) {
                // The storage may be full: the camera opens all the same.
                Log.w(TAG, "default camera not saved", e)
                messageChannel.send(ScanMessage.SettingNotSaved)
            }
        }
    }

    /**
     * What Google's scanner returned: its pages join the run, waiting for confirmation. Without
     * pages, the user canceled, or the scanner could not hand them over: the two look the same, so
     * nothing is said, unless the phone's storage is nearly full, the likely reason for a failure.
     */
    fun onPagesScanned(pages: List<Uri>) {
        if (pages.isEmpty()) {
            viewModelScope.launch {
                if (withContext(io) { isStorageLow(freeStorage()) }) {
                    messageChannel.send(ScanMessage.StorageFull)
                }
            }
            return
        }
        // The copy outlives this view model: it refers to none of it.
        val addPagesToRun = addScannedPages
        runPreparation.start(documentId, CopySource.SCANNED_PAGES, pages.size) { onProgress ->
            addPagesToRun(pages, onProgress)
            null
        }
    }

    /** Photos chosen in the photo picker: they join the run, in the order they were taken. */
    fun onPhotosPicked(photos: List<Uri>) {
        if (photos.isEmpty()) return
        val addPhotosToRun = addPhotos
        runPreparation.start(documentId, CopySource.GALLERY_PHOTOS, photos.size) { onProgress ->
            val result = addPhotosToRun(photos, onProgress)
            if (result.unsupported + result.tooLarge + result.unreadable > 0) {
                PreparationOutcome.PhotosSkipped(result.unsupported, result.tooLarge, result.unreadable)
            } else {
                null
            }
        }
    }

    /**
     * Photos shared from another app, for this document: they join the run like picked photos,
     * once only, even when the screen is recreated with the same share. Whether they started to.
     */
    fun importSharedPhotos(photos: List<Uri>): Boolean {
        if (photos.isEmpty() || savedState.get<Boolean>(KEY_SHARED_IMPORTED) == true) return false
        savedState[KEY_SHARED_IMPORTED] = true
        onPhotosPicked(photos)
        return true
    }

    /**
     * Whether the screen, opened to scan or import at once (a library card's scan button, a new
     * document), must do so now: true once only, not when the screen is recreated or comes back
     * from the camera or the photo picker.
     */
    fun takeActionOnOpen(): Boolean {
        if (savedState.get<Boolean>(KEY_ACTION_ON_OPEN_DONE) == true) return false
        savedState[KEY_ACTION_ON_OPEN_DONE] = true
        return true
    }

    /** Stops an import: the copies made so far are deleted; the photos stay in the gallery. */
    fun cancelPreparation() {
        runPreparation.cancel(documentId)
    }

    fun dismissOutcome() {
        runPreparation.dismissOutcome(documentId)
    }

    fun dismissAddingInterrupted() {
        savedState[KEY_ADDING_INTERRUPTED] = false
    }

    fun closeReview() {
        if (sending.value || reviewEnd.value != null) return
        val scan = scanState.value
        reviewEnd.value = if (scan.stagedPages.isEmpty() && !scan.preparing) ReviewEnd.Emptied else ReviewEnd.PagesKept
    }

    fun onReviewEndShown() {
        reviewEnd.value = null
    }

    /** A review opens: an end left over from an earlier one would close it at once. */
    fun onReviewOpened() {
        reviewEnd.value = null
    }

    /** Google's scanner is about to open: whatever failed before, it works on this phone. */
    fun onScannerStarted() {
        viewModelScope.launch {
            saveQuietly { if (settings.current().googleScannerUnavailable) settings.setGoogleScannerUnavailable(false) }
        }
    }

    /**
     * Google's scanner could not be started: it is remembered, so that "Scan" opens the app's
     * camera until the scanner starts again (chosen in "Scan with…" or in the settings).
     */
    fun onScannerUnavailable(error: Exception) {
        Log.w(TAG, "document scanner unavailable", error)
        messageChannel.trySend(ScanMessage.ScannerUnavailable)
        viewModelScope.launch { saveQuietly { settings.setGoogleScannerUnavailable(true) } }
    }

    /** Google's scanner failed for another reason than the phone: said, not remembered. */
    fun onScannerFailed(error: Exception) {
        Log.w(TAG, "document scanner failed", error)
        messageChannel.trySend(ScanMessage.ScannerFailed)
    }

    /** Writes a setting the user did not choose: if it cannot be written, it is only logged. */
    private suspend fun saveQuietly(write: suspend () -> Unit) {
        try {
            write()
        } catch (e: IOException) {
            Log.w(TAG, "setting not saved", e)
        }
    }

    fun onPhotoPickerUnavailable(error: Exception) {
        Log.w(TAG, "photo picker unavailable", error)
        messageChannel.trySend(ScanMessage.PhotoPickerUnavailable)
    }

    /** Queues the pages of the run for upload, as one session numbered as the user asked. */
    fun send() {
        val scan = scanState.value
        val numbering = scan.numbering ?: return
        if (scan.stagedPages.isEmpty() || scan.preparing || sending.value) return
        sending.value = true
        viewModelScope.launch {
            try {
                val count = sendRun(numbering)
                // Scanning a book in order: the next run starts after this one.
                savedState[KEY_FIRST_PAGE] = numbering.nextFirstPage(count)?.toString().orEmpty()
                savedState[KEY_ADDING_INTERRUPTED] = false
                runPreparation.dismissOutcome(documentId)
                // Before sending is over: the emptied run then never reads as a review left empty.
                reviewEnd.value = ReviewEnd.PagesSent(count)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // The database (full, closed...) or the files: the run stays as it was.
                Log.e(TAG, "could not queue the pages of the run", e)
                messageChannel.send(if (e.isStorageFull()) ScanMessage.StorageFull else ScanMessage.SendFailed)
            } finally {
                sending.value = false
            }
        }
    }

    fun discard() {
        val scan = scanState.value
        if (scan.preparing || sending.value) return
        // Before the deletion: the emptied run then never reads as a review left empty.
        reviewEnd.value = ReviewEnd.PagesDeleted(scan.stagedPages.size)
        savedState[KEY_ADDING_INTERRUPTED] = false
        runPreparation.dismissOutcome(documentId)
        viewModelScope.launch { staging.discard(documentId) }
    }

    /** Takes one page out of the run waiting for confirmation (blurred, twice the same...). */
    fun removePage(page: StagedPage) {
        viewModelScope.launch {
            try {
                staging.delete(documentId, page)
            } catch (e: IOException) {
                Log.w(TAG, "staged page not deleted", e)
            }
        }
    }

    companion object {
        private const val TAG = "Scan"
        private const val KEY_SHARED_IMPORTED = "scan_shared_imported"
        private const val KEY_ACTION_ON_OPEN_DONE = "scan_action_on_open_done"
        private const val KEY_FIRST_PAGE = "scan_first_page"
        private const val KEY_CONSECUTIVE = "scan_consecutive"
        private const val KEY_ADDING_INTERRUPTED = "scan_adding_interrupted"
        private const val MAX_FIRST_PAGE_DIGITS = 4

        val Factory = viewModelFactory {
            initializer {
                val container = this.container
                val savedState = createSavedStateHandle()
                val documentId = savedState.toRoute<DocumentRoute>().documentId
                val scanImporter = container.scanImporter
                ScanViewModel(
                    savedState,
                    documentId,
                    container.staging,
                    container.runPreparation,
                    container.settings,
                    addScannedPages = { pages, onProgress ->
                        scanImporter.addScannedPages(documentId, pages, onProgress)
                    },
                    addPhotos = { photos, onProgress -> scanImporter.addPhotos(documentId, photos, onProgress) },
                    sendRun = { numbering -> scanImporter.send(documentId, numbering) },
                    freeStorage = container::freeStorage,
                    hasCamera = container.hasCamera,
                )
            }
        }
    }
}

/**
 * Whether the message says that pages could be lost, or that the user must act:
 * it then shows longer (about ten seconds rather than four), with a close button.
 */
internal val ScanMessage.important: Boolean get() = when (this) {
    ScanMessage.StorageFull,
    ScanMessage.SendFailed,
    ScanMessage.ScannerUnavailable,
    ScanMessage.ScannerFailed,
    ScanMessage.PhotoPickerUnavailable,
    -> true

    ScanMessage.SettingNotSaved -> false
}
