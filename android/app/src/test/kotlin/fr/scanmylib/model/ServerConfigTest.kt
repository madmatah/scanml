package fr.scanmylib.model

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ServerConfigTest {
    @RunWith(Enclosed::class)
    class TheResolveMethod {
        @RunWith(Parameterized::class)
        class WhenTheUrlIsOnTheServer(private val case: String, private val serverUrl: String) {
            private lateinit var resolution: Resolution

            @Before
            fun resolveTheUrl() {
                resolution = Resolution(SERVER.resolve(serverUrl))
            }

            @Test
            fun `should resolve it against the server's address`() {
                assertEquals(case, "http://192.168.1.10:8765/api/pages/p1/thumb", resolution.url.toString())
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun urls(): List<Array<Any>> = listOf(
                    arrayOf("a path", "/api/pages/p1/thumb"),
                    arrayOf("an absolute URL of the server", "http://192.168.1.10:8765/api/pages/p1/thumb"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheUrlLeadsToAnotherOrigin(private val case: String, private val serverUrl: String) {
            private lateinit var resolution: Resolution

            @Before
            fun resolveTheUrl() {
                resolution = Resolution(SERVER.resolve(serverUrl))
            }

            @Test
            fun `should resolve to nothing, since another origin must never receive the token`() {
                assertNull(case, resolution.url)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun origins(): List<Array<Any>> = listOf(
                    arrayOf("another host", "http://evil.example/api/pages/p1/thumb"),
                    arrayOf("another host, without a scheme", "//evil.example/api/pages/p1/thumb"),
                    arrayOf("another host, after backslashes", "\\\\evil.example/x"),
                    arrayOf("another host, behind a user name", "http://192.168.1.10:8765@evil.example/x"),
                    arrayOf("another port", "http://192.168.1.10:9999/x"),
                    arrayOf("another scheme", "https://192.168.1.10:8765/x"),
                    arrayOf("a script", "javascript:alert(1)"),
                )
            }
        }
    }

    class TheToStringMethod {
        private lateinit var text: String

        @Before
        fun writeTheServer() {
            text = SERVER.toString()
        }

        @Test
        fun `should keep the token out, so that logs and crash reports never show it`() {
            assertFalse(TOKEN in text)
        }
    }
}

private const val TOKEN = "q9Xz-Lm_3vT0"

private val SERVER = ServerConfig("http://192.168.1.10:8765/".toHttpUrl(), TOKEN)

private data class Resolution(val url: HttpUrl?)
