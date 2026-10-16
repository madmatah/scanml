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
import fr.scanmylib.update.AppUpdater
import fr.scanmylib.update.UpdateState
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
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
    private val updates: AppUpdater,
) : ViewModel() {

    /** The update the PC offers, if any. */
    val updateState: StateFlow<UpdateState> = updates.state

    private val refreshing = MutableStateFlow(false)

    /** Refreshes asked by the user and automatic ones, one at a time. */
    private val refreshMutex = Mutex()
    private val pc = MutableStateFlow<PcState>(PcState.Unknown)

    val uiState: StateFlow<LibraryUiState> = combine(
        library.observeLibrary(),
        staging.observeRunSizes(),
        settings.settings,
        refreshing,
        pc,
    ) { documents, stagedPages, settings, refreshing, pc ->
        LibraryUiState(documents, stagedPages, settings.server, refreshing, pc)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), LibraryUiState())

    init {
        refresh()
    }

    fun installUpdate() = updates.install()

    fun cancelUpdate() = updates.cancel()

    /**
     * Refreshes the library and the PC status, and retries pending uploads right away; asks the PC
     * for an update unless it was asked recently.
     */
    fun refresh() {
        if (refreshing.value) return
        refreshing.value = true
        updates.checkIfDue()
        viewModelScope.launch {
            try {
                showPc(fetchFromServer(retryUploads = true))
            } finally {
                refreshing.value = false
            }
        }
    }

    /**
     * Keeps the library and the PC status up to date while the screen is visible, until
     * canceled: refreshes them once pages are uploaded, then while the PC processes pages (see
     * [autoRefresh]). Asks the PC for an update as the screen shows, unless it was asked recently.
     */
    suspend fun keepUpToDate() {
        updates.checkIfDue()
        val work = combine(uiState, library.observeUnlistedUploads()) { state, unlistedUploads ->
            libraryWork(state.documents, unlistedUploads, (state.pc as? PcState.Online)?.status?.queue)
        }
        autoRefresh(work, AUTO_REFRESH_INTERVAL) {
            // In the view model's scope: a refresh under way ends normally if the screen is left.
            viewModelScope.async {
                // Not retrying the uploads: that would cut their backoff delay short again and again.
                val state = fetchFromServer(retryUploads = false)
                showPc(state)
                state is PcState.Online
            }.await()
        }
    }

    /** Shows the PC's [state]; once the PC answers again, a check for updates that could not reach it is made again. */
    private fun showPc(state: PcState) {
        val wasOnline = pc.value is PcState.Online
        pc.value = state
        if (state is PcState.Online && !wasOnline) updates.onPcBack()
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
                    container.updates,
                )
            }
        }
    }
}
