package fr.scanmylib.ui.document

import android.database.sqlite.SQLiteFullException
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
import fr.scanmylib.library.autoRefresh
import fr.scanmylib.library.documentWork
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.sync.SyncScheduler
import fr.scanmylib.ui.DocumentRoute
import fr.scanmylib.ui.container
import java.io.File
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

/** One-off messages shown in a snackbar. */
sealed interface DocumentMessage {
    data object Unreachable : DocumentMessage

    data object TokenRefused : DocumentMessage

    data class ServerError(val detail: String) : DocumentMessage

    /** A local page cannot be deleted while it is being uploaded. */
    data object PageBusy : DocumentMessage
}

class DocumentViewModel(
    private val savedState: SavedStateHandle,
    private val library: LibraryRepository,
    private val settings: SettingsRepository,
    private val syncScheduler: SyncScheduler,
) : ViewModel() {

    private val documentId = savedState.toRoute<DocumentRoute>().documentId
    private val refreshing = MutableStateFlow(false)

    /** Refreshes asked by the user and automatic ones, one at a time. */
    private val refreshMutex = Mutex()
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

    init {
        refresh()
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

        val Factory = viewModelFactory {
            initializer {
                val container = this.container
                DocumentViewModel(
                    createSavedStateHandle(),
                    container.library,
                    container.settings,
                    container.syncScheduler,
                )
            }
        }
    }
}

/**
 * Whether [freeBytes] is too little for Google's scanner to hand its pages over: it writes each
 * page, a few megabytes, before returning them, and then the app copies them.
 */
internal fun isStorageLow(freeBytes: Long): Boolean = freeBytes < LOW_STORAGE_BYTES

private const val LOW_STORAGE_BYTES = 100L * 1024 * 1024

/**
 * Whether the message says that the user must act: it then shows longer (about ten seconds rather
 * than four), with a close button.
 */
internal val DocumentMessage.important: Boolean get() = when (this) {
    DocumentMessage.TokenRefused -> true

    DocumentMessage.Unreachable,
    is DocumentMessage.ServerError,
    DocumentMessage.PageBusy,
    -> false
}

/** Whether [this] failed because the phone's storage is full (files or database). */
internal fun Throwable.isStorageFull(): Boolean = generateSequence(this) { it.cause }.take(MAX_CAUSES).any {
    it is SQLiteFullException || it.message?.contains("ENOSPC") == true
}

private const val MAX_CAUSES = 10
