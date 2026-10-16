package fr.scanmylib.ui.settings

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.library.KeptCopies
import fr.scanmylib.library.LibraryRepository
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.pairing.ConnectionCheck
import fr.scanmylib.pairing.PairingManager
import fr.scanmylib.pairing.checkConnection
import fr.scanmylib.settings.AppSettings
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.sync.SyncScheduler
import fr.scanmylib.ui.container
import fr.scanmylib.update.AppUpdater
import fr.scanmylib.update.UpdateState
import java.io.IOException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class SettingsUiState(
    val settings: AppSettings? = null,
    val keptCopies: KeptCopies = KeptCopies(0, 0),
    val testing: Boolean = false,
    val lastCheck: ConnectionCheck? = null,
)

class SettingsViewModel(
    private val settings: SettingsRepository,
    private val library: LibraryRepository,
    private val pairing: PairingManager,
    private val syncScheduler: SyncScheduler,
    private val api: (ServerConfig) -> ScanMyLibApi,
    private val updates: AppUpdater,
) : ViewModel() {

    /** The update the PC offers, if any, and the last check. */
    val updateState: StateFlow<UpdateState> = updates.state

    fun checkForUpdate() = updates.check()

    fun installUpdate() = updates.install()

    fun cancelUpdate() = updates.cancel()

    private val testing = MutableStateFlow(false)
    private val lastCheck = MutableStateFlow<ConnectionCheck?>(null)
    private val unpairedChannel = Channel<Unit>(Channel.CONFLATED)
    private val notSavedChannel = Channel<Unit>(Channel.CONFLATED)

    val uiState: StateFlow<SettingsUiState> =
        combine(settings.settings, library.observeKeptCopies(), testing, lastCheck) { settings, copies, testing, check ->
            SettingsUiState(settings, copies, testing, check)
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SettingsUiState())

    /** Emits once the phone is unpaired. */
    val unpaired: Flow<Unit> = unpairedChannel.receiveAsFlow()

    /** Emits when a setting could not be saved: the phone's storage may be full. */
    val settingNotSaved: Flow<Unit> = notSavedChannel.receiveAsFlow()

    fun testConnection() {
        if (testing.value) return
        testing.value = true
        viewModelScope.launch {
            try {
                lastCheck.value = settings.current().server?.let { checkConnection(api(it)) }
            } finally {
                testing.value = false
            }
        }
    }

    fun setWifiOnly(enabled: Boolean) {
        viewModelScope.launch {
            // The waiting upload must pick up the new network constraint.
            if (save { settings.setWifiOnly(enabled) }) syncScheduler.restart()
        }
    }

    fun setKeepLocalCopies(enabled: Boolean) {
        viewModelScope.launch { save { settings.setKeepLocalCopies(enabled) } }
    }

    fun setScannerMode(mode: ScannerMode) {
        viewModelScope.launch { save { settings.setScannerMode(mode) } }
    }

    /** The camera "Scan" opens: Google's scanner or the app's camera. */
    fun setDefaultCamera(camera: ScanSource) {
        viewModelScope.launch { save { settings.setDefaultCamera(camera) } }
    }

    /** Writes a setting; returns false if it could not be written. */
    private suspend fun save(write: suspend () -> Unit): Boolean = try {
        write()
        true
    } catch (e: IOException) {
        // The screen keeps showing the stored value.
        Log.w(TAG, "setting not saved", e)
        notSavedChannel.send(Unit)
        false
    }

    fun deleteKeptCopies() {
        viewModelScope.launch { library.deleteKeptCopies() }
    }

    fun unpair() {
        viewModelScope.launch {
            pairing.unpair()
            unpairedChannel.send(Unit)
        }
    }

    companion object {
        private const val TAG = "Settings"

        val Factory = viewModelFactory {
            initializer {
                val container = this.container
                SettingsViewModel(
                    container.settings,
                    container.library,
                    container.pairing,
                    container.syncScheduler,
                    container::api,
                    container.updates,
                )
            }
        }
    }
}
