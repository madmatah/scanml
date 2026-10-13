package fr.scanmylib.api

import fr.scanmylib.model.DocumentKind
import fr.scanmylib.model.ServerConfig
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MultipartBody
import okhttp3.MultipartReader
import okhttp3.Request
import okio.Buffer
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ApiRequestsTest {

    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private val requests = ApiRequests(ServerConfig("http://192.168.1.10:8765/".toHttpUrl(), TOKEN))

    @Test
    fun `health is public and carries no token`() {
        val request = requests.health()
        assertEquals("GET", request.method)
        assertEquals("http://192.168.1.10:8765/api/health", request.url.toString())
        assertNull(request.header("Authorization"))
    }

    @Test
    fun `authenticated requests carry the token and the CSRF guard header`() {
        for (request in listOf(requests.status(), requests.documents(), requests.document(ApiFixtures.DOCUMENT_ID))) {
            assertEquals("Bearer $TOKEN", request.header("Authorization"))
            assertEquals("1", request.header("X-ScanMyLib"))
        }
        assertEquals("http://192.168.1.10:8765/api/status", requests.status().url.toString())
        assertEquals("http://192.168.1.10:8765/api/documents", requests.documents().url.toString())
        assertEquals(
            "http://192.168.1.10:8765/api/documents/${ApiFixtures.DOCUMENT_ID}",
            requests.document(ApiFixtures.DOCUMENT_ID).url.toString(),
        )
    }

    @Test
    fun `ids stay a single path segment`() {
        assertEquals("http://192.168.1.10:8765/api/documents/a%2F..%2Fb", requests.document("a/../b").url.toString())
    }

    @Test
    fun `document upsert is a JSON PUT`() {
        val request = requests.upsertDocument(
            ApiFixtures.DOCUMENT_ID,
            DocumentUpsert(title = "Sample Letters", author = "", kind = DocumentKind.DOCUMENT, unwarp = false),
        )
        assertEquals("PUT", request.method)
        assertEquals("http://192.168.1.10:8765/api/documents/${ApiFixtures.DOCUMENT_ID}", request.url.toString())
        assertEquals("Bearer $TOKEN", request.header("Authorization"))
        val body = checkNotNull(request.body)
        assertEquals("application/json; charset=utf-8", body.contentType().toString())
        assertEquals(
            """{"title":"Sample Letters","author":"","kind":"document","unwarp":false}""",
            Buffer().also(body::writeTo).readUtf8(),
        )
    }

    @Test
    fun `page upload is a multipart POST with the page metadata and the image`() {
        val image = temporaryFolder.newFile("scan.jpg").apply { writeBytes(IMAGE_BYTES) }
        val request = requests.uploadPage(upload(pageNumberHint = 13), image)

        assertEquals("POST", request.method)
        assertEquals(
            "http://192.168.1.10:8765/api/documents/${ApiFixtures.DOCUMENT_ID}/pages",
            request.url.toString(),
        )
        assertEquals("Bearer $TOKEN", request.header("Authorization"))
        assertEquals("1", request.header("X-ScanMyLib"))

        val form = readForm(request)
        assertEquals(
            mapOf(
                "page_id" to ApiFixtures.PAGE_ID,
                "session_id" to SESSION_ID,
                "seq" to "3",
                "captured_at" to "2026-10-12T20:15:30+02:00",
                "page_number_hint" to "13",
            ),
            form.fields,
        )
        val file = checkNotNull(form.file)
        assertEquals("""form-data; name="file"; filename="${ApiFixtures.PAGE_ID}.jpg"""", file.disposition)
        assertEquals("image/jpeg", file.contentType)
        assertArrayEquals(IMAGE_BYTES, file.bytes)
    }

    @Test
    fun `page upload without hint omits the field`() {
        val image = temporaryFolder.newFile("scan.jpg").apply { writeBytes(IMAGE_BYTES) }
        val form = readForm(requests.uploadPage(upload(pageNumberHint = null), image))
        assertFalse("page_number_hint" in form.fields)
    }

    @Test
    fun `the thumbnail of an uploaded page is where the server lists it`() {
        val page = ApiJson.decodeFromString(Page.serializer(), ApiFixtures.PAGE)
        assertEquals(page.thumbUrl, pageThumbUrl(page.id))
    }

    private fun upload(pageNumberHint: Int?) = PageUpload(
        documentId = ApiFixtures.DOCUMENT_ID,
        pageId = ApiFixtures.PAGE_ID,
        sessionId = SESSION_ID,
        seq = 3,
        capturedAt = "2026-10-12T20:15:30+02:00",
        pageNumberHint = pageNumberHint,
    )

    private class FilePart(val disposition: String?, val contentType: String?, val bytes: ByteArray)

    private class Form(val fields: Map<String, String>, val file: FilePart?)

    /** Parses the multipart body as the server would. */
    private fun readForm(request: Request): Form {
        val body = request.body as MultipartBody
        assertEquals("multipart/form-data; boundary=${body.boundary}", body.contentType().toString())
        val fields = mutableMapOf<String, String>()
        var file: FilePart? = null
        MultipartReader(Buffer().also(body::writeTo), body.boundary).use { reader ->
            while (true) {
                val part = reader.nextPart() ?: break
                val disposition = checkNotNull(part.headers["Content-Disposition"])
                if ("filename=" in disposition) {
                    file = FilePart(disposition, part.headers["Content-Type"], part.body.readByteArray())
                } else {
                    val name = checkNotNull(Regex("name=\"([^\"]+)\"").find(disposition)).groupValues[1]
                    fields[name] = part.body.readUtf8()
                }
            }
        }
        return Form(fields, file)
    }

    private companion object {
        const val TOKEN = "q9Xz-Lm_3vT0"
        const val SESSION_ID = "0b1c2d3e-0000-4000-8000-000000000001"
        val IMAGE_BYTES = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte(), 0xE0.toByte(), 1, 2, 3)
    }
}
