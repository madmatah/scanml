package fr.scanmylib.pairing

import fr.scanmylib.model.ServerConfig
import java.io.UnsupportedEncodingException
import java.net.URI
import java.net.URISyntaxException
import java.net.URLDecoder

/** Why a scanned QR code cannot be used to pair with a server. */
enum class PairingError {
    /** Not a `scanmylib://pair` URI (another QR code, or a damaged one). */
    NOT_A_PAIRING_CODE,
    INVALID_URL,
    INVALID_TOKEN,
}

sealed interface PairingResult {
    data class Valid(val server: ServerConfig) : PairingResult

    data class Invalid(val error: PairingError) : PairingResult
}

/**
 * The pairing URI shown as a QR code by the server's web UI:
 * `scanmylib://pair?url=<urlencoded server URL>&token=<token>`.
 */
object PairingUri {
    private const val SCHEME = "scanmylib"
    private const val HOST = "pair"

    fun parse(text: String): PairingResult {
        val uri = try {
            URI(text.trim())
        } catch (e: URISyntaxException) {
            return PairingResult.Invalid(PairingError.NOT_A_PAIRING_CODE)
        }
        if (!uri.scheme.equals(SCHEME, ignoreCase = true) || !uri.host.equals(HOST, ignoreCase = true)) {
            return PairingResult.Invalid(PairingError.NOT_A_PAIRING_CODE)
        }
        val parameters = parseQuery(uri.rawQuery)
            ?: return PairingResult.Invalid(PairingError.NOT_A_PAIRING_CODE)

        val address = parameters["url"]?.let(ServerAddress::parse)
        if (address !is AddressResult.Valid) return PairingResult.Invalid(PairingError.INVALID_URL)
        val token = parameters["token"]
        if (token == null || !isValidToken(token)) return PairingResult.Invalid(PairingError.INVALID_TOKEN)

        return PairingResult.Valid(ServerConfig(address.url, token))
    }

    /** Decodes form-urlencoded parameters; null if one is malformed or repeated (ambiguous). */
    private fun parseQuery(rawQuery: String?): Map<String, String>? {
        val parameters = mutableMapOf<String, String>()
        for (pair in rawQuery.orEmpty().split('&')) {
            if (pair.isEmpty()) continue
            val name = decode(pair.substringBefore('=')) ?: return null
            val value = decode(pair.substringAfter('=', missingDelimiterValue = "")) ?: return null
            if (parameters.put(name, value) != null) return null
        }
        return parameters
    }

    private fun decode(component: String): String? = try {
        // The Charset overload needs API 33; minSdk is 26.
        URLDecoder.decode(component, "UTF-8")
    } catch (e: IllegalArgumentException) {
        null
    } catch (e: UnsupportedEncodingException) {
        null
    }
}
