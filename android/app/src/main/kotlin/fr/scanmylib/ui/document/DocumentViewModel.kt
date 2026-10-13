package fr.scanmylib.ui.document

import android.database.sqlite.SQLiteFullException
import android.net.Uri
import android.util.Log
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.toRoute
import fr.scanmylib.api.ApiException
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.library.AUTO_REFRESH_INTERVAL
import fr.scanmylib.library.DocumentPages
import fr.scanmylib.library.LibraryRepository
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.library.ScanImporter
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.autoRefresh
import fr.scanmylib.library.documentWork
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.sync.SyncScheduler
import fr.scanmylib.ui.DocumentRoute
import fr.scanmylib.ui.container
import java.io.File
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class DocumentUiState(
    val loading: Boolean = true,
    /** Null once loaded if the document no longer exists (deleted on the PC). */
    val document: DocumentEntity? = null,
    val pages: DocumentPages = DocumentPages.EMPTY,
    val server: ServerConfig? = null,
    val refreshing: Boolean = false,
)

/**
 * The "scan pages" flow: the source of the pages and their optional numbering, then the pages of
 * the run, kept on the phone until the user confirms them for upload (or discards them).
 */
data class ScanUiState(
    val setupVisible: Boolean = false,
    val source: ScanSource = ScanSource.DEFAULT,
    val scannerMode: ScannerMode = ScannerMode.DEFAULT,
    val firstPage: String = "",
    val consecutive: Boolean = true,
    /** Pages captured, scanned or imported, waiting for the user's confirmation. */
    val stagedPages: List<StagedPage> = emptyList(),
    /** Scanned or imported images being copied to the run. */
    val preparation: Preparation? = null,
    /** The run is being queued for upload. */
    val sending: Boolean = false,
) {
    /** Null while the first page field is invalid. */
    val numbering: PageNumbering? get() = PageNumbering.fromInput(firstPage, consecutive)

    val preparing: Boolean get() = preparation != null
}

/** Scanned or imported images being copied to the run: [done] of [total] so far. */
data class Preparation(val done: Int, val total: Int, val cancellable: Boolean)

/** One-off messages shown in a snackbar. */
sealed interface DocumentMessage {
    data object Unreachable : DocumentMessage

    data object TokenRefused : DocumentMessage

    data class ServerError(val detail: String) : DocumentMessage

    data class PagesQueued(val count: Int) : DocumentMessage

    /** Scanned or imported images could not be copied to the run. */
    data object ImportFailed : DocumentMessage

    /** The run could not be queued for upload; it stays as it was. */
    data object SendFailed : DocumentMessage

    /** Like [ImportFailed] or [SendFailed], because the phone's storage is full. */
    data object StorageFull : DocumentMessage

    /** Photos left out of an import: the server refuses their format. */
    data class UnsupportedPhotos(val count: Int) : DocumentMessage

    /** Photos left out of an import: over the server's size limits. */
    data class TooLargePhotos(val count: Int) : DocumentMessage

    /** Photos left out of an import: they could not be read. */
    data class UnreadablePhotos(val count: Int) : DocumentMessage

    /** Google's scanner returned without pages: canceled, or it could not hand them over. */
    data object NothingScanned : DocumentMessage

    /** Images on their way to the run were cut short when the app was last closed. */
    data object AddingInterrupted : DocumentMessage

    data object SettingNotSaved : DocumentMessage

    data object ScannerUnavailable : DocumentMessage

    data object PhotoPickerUnavailable : DocumentMessage

    /** A local page cannot be deleted while it is being uploaded. */
    data object PageBusy : DocumentMessage
}

class DocumentViewModel(
    private val savedState: SavedStateHandle,
    private val library: LibraryRepository,
    private val scanImporter: ScanImporter,
    private val staging: StagingArea,
    private val settings: SettingsRepository,
    private val syncScheduler: SyncScheduler,
) : ViewModel() {

    private val documentId = savedState.toRoute<DocumentRoute>().documentId
    private val refreshing = MutableStateFlow(false)

    /** Refreshes asked by the user and automatic ones, one at a time. */
    private val refreshMutex = Mutex()
    private val preparation = MutableStateFlow<Preparation?>(null)
    private var preparationJob: Job? = null

    /** Tells the current preparation from one canceled but still winding down. */
    private var preparationId = 0
    private val sending = MutableStateFlow(false)
    private val messageChannel = Channel<DocumentMessage>(Channel.BUFFERED)

    val messages: Flow<DocumentMessage> = messageChannel.receiveAsFlow()

    val uiState: StateFlow<DocumentUiState> = combine(
        library.observeDocument(documentId),
        library.observePages(documentId),
        settings.settings,
        refreshing,
    ) { document, pages, settings, refreshing ->
        DocumentUiState(loading = false, document, pages, settings.server, refreshing)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), DocumentUiState())

    // The form is kept in the saved state, as the process may be killed while the scanner or the
    // camera is in front; the pages of the run are files (StagingArea).
    private val scanForm: Flow<ScanUiState> = combine(
        savedState.getStateFlow(KEY_SETUP_VISIBLE, false),
        savedState.getStateFlow(KEY_FIRST_PAGE, ""),
        savedState.getStateFlow(KEY_CONSECUTIVE, true),
        settings.settings,
    ) { setupVisible, firstPage, consecutive, settings ->
        ScanUiState(setupVisible, settings.scanSource, settings.scannerMode, firstPage, consecutive)
    }

    val scanState: StateFlow<ScanUiState> = combine(
        scanForm,
        staging.observe(documentId),
        preparation,
        sending,
    ) { form, stagedPages, preparation, sending ->
        form.copy(stagedPages = stagedPages, preparation = preparation, sending = sending)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ScanUiState())

    init {
        refresh()
        viewModelScope.launch {
            // The app was closed (or killed in the background) while pages were being added.
            if (staging.takeInterrupted(documentId)) messageChannel.send(DocumentMessage.AddingInterrupted)
        }
    }

    fun localImage(page: PendingPageEntity): File? = library.imageOf(page)

    /** Refreshes the document from the PC, and retries pending uploads right away. */
    fun refresh() {
        if (refreshing.value) return
        refreshing.value = true
        viewModelScope.launch {
            try {
                val server = settings.current().server ?: return@launch
                syncScheduler.requestSyncIfPending()
                refreshMutex.withLock { library.refreshDocument(server, documentId) }
            } catch (e: ApiException) {
                messageChannel.send(
                    when (e) {
                        is ApiException.Unreachable -> DocumentMessage.Unreachable
                        is ApiException.Unauthorized -> DocumentMessage.TokenRefused
                        else -> DocumentMessage.ServerError(e.message.orEmpty())
                    },
                )
            } finally {
                refreshing.value = false
            }
        }
    }

    /**
     * Keeps the document up to date while the screen is visible, until canceled: refreshes it
     * once its pages are uploaded, then while the PC processes them (see [autoRefresh]). Without
     * this, uploaded pages would stay shown as on the phone, and the PC's state as it was when the
     * screen was opened.
     */
    suspend fun keepUpToDate() {
        autoRefresh(uiState.map { documentWork(it.document, it.pages) }, AUTO_REFRESH_INTERVAL) {
            // In the view model's scope: a refresh under way ends normally if the screen is left.
            viewModelScope.async { refreshQuietly() }.await()
        }
    }

    /** An automatic refresh: unlike [refresh], it does not report failures, only returns them. */
    private suspend fun refreshQuietly(): Boolean {
        val server = settings.current().server ?: return false
        return try {
            refreshMutex.withLock { library.refreshDocument(server, documentId) }
            true
        } catch (e: ApiException) {
            Log.i(TAG, "automatic refresh failed: ${e.message}")
            false
        }
    }

    fun openScanSetup() {
        savedState[KEY_SETUP_VISIBLE] = true
    }

    fun closeScanSetup() {
        savedState[KEY_SETUP_VISIBLE] = false
    }

    fun onFirstPageChange(text: String) {
        savedState[KEY_FIRST_PAGE] = text.filter(Char::isDigit).take(MAX_FIRST_PAGE_DIGITS)
    }

    fun onConsecutiveChange(consecutive: Boolean) {
        savedState[KEY_CONSECUTIVE] = consecutive
    }

    /** Remembers the source, offered first for the next runs too. */
    fun onSourceChange(source: ScanSource) {
        viewModelScope.launch {
            try {
                settings.setScanSource(source)
            } catch (e: IOException) {
                // The storage may be full: the choice still applies to this run, not saved.
                Log.w(TAG, "scan source not saved", e)
                messageChannel.send(DocumentMessage.SettingNotSaved)
            }
        }
    }

    /** Pages returned by Google's scanner: they join the run, waiting for confirmation. */
    fun onPagesScanned(pages: List<Uri>) {
        if (pages.isEmpty()) {
            messageChannel.trySend(DocumentMessage.NothingScanned)
            return
        }
        // Not cancellable: the scanned pages exist nowhere else.
        prepare(pages.size, cancellable = false) { onProgress ->
            scanImporter.addScannedPages(documentId, pages, onProgress)
        }
    }

    /** Photos chosen in the photo picker: they join the run, in the order they were taken. */
    fun onPhotosPicked(photos: List<Uri>) {
        if (photos.isEmpty()) return
        prepare(photos.size, cancellable = true) { onProgress ->
            val result = scanImporter.addPhotos(documentId, photos, onProgress)
            if (result.unsupported > 0) messageChannel.send(DocumentMessage.UnsupportedPhotos(result.unsupported))
            if (result.tooLarge > 0) messageChannel.send(DocumentMessage.TooLargePhotos(result.tooLarge))
            if (result.unreadable > 0) messageChannel.send(DocumentMessage.UnreadablePhotos(result.unreadable))
        }
    }

    /** Runs [addPages], which reports how many of the [total] images it has copied so far. */
    private fun prepare(total: Int, cancellable: Boolean, addPages: suspend (onProgress: (Int) -> Unit) -> Unit) {
        val id = ++preparationId
        preparation.value = Preparation(done = 0, total = total, cancellable = cancellable)
        preparationJob = viewModelScope.launch {
            try {
                addPages { done -> if (id == preparationId) preparation.value = Preparation(done, total, cancellable) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // Whatever the images' provider throws: IOException, SecurityException, but also
                // the runtime exceptions a content provider passes across the binder.
                onImportFailed(e)
            } finally {
                if (id == preparationId) preparation.value = null
            }
        }
    }

    /** Stops an import: the copies made so far are deleted; the photos stay in the gallery. */
    fun cancelPreparation() {
        if (preparation.value?.cancellable != true) return
        // A read in progress (a cloud photo...) may take a while to give up: no need to wait.
        preparationId++
        preparationJob?.cancel()
        preparation.value = null
    }

    fun onScannerUnavailable(error: Exception) {
        Log.w(TAG, "document scanner unavailable", error)
        messageChannel.trySend(DocumentMessage.ScannerUnavailable)
    }

    fun onPhotoPickerUnavailable(error: Exception) {
        Log.w(TAG, "photo picker unavailable", error)
        messageChannel.trySend(DocumentMessage.PhotoPickerUnavailable)
    }

    /** Queues the pages of the run for upload, as one session numbered as the user asked. */
    fun confirmScan() {
        val scan = scanState.value
        val numbering = scan.numbering ?: return
        if (scan.stagedPages.isEmpty() || sending.value) return
        sending.value = true
        viewModelScope.launch {
            try {
                val count = scanImporter.send(documentId, numbering)
                // Scanning a book in order: the next run starts after this one.
                savedState[KEY_FIRST_PAGE] = numbering.nextFirstPage(count)?.toString().orEmpty()
                if (count > 0) messageChannel.send(DocumentMessage.PagesQueued(count))
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // The database (full, closed...) or the files: the run stays as it was.
                Log.e(TAG, "could not queue the pages of the run", e)
                messageChannel.send(if (e.isStorageFull()) DocumentMessage.StorageFull else DocumentMessage.SendFailed)
            } finally {
                sending.value = false
            }
        }
    }

    private suspend fun onImportFailed(error: Exception) {
        Log.e(TAG, "could not save the pages of the run", error)
        messageChannel.send(if (error.isStorageFull()) DocumentMessage.StorageFull else DocumentMessage.ImportFailed)
    }

    fun discardScan() {
        viewModelScope.launch { scanImporter.discard(documentId) }
    }

    /** Takes one page out of the run waiting for confirmation (blurred, twice the same...). */
    fun removeStagedPage(page: StagedPage) {
        viewModelScope.launch {
            try {
                staging.remove(documentId, page)
            } catch (e: IOException) {
                Log.w(TAG, "staged page not deleted", e)
            }
        }
    }

    fun retryDocumentUpload() {
        viewModelScope.launch { library.retryDocumentUpload(documentId) }
    }

    fun retryPage(pageId: String) {
        viewModelScope.launch { library.retryPage(pageId) }
    }

    fun deletePage(pageId: String) {
        viewModelScope.launch {
            if (!library.deleteLocalPage(pageId)) messageChannel.send(DocumentMessage.PageBusy)
        }
    }

    companion object {
        private const val TAG = "Document"
        private const val KEY_SETUP_VISIBLE = "scan_setup_visible"
        private const val KEY_FIRST_PAGE = "scan_first_page"
        private const val KEY_CONSECUTIVE = "scan_consecutive"
        private const val MAX_FIRST_PAGE_DIGITS = 4

        val Factory = viewModelFactory {
            initializer {
                val container = this.container
                DocumentViewModel(
                    createSavedStateHandle(),
                    container.library,
                    container.scanImporter,
                    container.staging,
                    container.settings,
                    container.syncScheduler,
                )
            }
        }
    }
}

/** Whether [this] failed because the phone's storage is full (files or database). */
internal fun Throwable.isStorageFull(): Boolean = generateSequence(this) { it.cause }.take(MAX_CAUSES).any {
    it is SQLiteFullException || it.message?.contains("ENOSPC") == true
}

private const val MAX_CAUSES = 10
