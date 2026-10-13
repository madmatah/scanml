package fr.scanmylib.model

import okhttp3.HttpUrl

/**
 * The ScanMyLib server this phone is paired with.
 *
 * @property baseUrl root URL of the server, e.g. `http://192.168.1.10:8765/`.
 * @property token bearer token given by the server's pairing QR code.
 */
data class ServerConfig(val baseUrl: HttpUrl, val token: String) {

    /** The base URL as shown to the user, without the trailing slash. */
    val displayUrl: String get() = baseUrl.toString().removeSuffix("/")

    /**
     * Resolves a URL returned by the server, such as `/api/pages/<id>/thumb`; null if it points
     * to another origin, which must never receive the token.
     */
    fun resolve(serverUrl: String): HttpUrl? = baseUrl.resolve(serverUrl)?.takeIf {
        it.scheme == baseUrl.scheme && it.host == baseUrl.host && it.port == baseUrl.port
    }

    // Keeps the token out of logs and crash reports.
    override fun toString(): String = "ServerConfig(baseUrl=$baseUrl)"
}
