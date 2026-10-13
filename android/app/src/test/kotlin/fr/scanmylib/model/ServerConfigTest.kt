package fr.scanmylib.model

import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class ServerConfigTest {

    private val server = ServerConfig("http://192.168.1.10:8765/".toHttpUrl(), TOKEN)

    @Test
    fun `resolves the URLs given by the server against its address`() {
        assertEquals(
            "http://192.168.1.10:8765/api/pages/p1/thumb",
            server.resolve("/api/pages/p1/thumb").toString(),
        )
        assertEquals(
            "http://192.168.1.10:8765/api/pages/p1/thumb",
            server.resolve("http://192.168.1.10:8765/api/pages/p1/thumb").toString(),
        )
    }

    @Test
    fun `never resolves to another origin, which must not receive the token`() {
        assertNull(server.resolve("http://evil.example/api/pages/p1/thumb"))
        assertNull(server.resolve("//evil.example/api/pages/p1/thumb"))
        assertNull(server.resolve("\\\\evil.example/x"))
        assertNull(server.resolve("http://192.168.1.10:8765@evil.example/x"))
        assertNull(server.resolve("http://192.168.1.10:9999/x"))
        assertNull(server.resolve("https://192.168.1.10:8765/x"))
        assertNull(server.resolve("javascript:alert(1)"))
    }

    @Test
    fun `keeps the token out of its text form`() {
        assertFalse(TOKEN in server.toString())
    }

    private companion object {
        const val TOKEN = "q9Xz-Lm_3vT0"
    }
}
