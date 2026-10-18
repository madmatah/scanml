package fr.scanmylib.api

import fr.scanmylib.model.ServerConfig
import java.io.File
import java.io.IOException
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response

/**
 * Client of the ScanMyLib HTTP API (docs/API.md) for one server. Calls are main-safe and report
 * failures as [ApiException].
 */
class ScanMyLibApi(private val http: OkHttpClient, server: ServerConfig, private val json: Json = ApiJson) {
    private val requests = ApiRequests(server, json)

    suspend fun health(): Health = call(requests.health(), Health.serializer())

    suspend fun status(): ServerStatus = call(requests.status(), ServerStatus.serializer())

    suspend fun documents(): List<Document> = call(requests.documents(), DocumentList.serializer()).documents

    suspend fun document(id: String): DocumentDetail = call(requests.document(id)) { body ->
        val element = json.parseToJsonElement(body)
        DocumentDetail(
            document = json.decodeFromJsonElement(Document.serializer(), element),
            pages = json.decodeFromJsonElement(PageList.serializer(), element).pages,
        )
    }

    suspend fun upsertDocument(id: String, body: DocumentUpsert): Document =
        call(requests.upsertDocument(id, body), Document.serializer())

    suspend fun uploadPage(upload: PageUpload, image: File): Page =
        call(requests.uploadPage(upload, image), Page.serializer())

    private suspend fun <T> call(request: Request, deserializer: DeserializationStrategy<T>): T =
        call(request) { body -> json.decodeFromString(deserializer, body) }

    private suspend fun <T> call(request: Request, decode: (String) -> T): T = withContext(Dispatchers.IO) {
        val response = try {
            http.newCall(request).await()
        } catch (e: IOException) {
            throw ApiException.Unreachable(e)
        }
        response.use {
            val body = try {
                it.body.string()
            } catch (e: IOException) {
                throw ApiException.Unreachable(e)
            }
            if (it.code == 401) throw ApiException.Unauthorized()
            if (!it.isSuccessful) throw ApiException.Http(it.code, errorDetail(body))
            try {
                decode(body)
            } catch (e: IllegalArgumentException) { // includes kotlinx.serialization errors
                throw ApiException.InvalidResponse(e)
            }
        }
    }

    /** The `detail` of a FastAPI error body: a message, or the JSON of validation errors. */
    private fun errorDetail(body: String): String? = try {
        when (val detail = json.parseToJsonElement(body).jsonObject["detail"]) {
            null, JsonNull -> null
            is JsonPrimitive -> detail.content
            else -> detail.toString()
        }
    } catch (e: IllegalArgumentException) {
        null
    }
}

/** Suspends until the call completes; canceling the coroutine cancels the call. */
private suspend fun Call.await(): Response = suspendCancellableCoroutine { continuation ->
    continuation.invokeOnCancellation { cancel() }
    enqueue(
        object : Callback {
            override fun onResponse(call: Call, response: Response) {
                continuation.resume(response) { _, value, _ -> value.close() }
            }

            override fun onFailure(call: Call, e: IOException) {
                continuation.resumeWithException(e)
            }
        },
    )
}
