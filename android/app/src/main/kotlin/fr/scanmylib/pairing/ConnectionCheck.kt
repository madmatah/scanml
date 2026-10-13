package fr.scanmylib.pairing

import fr.scanmylib.api.ApiException
import fr.scanmylib.api.SUPPORTED_API_VERSION
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.api.ServerStatus

/** Outcome of [checkConnection]. */
sealed interface ConnectionCheck {
    data class Ok(val status: ServerStatus) : ConnectionCheck

    data object Unreachable : ConnectionCheck

    /** Something answers at this address, but it is not a ScanMyLib server. */
    data object NotScanMyLib : ConnectionCheck

    /** A ScanMyLib server speaking another version of the API. */
    data object IncompatibleServer : ConnectionCheck

    data object TokenRefused : ConnectionCheck

    data class Failed(val detail: String) : ConnectionCheck
}

/**
 * Checks that [api] reaches a compatible ScanMyLib server that accepts its token: first the
 * public `GET /api/health` (the token is only sent to a server that identifies as ScanMyLib),
 * then the authenticated `GET /api/status`.
 */
suspend fun checkConnection(api: ScanMyLibApi): ConnectionCheck {
    val health = try {
        api.health()
    } catch (e: ApiException) {
        return when (e) {
            is ApiException.Unreachable -> ConnectionCheck.Unreachable
            else -> ConnectionCheck.NotScanMyLib
        }
    }
    if (health.name != "ScanMyLib") return ConnectionCheck.NotScanMyLib
    if (health.api != SUPPORTED_API_VERSION) return ConnectionCheck.IncompatibleServer

    return try {
        ConnectionCheck.Ok(api.status())
    } catch (e: ApiException) {
        when (e) {
            is ApiException.Unauthorized -> ConnectionCheck.TokenRefused
            is ApiException.Unreachable -> ConnectionCheck.Unreachable
            else -> ConnectionCheck.Failed(e.message.orEmpty())
        }
    }
}
