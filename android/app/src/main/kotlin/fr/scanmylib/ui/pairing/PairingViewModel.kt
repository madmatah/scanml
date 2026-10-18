package fr.scanmylib.ui.pairing

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.pairing.AddressError
import fr.scanmylib.pairing.AddressResult
import fr.scanmylib.pairing.ConnectionCheck
import fr.scanmylib.pairing.PairingError
import fr.scanmylib.pairing.PairingManager
import fr.scanmylib.pairing.PairingResult
import fr.scanmylib.pairing.PairingUri
import fr.scanmylib.pairing.ServerAddress
import fr.scanmylib.pairing.checkConnection
import fr.scanmylib.pairing.isValidToken
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.ui.container
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** Why pairing did not succeed, shown under the form. */
sealed interface PairingProblem {
    data class InvalidQrCode(val error: PairingError) : PairingProblem

    /** Any [ConnectionCheck] but [ConnectionCheck.Ok]. */
    data class Connection(val check: ConnectionCheck) : PairingProblem

    data class ScannerUnavailable(val detail: String) : PairingProblem
}

data class PairingUiState(
    val url: String = "",
    val token: String = "",
    val urlError: AddressError? = null,
    val tokenInvalid: Boolean = false,
    val checking: Boolean = false,
    val problem: PairingProblem? = null,
    val paired: Boolean = false,
)

class PairingViewModel(
    private val settings: SettingsRepository,
    private val pairing: PairingManager,
    private val api: (ServerConfig) -> ScanMyLibApi,
) : ViewModel() {

    private val state = MutableStateFlow(PairingUiState())
    val uiState: StateFlow<PairingUiState> = state.asStateFlow()

    init {
        // When changing servers, start from the current address.
        viewModelScope.launch {
            val current = settings.current().server ?: return@launch
            state.update { if (it.url.isEmpty()) it.copy(url = current.displayUrl) else it }
        }
    }

    fun onUrlChange(url: String) = state.update { it.copy(url = url, urlError = null, problem = null) }

    fun onTokenChange(token: String) = state.update { it.copy(token = token, tokenInvalid = false, problem = null) }

    fun onQrCodeScanned(text: String) {
        when (val result = PairingUri.parse(text)) {
            is PairingResult.Invalid -> state.update { it.copy(problem = PairingProblem.InvalidQrCode(result.error)) }

            is PairingResult.Valid -> {
                state.update {
                    it.copy(
                        url = result.server.displayUrl,
                        token = result.server.token,
                        urlError = null,
                        tokenInvalid = false,
                    )
                }
                connect(result.server)
            }
        }
    }

    fun onScannerUnavailable(error: Exception) {
        Log.w(TAG, "QR code scanner unavailable", error)
        state.update { it.copy(problem = PairingProblem.ScannerUnavailable(error.toString())) }
    }

    /** Pairs with the address and token typed by the user. */
    fun submit() {
        val current = state.value
        val address = ServerAddress.parse(current.url)
        val token = current.token.trim()
        val tokenValid = isValidToken(token)
        state.update {
            it.copy(urlError = (address as? AddressResult.Invalid)?.error, tokenInvalid = !tokenValid, problem = null)
        }
        if (address is AddressResult.Valid && tokenValid) connect(ServerConfig(address.url, token))
    }

    private fun connect(server: ServerConfig) {
        if (state.value.checking) return
        state.update { it.copy(checking = true, problem = null) }
        viewModelScope.launch {
            val check = checkConnection(api(server))
            if (check is ConnectionCheck.Ok) pairing.pair(server)
            state.update {
                it.copy(
                    checking = false,
                    paired = check is ConnectionCheck.Ok,
                    problem = if (check is ConnectionCheck.Ok) null else PairingProblem.Connection(check),
                )
            }
        }
    }

    companion object {
        private const val TAG = "Pairing"

        val Factory = viewModelFactory {
            initializer {
                val container = this.container
                PairingViewModel(container.settings, container.pairing, container::api)
            }
        }
    }
}
