package fr.scanmylib.api

import java.io.IOException

/** Failure of a call to the ScanMyLib server. */
sealed class ApiException(message: String, cause: Throwable? = null) : Exception(message, cause) {

    /** The server could not be reached: PC off or asleep, wrong address, no network... */
    class Unreachable(cause: IOException) : ApiException("server unreachable: ${cause.message}", cause)

    /** The server refused the token (HTTP 401). */
    class Unauthorized : ApiException("token refused")

    /** Any other unsuccessful HTTP status, with the server's `detail` message if any. */
    class Http(val code: Int, val detail: String?) :
        ApiException(if (detail.isNullOrBlank()) "HTTP $code" else "HTTP $code: $detail")

    /** The answer is not the expected JSON (not a ScanMyLib server, or an incompatible one). */
    class InvalidResponse(cause: Throwable) : ApiException("unexpected response: ${cause.message}", cause)
}
