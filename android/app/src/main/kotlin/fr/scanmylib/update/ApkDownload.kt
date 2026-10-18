package fr.scanmylib.update

import java.io.File
import java.io.IOException
import java.security.MessageDigest
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request

/** The SHA-256 (lowercase hex) and the size of a downloaded file. */
data class ApkDownload(val sha256: String, val size: Long)

/**
 * Downloads [update]'s APK into [file], reporting the bytes received so far ([onProgress]);
 * stops a byte past the announced size, which the check then refuses. Cancellable, even while a
 * read waits for the PC. Never sends the token: the download route is public. Never follows a
 * redirect: the APK comes from the paired PC only.
 *
 * @throws IOException if the PC cannot be reached or answers with an error, or a redirect.
 */
suspend fun downloadApk(
    http: OkHttpClient,
    update: AvailableUpdate,
    file: File,
    onProgress: (Long) -> Unit,
): ApkDownload = withContext(Dispatchers.IO) {
    val digest = MessageDigest.getInstance("SHA-256")
    var received = 0L
    val client = http.newBuilder().followRedirects(false).followSslRedirects(false).build()
    val call = client.newCall(Request.Builder().url(update.url).build())
    // Canceling the download cancels the call, which ends a blocked read at once. Started
    // undispatched, so that it already waits when the call starts: its finally always runs.
    val watcher = launch(start = CoroutineStart.UNDISPATCHED) {
        try {
            awaitCancellation()
        } finally {
            call.cancel()
        }
    }
    try {
        call.execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code} for ${update.url}")
            file.parentFile?.mkdirs()
            file.outputStream().use { output ->
                response.body.byteStream().use { input ->
                    val buffer = ByteArray(BUFFER_SIZE)
                    while (received <= update.size) {
                        ensureActive()
                        val read = input.read(buffer)
                        if (read < 0) break
                        output.write(buffer, 0, read)
                        digest.update(buffer, 0, read)
                        received += read
                        onProgress(received)
                    }
                }
                output.fd.sync()
            }
        }
    } catch (e: IOException) {
        // The call canceled with the download: a cancellation, not a failure.
        ensureActive()
        throw e
    } finally {
        watcher.cancel()
    }
    ApkDownload(digest.digest().joinToString("") { "%02x".format(it) }, received)
}

private const val BUFFER_SIZE = 64 * 1024
