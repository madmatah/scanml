package fr.scanmylib.api

import fr.scanmylib.model.ServerConfig
import java.io.File
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

/** Headers authenticating a request to [server]; the phone always sends the CSRF guard header too. */
fun authenticationHeaders(server: ServerConfig): Map<String, String> = mapOf(
    "Authorization" to "Bearer ${server.token}",
    "X-ScanMyLib" to "1",
)

/**
 * The thumbnail of page [pageId] (`GET /api/pages/{id}/thumb`), as the `thumb_url` of the pages the
 * server lists: to resolve with [ServerConfig.resolve]. Page ids are UUIDs: the server refuses others.
 */
fun pageThumbUrl(pageId: String): String = "/api/pages/$pageId/thumb"

/** Metadata of one scanned page, sent along with its image. */
data class PageUpload(
    val documentId: String,
    val pageId: String,
    /** One id per scanner run. */
    val sessionId: String,
    /** Position of the page in its scanner run, from 1. */
    val seq: Int,
    /** ISO-8601 with offset. */
    val capturedAt: String,
    val pageNumberHint: Int?,
)

/**
 * Builds the HTTP requests of the API for one server: URLs, authentication headers and bodies.
 * The token is only attached to requests for [server], never to other hosts.
 */
class ApiRequests(private val server: ServerConfig, private val json: Json = ApiJson) {

    /** Public endpoint: lets the app check a server before sending it the token. */
    fun health(): Request = Request.Builder().url(url("api", "health")).build()

    fun status(): Request = authenticated(url("api", "status")).build()

    fun documents(): Request = authenticated(url("api", "documents")).build()

    fun document(id: String): Request = authenticated(url("api", "documents", id)).build()

    /** Idempotent: creates the document with this client-side id, or updates it. */
    fun upsertDocument(id: String, body: DocumentUpsert): Request = authenticated(url("api", "documents", id))
        .put(json.encodeToString(DocumentUpsert.serializer(), body).toRequestBody(JSON))
        .build()

    /** Idempotent on [PageUpload.pageId]: the server ignores a page it already has. */
    fun uploadPage(upload: PageUpload, image: File): Request {
        val form = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("page_id", upload.pageId)
            .addFormDataPart("session_id", upload.sessionId)
            .addFormDataPart("seq", upload.seq.toString())
            .addFormDataPart("captured_at", upload.capturedAt)
        upload.pageNumberHint?.let { form.addFormDataPart("page_number_hint", it.toString()) }
        form.addFormDataPart("file", "${upload.pageId}.jpg", image.asRequestBody(JPEG))
        return authenticated(url("api", "documents", upload.documentId, "pages"))
            .post(form.build())
            .build()
    }

    private fun url(vararg segments: String): HttpUrl =
        server.baseUrl.newBuilder().apply { segments.forEach(::addPathSegment) }.build()

    private fun authenticated(url: HttpUrl): Request.Builder = Request.Builder()
        .url(url)
        .apply { authenticationHeaders(server).forEach { (name, value) -> header(name, value) } }

    private companion object {
        val JSON = "application/json; charset=utf-8".toMediaType()
        val JPEG = "image/jpeg".toMediaType()
    }
}
