package fr.scanmylib.pairing

import fr.scanmylib.api.ApiFixtures
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.model.ServerConfig
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

class ConnectionCheckTest {

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
    fun `succeeds with a ScanMyLib server that accepts the token`() = runTest {
        respond(200, ApiFixtures.HEALTH)
        respond(200, ApiFixtures.STATUS)

        val check = checkConnection(api)

        assertEquals("idle", (check as ConnectionCheck.Ok).status.ocr.state)
        val health = server.takeRequest()
        assertEquals("/api/health", health.url.encodedPath)
        assertNull("the token is only sent once the server is identified", health.headers["Authorization"])
        val status = server.takeRequest()
        assertEquals("/api/status", status.url.encodedPath)
        assertEquals("Bearer $TOKEN", status.headers["Authorization"])
    }

    @Test
    fun `never sends the token to something else than ScanMyLib`() = runTest {
        respond(404, "<html>Not found</html>")
        assertEquals(ConnectionCheck.NotScanMyLib, checkConnection(api))
        respond(200, """{"name": "SomethingElse", "version": "1", "api": 1}""")
        assertEquals(ConnectionCheck.NotScanMyLib, checkConnection(api))
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `rejects another version of the API`() = runTest {
        respond(200, """{"name": "ScanMyLib", "version": "2.0.0", "api": 2}""")
        assertEquals(ConnectionCheck.IncompatibleServer, checkConnection(api))
    }

    @Test
    fun `reports a refused token`() = runTest {
        respond(200, ApiFixtures.HEALTH)
        respond(401, """{"detail": "unauthorized"}""")
        assertEquals(ConnectionCheck.TokenRefused, checkConnection(api))
    }

    @Test
    fun `reports server errors`() = runTest {
        respond(200, ApiFixtures.HEALTH)
        respond(500, """{"detail": "database locked"}""")
        assertEquals(ConnectionCheck.Failed("HTTP 500: database locked"), checkConnection(api))
    }

    @Test
    fun `reports an unreachable server`() = runTest {
        server.close()
        assertEquals(ConnectionCheck.Unreachable, checkConnection(api))
    }

    private companion object {
        const val TOKEN = "q9Xz-Lm_3vT0"
    }
}
