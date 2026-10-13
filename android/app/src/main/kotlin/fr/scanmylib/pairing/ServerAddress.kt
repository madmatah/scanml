package fr.scanmylib.pairing

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** Why a server address was rejected. */
enum class AddressError {
    EMPTY,

    /** Not a parsable URL (bad host or port...). */
    MALFORMED,

    /** Only `http` and `https` are supported. */
    UNSUPPORTED_SCHEME,

    /** The address must be the server root: no credentials, path, query or fragment. */
    NOT_A_ROOT_URL,
}

sealed interface AddressResult {
    data class Valid(val url: HttpUrl) : AddressResult

    data class Invalid(val error: AddressError) : AddressResult
}

/** Parsing of the server address typed by the user or carried by a pairing QR code. */
object ServerAddress {
    private val schemePrefix = Regex("^([A-Za-z][A-Za-z0-9+.-]*)://")

    /**
     * Parses [input] as the root URL of a ScanMyLib server. A missing scheme defaults to
     * `http://`, which is what the server uses on a local network; a valid result always has the
     * path `/`.
     */
    fun parse(input: String): AddressResult {
        val text = input.trim()
        if (text.isEmpty()) return AddressResult.Invalid(AddressError.EMPTY)

        val scheme = schemePrefix.find(text)?.groupValues?.get(1)?.lowercase()
        if (scheme != null && scheme != "http" && scheme != "https") {
            return AddressResult.Invalid(AddressError.UNSUPPORTED_SCHEME)
        }
        val url = (if (scheme == null) "http://$text" else text).toHttpUrlOrNull()
            ?: return AddressResult.Invalid(AddressError.MALFORMED)

        val isRoot = url.username.isEmpty() && url.password.isEmpty() &&
            url.encodedPath == "/" && url.query == null && url.fragment == null
        return if (isRoot) AddressResult.Valid(url) else AddressResult.Invalid(AddressError.NOT_A_ROOT_URL)
    }
}

/** Tokens travel in an HTTP header: printable ASCII without spaces, reasonably short. */
fun isValidToken(token: String): Boolean =
    token.length in 1..MAX_TOKEN_LENGTH && token.all { it in '!'..'~' }

private const val MAX_TOKEN_LENGTH = 512
