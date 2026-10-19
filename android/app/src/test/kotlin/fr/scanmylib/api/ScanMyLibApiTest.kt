package fr.scanmylib.api

import java.io.File
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.BeforeClass
import org.junit.ClassRule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class ScanMyLibApiTest {
    @RunWith(Enclosed::class)
    class TheDocumentsMethod {
        class WhenTheServerListsADocument {
            @Test
            fun `should return it`() {
                assertEquals(listOf(ApiFixtures.DOCUMENT_ID), documentIds)
            }

            @Test
            fun `should send a GET`() {
                assertEquals("GET", request.method)
            }

            @Test
            fun `should ask for the documents`() {
                assertEquals("/api/documents", request.url.encodedPath)
            }

            @Test
            fun `should carry the token`() {
                assertEquals("Bearer ${ApiFixtures.TOKEN}", request.headers["Authorization"])
            }

            @Test
            fun `should carry the CSRF guard header`() {
                assertEquals("1", request.headers["X-ScanMyLib"])
            }

            companion object {
                private lateinit var documentIds: List<String>
                private lateinit var request: RecordedRequest

                @BeforeClass
                @JvmStatic
                fun listTheDocuments() = runTest {
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, """{"documents": [${ApiFixtures.DOCUMENT}]}"""))
                        documentIds = MockPc.buildApi(server.url("/")).documents().map { it.id }
                        request = server.takeRequest()
                    }
                }
            }
        }

        class WhenTheRequestIsInvalid {
            private val validationErrors = """{"detail": [{"loc": ["body", "page_id"], "msg": "field required"}]}"""
            private lateinit var server: MockWebServer
            private lateinit var listTheDocuments: suspend () -> List<Document>

            @Before
            fun answerWithValidationErrors() {
                server = MockWebServer()
                server.start()
                server.enqueue(MockPc.buildResponse(422, validationErrors))
                val api = MockPc.buildApi(server.url("/"))
                listTheDocuments = { api.documents() }
            }

            @After
            fun stopTheServer() {
                server.close()
            }

            @Test
            fun `should fail with the HTTP status`() = runTest {
                val failure = runCatching { listTheDocuments() }.exceptionOrNull()
                assertEquals(ApiException.Http::class.java, failure?.javaClass)
                assertEquals(422, (failure as ApiException.Http).code)
            }

            @Test
            fun `should give the validation errors of the server as its detail`() = runTest {
                val failure = runCatching { listTheDocuments() }.exceptionOrNull()
                assertEquals(ApiException.Http::class.java, failure?.javaClass)
                val detail = (failure as ApiException.Http).detail.orEmpty()
                assertTrue(detail.contains("page_id"))
                assertEquals("HTTP 422: $detail", failure.message)
            }
        }

        class WhenTheGatewayFailsWithoutJson {
            private lateinit var server: MockWebServer
            private lateinit var listTheDocuments: suspend () -> List<Document>

            @Before
            fun answerWithABadGateway() {
                server = MockWebServer()
                server.start()
                server.enqueue(MockPc.buildResponse(502, "<html>Bad gateway</html>"))
                val api = MockPc.buildApi(server.url("/"))
                listTheDocuments = { api.documents() }
            }

            @After
            fun stopTheServer() {
                server.close()
            }

            @Test
            fun `should fail with the HTTP status`() = runTest {
                val failure = runCatching { listTheDocuments() }.exceptionOrNull()
                assertEquals(ApiException.Http::class.java, failure?.javaClass)
                assertEquals(502, (failure as ApiException.Http).code)
            }

            @Test
            fun `should give no detail, since the answer holds none`() = runTest {
                val failure = runCatching { listTheDocuments() }.exceptionOrNull()
                assertEquals(ApiException.Http::class.java, failure?.javaClass)
                assertEquals("HTTP 502", failure?.message)
                assertNull((failure as ApiException.Http).detail)
            }
        }

        class WhenADocumentLacksItsTitle {
            private lateinit var server: MockWebServer
            private lateinit var listTheDocuments: suspend () -> List<Document>

            @Before
            fun answerWithAnIncompleteDocument() {
                server = MockWebServer()
                server.start()
                server.enqueue(MockPc.buildResponse(200, """{"documents": [{"id": "no title"}]}"""))
                val api = MockPc.buildApi(server.url("/"))
                listTheDocuments = { api.documents() }
            }

            @After
            fun stopTheServer() {
                server.close()
            }

            @Test
            fun `should fail as an unexpected response`() = runTest {
                val failure = runCatching { listTheDocuments() }.exceptionOrNull()
                assertEquals(ApiException.InvalidResponse::class.java, failure?.javaClass)
                assertEquals("unexpected response", failure?.message?.substringBefore(":"))
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDocumentMethod {
        class WhenTheServerAnswersWithTheDocumentAndItsPages {
            @Test
            fun `should read the document`() {
                assertEquals("Example Book", detail.document.title)
            }

            @Test
            fun `should read its pages`() {
                assertEquals(listOf(ApiFixtures.PAGE_ID), detail.pages.map { it.id })
            }

            @Test
            fun `should ask for the document`() {
                assertEquals("/api/documents/${ApiFixtures.DOCUMENT_ID}", request.url.encodedPath)
            }

            companion object {
                private lateinit var detail: DocumentDetail
                private lateinit var request: RecordedRequest

                @BeforeClass
                @JvmStatic
                fun readTheDocument() = runTest {
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, ApiFixtures.DOCUMENT_DETAIL))
                        detail = MockPc.buildApi(server.url("/")).document(ApiFixtures.DOCUMENT_ID)
                        request = server.takeRequest()
                    }
                }
            }
        }

        class WhenTheDocumentIsUnknown {
            private lateinit var server: MockWebServer
            private lateinit var readTheDocument: suspend () -> DocumentDetail

            @Before
            fun answerWithNotFound() {
                server = MockWebServer()
                server.start()
                server.enqueue(MockPc.buildResponse(404, """{"detail": "unknown document"}"""))
                val api = MockPc.buildApi(server.url("/"))
                readTheDocument = { api.document("missing") }
            }

            @After
            fun stopTheServer() {
                server.close()
            }

            @Test
            fun `should fail with the HTTP status`() = runTest {
                val failure = runCatching { readTheDocument() }.exceptionOrNull()
                assertEquals(ApiException.Http::class.java, failure?.javaClass)
                assertEquals(404, (failure as ApiException.Http).code)
            }

            @Test
            fun `should give the detail of the server`() = runTest {
                val failure = runCatching { readTheDocument() }.exceptionOrNull()
                assertEquals(ApiException.Http::class.java, failure?.javaClass)
                assertEquals("HTTP 404: unknown document", failure?.message)
                assertEquals("unknown document", (failure as ApiException.Http).detail)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheUploadPageMethod {
        class WhenTheServerCreatesThePage {
            @Test
            fun `should return the page`() {
                assertEquals(ApiFixtures.PAGE_ID, page.id)
            }

            @Test
            fun `should send a POST`() {
                assertEquals("POST", request.method)
            }

            @Test
            fun `should send it to the pages of the document`() {
                assertEquals("/api/documents/${ApiFixtures.DOCUMENT_ID}/pages", request.url.encodedPath)
            }

            @Test
            fun `should send it as multipart form data`() {
                assertTrue(request.headers["Content-Type"].orEmpty().startsWith("multipart/form-data; boundary="))
            }

            companion object {
                @ClassRule
                @JvmField
                val temporaryFolder = TemporaryFolder()

                private lateinit var page: Page
                private lateinit var request: RecordedRequest

                @BeforeClass
                @JvmStatic
                fun uploadThePage() = runTest {
                    val image = writeImage(temporaryFolder, byteArrayOf(1, 2, 3))
                    val upload = ApiFixtures.buildPageUpload(seq = 1, pageNumberHint = null)
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(201, ApiFixtures.PAGE))
                        page = MockPc.buildApi(server.url("/")).uploadPage(upload, image)
                        request = server.takeRequest()
                    }
                }
            }
        }

        class WhenTheServerAlreadyHasThePage {
            @Test
            fun `should return the page, as a success`() {
                assertEquals(ApiFixtures.PAGE_ID, page.id)
            }

            companion object {
                @ClassRule
                @JvmField
                val temporaryFolder = TemporaryFolder()

                private lateinit var page: Page

                @BeforeClass
                @JvmStatic
                fun uploadThePageAgain() = runTest {
                    val image = writeImage(temporaryFolder, byteArrayOf(1))
                    val upload = ApiFixtures.buildPageUpload(seq = 1, pageNumberHint = 7)
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, ApiFixtures.PAGE))
                        page = MockPc.buildApi(server.url("/")).uploadPage(upload, image)
                    }
                }
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheStatusMethod {
        class WhenTheServerRefusesTheToken {
            private lateinit var server: MockWebServer
            private lateinit var readTheStatus: suspend () -> ServerStatus

            @Before
            fun answerWithARefusal() {
                server = MockWebServer()
                server.start()
                server.enqueue(MockPc.buildResponse(401, """{"detail": "unauthorized"}"""))
                val api = MockPc.buildApi(server.url("/"))
                readTheStatus = { api.status() }
            }

            @After
            fun stopTheServer() {
                server.close()
            }

            @Test
            fun `should fail as unauthorized`() = runTest {
                val failure = runCatching { readTheStatus() }.exceptionOrNull()
                assertEquals(ApiException.Unauthorized::class.java, failure?.javaClass)
                assertEquals("token refused", failure?.message)
            }
        }

        class WhenTheAnswerIsNoJson {
            private lateinit var server: MockWebServer
            private lateinit var readTheStatus: suspend () -> ServerStatus

            @Before
            fun answerWithHtml() {
                server = MockWebServer()
                server.start()
                server.enqueue(MockPc.buildResponse(200, "<html>not an API</html>"))
                val api = MockPc.buildApi(server.url("/"))
                readTheStatus = { api.status() }
            }

            @After
            fun stopTheServer() {
                server.close()
            }

            @Test
            fun `should fail as an unexpected response`() = runTest {
                val failure = runCatching { readTheStatus() }.exceptionOrNull()
                assertEquals(ApiException.InvalidResponse::class.java, failure?.javaClass)
                assertEquals("unexpected response", failure?.message?.substringBefore(":"))
            }
        }

        class WhenTheServerRedirectsToAnotherServer {
            @Test
            fun `should send the token to the server`() {
                assertEquals("Bearer ${ApiFixtures.TOKEN}", requestToTheServer.headers["Authorization"])
            }

            @Test
            fun `should never forward the token to the other server`() {
                assertNull(requestToTheOtherServer.headers["Authorization"])
            }

            companion object {
                private lateinit var requestToTheServer: RecordedRequest
                private lateinit var requestToTheOtherServer: RecordedRequest

                @BeforeClass
                @JvmStatic
                fun followTheRedirect() = runTest {
                    MockWebServer().use { server ->
                        MockWebServer().use { otherServer ->
                            server.start()
                            otherServer.start()
                            otherServer.enqueue(MockPc.buildResponse(200, ApiFixtures.STATUS))
                            server.enqueue(
                                MockResponse.Builder()
                                    .code(302)
                                    .addHeader("Location", otherServer.url("/api/status").toString())
                                    .build(),
                            )
                            MockPc.buildApi(server.url("/")).status()
                            requestToTheServer = server.takeRequest()
                            requestToTheOtherServer = otherServer.takeRequest()
                        }
                    }
                }
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheHealthMethod {
        class WhenTheServerIsUnreachable {
            private lateinit var checkTheHealth: suspend () -> Health

            @Before
            fun addressAStoppedServer() {
                val address = MockWebServer().use { server ->
                    server.start()
                    server.url("/")
                }
                val api = MockPc.buildApi(address)
                checkTheHealth = { api.health() }
            }

            @Test
            fun `should fail as unreachable`() = runTest {
                val failure = runCatching { checkTheHealth() }.exceptionOrNull()
                assertEquals(ApiException.Unreachable::class.java, failure?.javaClass)
                assertEquals("server unreachable", failure?.message?.substringBefore(":"))
            }
        }
    }
}

private fun writeImage(folder: TemporaryFolder, bytes: ByteArray): File =
    folder.newFile("scan.jpg").apply { writeBytes(bytes) }
