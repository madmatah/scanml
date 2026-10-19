package fr.scanmylib.pairing

import fr.scanmylib.api.ApiFixtures
import fr.scanmylib.api.MockPc
import fr.scanmylib.api.OcrStatus
import fr.scanmylib.api.QueueCounts
import fr.scanmylib.api.ServerStatus
import kotlin.properties.Delegates
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.BeforeClass
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class ConnectionCheckTest {
    @RunWith(Enclosed::class)
    class TheCheckConnectionFunction {
        class WhenTheServerIsScanMyLibAndAcceptsTheToken {
            @Test
            fun `should succeed with the status of the server`() {
                assertEquals(
                    ConnectionCheck.Ok(
                        ServerStatus(
                            version = "0.1.0",
                            ocr = OcrStatus(state = "idle", lastError = null),
                            queue = QueueCounts(queued = 3, processing = 1),
                        ),
                    ),
                    check,
                )
            }

            @Test
            fun `should first ask for the health of the server`() {
                assertEquals("/api/health", requests[0].url.encodedPath)
            }

            @Test
            fun `should ask for the health without the token, which it sends only once the server is identified`() {
                assertNull(requests[0].headers["Authorization"])
            }

            @Test
            fun `should then ask for the status`() {
                assertEquals("/api/status", requests[1].url.encodedPath)
            }

            @Test
            fun `should ask for the status with the token`() {
                assertEquals("Bearer ${ApiFixtures.TOKEN}", requests[1].headers["Authorization"])
            }

            companion object {
                private lateinit var check: ConnectionCheck
                private lateinit var requests: List<RecordedRequest>

                @BeforeClass
                @JvmStatic
                fun checkTheConnection() = runTest {
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, ApiFixtures.HEALTH))
                        server.enqueue(MockPc.buildResponse(200, ApiFixtures.STATUS))
                        check = checkConnection(MockPc.buildApi(server.url("/")))
                        requests = List(server.requestCount) { server.takeRequest() }
                    }
                }
            }
        }

        class WhenSomethingElseAnswersWithAnError {
            @Test
            fun `should find no ScanMyLib server`() {
                assertEquals(ConnectionCheck.NotScanMyLib, check)
            }

            @Test
            fun `should ask nothing more, so that the token never reaches it`() {
                assertEquals(1, requestCount)
            }

            companion object {
                private lateinit var check: ConnectionCheck
                private var requestCount by Delegates.notNull<Int>()

                @BeforeClass
                @JvmStatic
                fun checkTheConnection() = runTest {
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(404, "<html>Not found</html>"))
                        check = checkConnection(MockPc.buildApi(server.url("/")))
                        requestCount = server.requestCount
                    }
                }
            }
        }

        class WhenAnotherServerIdentifiesItself {
            @Test
            fun `should find no ScanMyLib server`() {
                assertEquals(ConnectionCheck.NotScanMyLib, check)
            }

            @Test
            fun `should ask nothing more, so that the token never reaches it`() {
                assertEquals(1, requestCount)
            }

            companion object {
                private lateinit var check: ConnectionCheck
                private var requestCount by Delegates.notNull<Int>()

                @BeforeClass
                @JvmStatic
                fun checkTheConnection() = runTest {
                    val otherHealth = """{"name": "SomethingElse", "version": "1", "api": 1}"""
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, otherHealth))
                        check = checkConnection(MockPc.buildApi(server.url("/")))
                        requestCount = server.requestCount
                    }
                }
            }
        }

        class WhenTheServerSpeaksAnotherVersionOfTheApi {
            @Test
            fun `should find the server incompatible`() {
                assertEquals(ConnectionCheck.IncompatibleServer, check)
            }

            companion object {
                private lateinit var check: ConnectionCheck

                @BeforeClass
                @JvmStatic
                fun checkTheConnection() = runTest {
                    val newerHealth = """{"name": "ScanMyLib", "version": "2.0.0", "api": 2}"""
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, newerHealth))
                        check = checkConnection(MockPc.buildApi(server.url("/")))
                    }
                }
            }
        }

        class WhenTheServerRefusesTheToken {
            @Test
            fun `should report the token refused`() {
                assertEquals(ConnectionCheck.TokenRefused, check)
            }

            companion object {
                private lateinit var check: ConnectionCheck

                @BeforeClass
                @JvmStatic
                fun checkTheConnection() = runTest {
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, ApiFixtures.HEALTH))
                        server.enqueue(MockPc.buildResponse(401, """{"detail": "unauthorized"}"""))
                        check = checkConnection(MockPc.buildApi(server.url("/")))
                    }
                }
            }
        }

        class WhenTheServerFails {
            @Test
            fun `should report the failure, with the detail of the server`() {
                assertEquals(ConnectionCheck.Failed("HTTP 500: database locked"), check)
            }

            companion object {
                private lateinit var check: ConnectionCheck

                @BeforeClass
                @JvmStatic
                fun checkTheConnection() = runTest {
                    MockWebServer().use { server ->
                        server.start()
                        server.enqueue(MockPc.buildResponse(200, ApiFixtures.HEALTH))
                        server.enqueue(MockPc.buildResponse(500, """{"detail": "database locked"}"""))
                        check = checkConnection(MockPc.buildApi(server.url("/")))
                    }
                }
            }
        }

        class WhenTheServerIsUnreachable {
            @Test
            fun `should report it unreachable`() {
                assertEquals(ConnectionCheck.Unreachable, check)
            }

            companion object {
                private lateinit var check: ConnectionCheck

                @BeforeClass
                @JvmStatic
                fun checkTheConnection() = runTest {
                    val address = MockWebServer().use { server ->
                        server.start()
                        server.url("/")
                    }
                    check = checkConnection(MockPc.buildApi(address))
                }
            }
        }
    }
}
