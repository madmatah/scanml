package fr.scanmylib.ui.library

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.api.ApiException
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.api.ServerStatus
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.library.AUTO_REFRESH_INTERVAL
import fr.scanmylib.library.LibraryRepository
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.autoRefresh
import fr.scanmylib.library.libraryWork
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.sync.SyncScheduler
import fr.scanmylib.ui.container
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** What the app knows about the PC, from the last refresh. */
sealed interface PcState {
    data object Unknown : PcState

    data class Online(val status: ServerStatus) : PcState

    data object Unreachable : PcState

    data object TokenRefused : PcState

    data class Error(val detail: String) : PcState
}

data class LibraryUiState(
    val documents: List<LibraryRow> = emptyList(),
    /** Pages waiting on the phone for the user to send them, by document id. */
    val stagedPages: Map<String, Int> = emptyMap(),
    val server: ServerConfig? = null,
    val refreshing: Boolean = false,
    val pc: PcState = PcState.Unknown,
)

/** Fields of the "new document" form. */
data class NewDocument(val title: String, val author: String, val kind: DocumentKind, val unwarp: Boolean) {
    companion object {
        /**
         * Longest title or author the server accepts: it refuses to create a document with a
         * longer one (HTTP 422), and the app cannot edit a document, so it would never get there.
         */
        const val MAX_TEXT_LENGTH = 300

        /** What a title or author field keeps of the text typed or pasted into it. */
        fun fieldText(input: String): String = input.take(MAX_TEXT_LENGTH)
    }
}

class LibraryViewModel(
    private val library: LibraryRepository,
    staging: StagingArea,
    private val settings: SettingsRepository,
    private val syncScheduler: SyncScheduler,
    private val api: (ServerConfig) -> ScanMyLibApi,
) : ViewModel() {

    private val refreshing = MutableStateFlow(false)

    /** Refreshes asked by the user and automatic ones, one at a time. */
    private val refreshMutex = Mutex()
    private val pc = MutableStateFlow<PcState>(PcState.Unknown)
    private val createdDocuments = Channel<String>(Channel.BUFFERED)

    val uiState: StateFlow<LibraryUiState> = combine(
        library.observeLibrary(),
        staging.observeRunSizes(),
        settings.settings,
        refreshing,
        pc,
    ) { documents, stagedPages, settings, refreshing, pc ->
        LibraryUiState(documents, stagedPages, settings.server, refreshing, pc)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), LibraryUiState())

    /** Ids of documents just created, to open them. */
    val documentsToOpen: Flow<String> = createdDocuments.receiveAsFlow()

    init {
        refresh()
    }

    /** Refreshes the library and the PC status, and retries pending uploads right away. */
    fun refresh() {
        if (refreshing.value) return
        refreshing.value = true
        viewModelScope.launch {
            try {
                pc.value = fetchFromServer(retryUploads = true)
            } finally {
                refreshing.value = false
            }
        }
    }

    /**
     * Keeps the library and the PC status up to date while the screen is visible, until
     * canceled: refreshes them once pages are uploaded, then while the PC processes pages (see
     * [autoRefresh]).
     */
    suspend fun keepUpToDate() {
        val work = combine(uiState, library.observeUnlistedUploads()) { state, unlistedUploads ->
            libraryWork(state.documents, unlistedUploads, (state.pc as? PcState.Online)?.status?.queue)
        }
        autoRefresh(work, AUTO_REFRESH_INTERVAL) {
            // In the view model's scope: a refresh under way ends normally if the screen is left.
            viewModelScope.async {
                // Not retrying the uploads: that would cut their backoff delay short again and again.
                val state = fetchFromServer(retryUploads = false)
                pc.value = state
                state is PcState.Online
            }.await()
        }
    }

    private suspend fun fetchFromServer(retryUploads: Boolean): PcState {
        val server = settings.current().server ?: return PcState.Unknown
        if (retryUploads) syncScheduler.requestSyncIfPending()
        return try {
            refreshMutex.withLock {
                val status = api(server).status()
                library.refreshLibrary(server)
                PcState.Online(status)
            }
        } catch (e: ApiException) {
            when (e) {
                is ApiException.Unreachable -> PcState.Unreachable
                is ApiException.Unauthorized -> PcState.TokenRefused
                else -> PcState.Error(e.message.orEmpty())
            }
        }
    }

    fun createDocument(document: NewDocument) {
        viewModelScope.launch {
            val id = library.createDocument(document.title, document.author, document.kind, document.unwarp)
            createdDocuments.send(id)
        }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer {
                val container = this.container
                LibraryViewModel(
                    container.library,
                    container.staging,
                    container.settings,
                    container.syncScheduler,
                    container::api,
                )
            }
        }
    }
}
