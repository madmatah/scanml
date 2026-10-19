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
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ApiRequestsTest {
    class TheHealthMethod {
        private lateinit var request: Request

        @Before
        fun buildTheRequest() {
            request = ApiRequests(SERVER).health()
        }

        @Test
        fun `should be a GET`() {
            assertEquals("GET", request.method)
        }

        @Test
        fun `should address the health of the server`() {
            assertEquals("http://192.168.1.10:8765/api/health", request.url.toString())
        }

        @Test
        fun `should carry no token, so that the app checks a server before sending it the token`() {
            assertNull(request.header("Authorization"))
        }
    }

    @RunWith(Parameterized::class)
    class TheAuthenticatedReadMethods(
        private val case: String,
        private val buildRequest: (ApiRequests) -> Request,
        private val expectedUrl: String,
    ) {
        private lateinit var request: Request

        @Before
        fun buildTheRequest() {
            request = buildRequest(ApiRequests(SERVER))
        }

        @Test
        fun `should carry the token`() {
            assertEquals(case, "Bearer ${ApiFixtures.TOKEN}", request.header("Authorization"))
        }

        @Test
        fun `should carry the CSRF guard header`() {
            assertEquals(case, "1", request.header("X-ScanMyLib"))
        }

        @Test
        fun `should address its endpoint`() {
            assertEquals(case, expectedUrl, request.url.toString())
        }

        companion object {
            @JvmStatic
            @Parameterized.Parameters(name = "{0}")
            fun methods(): List<Array<Any>> = listOf(
                arrayOf("status()", ApiRequests::status, "http://192.168.1.10:8765/api/status"),
                arrayOf("documents()", ApiRequests::documents, "http://192.168.1.10:8765/api/documents"),
                arrayOf(
                    "document(id)",
                    { requests: ApiRequests -> requests.document(ApiFixtures.DOCUMENT_ID) },
                    "http://192.168.1.10:8765/api/documents/${ApiFixtures.DOCUMENT_ID}",
                ),
            )
        }
    }

    @RunWith(Enclosed::class)
    class TheDocumentMethod {
        class WhenTheIdHoldsSlashes {
            private lateinit var request: Request

            @Before
            fun buildTheRequest() {
                request = ApiRequests(SERVER).document("a/../b")
            }

            @Test
            fun `should keep it a single path segment`() {
                assertEquals("http://192.168.1.10:8765/api/documents/a%2F..%2Fb", request.url.toString())
            }
        }
    }

    class TheUpsertDocumentMethod {
        private lateinit var request: Request
        private lateinit var body: String

        @Before
        fun buildTheRequest() {
            request = ApiRequests(SERVER).upsertDocument(
                ApiFixtures.DOCUMENT_ID,
                DocumentUpsert(title = "Sample Letters", author = "", kind = DocumentKind.DOCUMENT, unwarp = false),
            )
            body = Buffer().also { request.body?.writeTo(it) }.readUtf8()
        }

        @Test
        fun `should be a PUT`() {
            assertEquals("PUT", request.method)
        }

        @Test
        fun `should address the document`() {
            assertEquals("http://192.168.1.10:8765/api/documents/${ApiFixtures.DOCUMENT_ID}", request.url.toString())
        }

        @Test
        fun `should carry the token`() {
            assertEquals("Bearer ${ApiFixtures.TOKEN}", request.header("Authorization"))
        }

        @Test
        fun `should carry the CSRF guard header`() {
            assertEquals("1", request.header("X-ScanMyLib"))
        }

        @Test
        fun `should send JSON`() {
            assertEquals("application/json; charset=utf-8", request.body?.contentType().toString())
        }

        @Test
        fun `should send the fields of the document`() {
            assertEquals("""{"title":"Sample Letters","author":"","kind":"document","unwarp":false}""", body)
        }
    }

    @RunWith(Enclosed::class)
    class TheUploadPageMethod {
        class WhenThePageHasANumberHint {
            @get:Rule
            val temporaryFolder = TemporaryFolder()

            private lateinit var request: Request
            private lateinit var form: MultipartForm

            @Before
            fun buildTheRequest() {
                val image = temporaryFolder.newFile("scan.jpg").apply { writeBytes(IMAGE_BYTES) }
                val upload = ApiFixtures.buildPageUpload(seq = 3, pageNumberHint = 13)
                request = ApiRequests(SERVER).uploadPage(upload, image)
                form = readForm(request.body as MultipartBody)
            }

            @Test
            fun `should be a POST`() {
                assertEquals("POST", request.method)
            }

            @Test
            fun `should address the pages of the document`() {
                assertEquals(
                    "http://192.168.1.10:8765/api/documents/${ApiFixtures.DOCUMENT_ID}/pages",
                    request.url.toString(),
                )
            }

            @Test
            fun `should carry the token`() {
                assertEquals("Bearer ${ApiFixtures.TOKEN}", request.header("Authorization"))
            }

            @Test
            fun `should carry the CSRF guard header`() {
                assertEquals("1", request.header("X-ScanMyLib"))
            }

            @Test
            fun `should send a multipart form`() {
                assertEquals("multipart/form-data; boundary=${form.boundary}", form.contentType)
            }

            @Test
            fun `should send the metadata of the page, its hint included`() {
                assertEquals(
                    mapOf(
                        "page_id" to ApiFixtures.PAGE_ID,
                        "session_id" to ApiFixtures.SESSION_ID,
                        "seq" to "3",
                        "captured_at" to ApiFixtures.CAPTURED_AT,
                        "page_number_hint" to "13",
                    ),
                    form.fields,
                )
            }

            @Test
            fun `should name the image after the page`() {
                assertEquals(
                    """form-data; name="file"; filename="${ApiFixtures.PAGE_ID}.jpg"""",
                    form.file?.disposition,
                )
            }

            @Test
            fun `should send the image as a JPEG`() {
                assertEquals("image/jpeg", form.file?.contentType)
            }

            @Test
            fun `should send the bytes of the image`() {
                assertArrayEquals(IMAGE_BYTES, form.file?.bytes)
            }
        }

        class WhenThePageHasNoNumberHint {
            @get:Rule
            val temporaryFolder = TemporaryFolder()

            private lateinit var form: MultipartForm

            @Before
            fun buildTheRequest() {
                val image = temporaryFolder.newFile("scan.jpg").apply { writeBytes(IMAGE_BYTES) }
                val upload = ApiFixtures.buildPageUpload(seq = 3, pageNumberHint = null)
                val request = ApiRequests(SERVER).uploadPage(upload, image)
                form = readForm(request.body as MultipartBody)
            }

            @Test
            fun `should leave the hint out of the form`() {
                assertEquals(
                    mapOf(
                        "page_id" to ApiFixtures.PAGE_ID,
                        "session_id" to ApiFixtures.SESSION_ID,
                        "seq" to "3",
                        "captured_at" to ApiFixtures.CAPTURED_AT,
                    ),
                    form.fields,
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class ThePageThumbUrlFunction {
        class WhenGivenTheIdOfAnUploadedPage {
            private lateinit var page: Page
            private lateinit var thumbUrl: String

            @Before
            fun locateTheThumbnail() {
                page = ApiJson.decodeFromString(Page.serializer(), ApiFixtures.PAGE)
                thumbUrl = pageThumbUrl(page.id)
            }

            @Test
            fun `should be where the server lists the thumbnail of the page`() {
                assertEquals(page.thumbUrl, thumbUrl)
            }
        }
    }
}

private val IMAGE_BYTES = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte(), 0xE0.toByte(), 1, 2, 3)
private val SERVER = ServerConfig("http://192.168.1.10:8765/".toHttpUrl(), ApiFixtures.TOKEN)

private class FormFile(val disposition: String, val contentType: String?, val bytes: ByteArray)

private class MultipartForm(
    val contentType: String,
    val boundary: String,
    val fields: Map<String, String>,
    val file: FormFile?,
)

private fun readForm(body: MultipartBody): MultipartForm {
    val fields = mutableMapOf<String, String>()
    val files = mutableListOf<FormFile>()
    MultipartReader(Buffer().also(body::writeTo), body.boundary).use { reader ->
        generateSequence { reader.nextPart() }.forEach { part ->
            val disposition = checkNotNull(part.headers["Content-Disposition"])
            if ("filename=" in disposition) {
                files += FormFile(disposition, part.headers["Content-Type"], part.body.readByteArray())
            } else {
                val name = checkNotNull(Regex("name=\"([^\"]+)\"").find(disposition)).groupValues[1]
                fields[name] = part.body.readUtf8()
            }
        }
    }
    return MultipartForm(body.contentType().toString(), body.boundary, fields, files.singleOrNull())
}
