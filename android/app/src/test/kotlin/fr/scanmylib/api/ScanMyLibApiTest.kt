package fr.scanmylib.api

import fr.scanmylib.expectFailure
import fr.scanmylib.model.ServerConfig
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ScanMyLibApiTest {

    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private val server = MockWebServer()
    private lateinit var api: ScanMyLibApi

    @Before
    fun setUp() {
        server.start()
        api = ScanMyLibApi(OkHttpClient(), ServerConfig(server.url("/"), TOKEN))
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun respond(code: Int, body: String) {
        server.enqueue(MockResponse.Builder().code(code).body(body).build())
    }

    @Test
    fun `lists the documents with the token`() = runTest {
        respond(200, """{"documents": [${ApiFixtures.DOCUMENT}]}""")
        assertEquals(listOf(ApiFixtures.DOCUMENT_ID), api.documents().map { it.id })

        val request = server.takeRequest()
        assertEquals("GET", request.method)
        assertEquals("/api/documents", request.url.encodedPath)
        assertEquals("Bearer $TOKEN", request.headers["Authorization"])
        assertEquals("1", request.headers["X-ScanMyLib"])
    }

    @Test
    fun `reads a document with its pages`() = runTest {
        respond(200, ApiFixtures.DOCUMENT_DETAIL)
        val detail = api.document(ApiFixtures.DOCUMENT_ID)
        assertEquals("Example Book", detail.document.title)
        assertEquals(listOf(ApiFixtures.PAGE_ID), detail.pages.map { it.id })
        assertEquals("/api/documents/${ApiFixtures.DOCUMENT_ID}", server.takeRequest().url.encodedPath)
    }

    @Test
    fun `uploads a page as multipart form data`() = runTest {
        respond(201, ApiFixtures.PAGE)
        val image = temporaryFolder.newFile("scan.jpg").apply { writeBytes(byteArrayOf(1, 2, 3)) }
        val upload = PageUpload(
            documentId = ApiFixtures.DOCUMENT_ID,
            pageId = ApiFixtures.PAGE_ID,
            sessionId = "0b1c2d3e-0000-4000-8000-000000000001",
            seq = 1,
            capturedAt = "2026-10-12T20:15:30+02:00",
            pageNumberHint = null,
        )
        assertEquals(ApiFixtures.PAGE_ID, api.uploadPage(upload, image).id)

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/documents/${ApiFixtures.DOCUMENT_ID}/pages", request.url.encodedPath)
        assertTrue(checkNotNull(request.headers["Content-Type"]).startsWith("multipart/form-data; boundary="))
    }

    @Test
    fun `an already uploaded page is a success too`() = runTest {
        respond(200, ApiFixtures.PAGE)
        val image = temporaryFolder.newFile("scan.jpg").apply { writeBytes(byteArrayOf(1)) }
        val upload = PageUpload(ApiFixtures.DOCUMENT_ID, ApiFixtures.PAGE_ID, "s", 1, "2026-10-12T20:15:30+02:00", 7)
        assertEquals(ApiFixtures.PAGE_ID, api.uploadPage(upload, image).id)
    }

    @Test
    fun `maps a refused token`() = runTest {
        respond(401, """{"detail": "unauthorized"}""")
        expectFailure<ApiException.Unauthorized> { api.status() }
    }

    @Test
    fun `maps HTTP errors with the server's detail`() = runTest {
        respond(404, """{"detail": "unknown document"}""")
        val notFound = expectFailure<ApiException.Http> { api.document("missing") }
        assertEquals(404, notFound.code)
        assertEquals("unknown document", notFound.detail)

        respond(422, """{"detail": [{"loc": ["body", "page_id"], "msg": "field required"}]}""")
        val invalid = expectFailure<ApiException.Http> { api.documents() }
        assertEquals(422, invalid.code)
        assertTrue(checkNotNull(invalid.detail).contains("page_id"))

        respond(502, "<html>Bad gateway</html>")
        val badGateway = expectFailure<ApiException.Http> { api.documents() }
        assertEquals(502, badGateway.code)
        assertNull(badGateway.detail)
    }

    @Test
    fun `reports answers that are not the expected JSON`() = runTest {
        respond(200, "<html>not an API</html>")
        expectFailure<ApiException.InvalidResponse> { api.status() }
        respond(200, """{"documents": [{"id": "no title"}]}""")
        expectFailure<ApiException.InvalidResponse> { api.documents() }
    }

    @Test
    fun `never forwards the token to another server through a redirect`() = runTest {
        MockWebServer().use { other ->
            other.start()
            other.enqueue(MockResponse.Builder().code(200).body(ApiFixtures.STATUS).build())
            server.enqueue(
                MockResponse.Builder().code(302).addHeader("Location", other.url("/api/status").toString()).build(),
            )

            api.status()

            assertEquals("Bearer $TOKEN", server.takeRequest().headers["Authorization"])
            assertNull(other.takeRequest().headers["Authorization"])
        }
    }

    @Test
    fun `reports an unreachable server`() = runTest {
        server.close()
        expectFailure<ApiException.Unreachable> { api.health() }
    }

    private companion object {
        const val TOKEN = "q9Xz-Lm_3vT0"
    }
}
