package fr.scanmylib.pairing

import kotlin.properties.Delegates
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ServerAddressTest {
    @RunWith(Enclosed::class)
    class TheParseMethod {
        @RunWith(Parameterized::class)
        class WhenGivenTheRootUrlOfTheServer(private val case: String, private val input: String) {
            private lateinit var address: AddressResult

            @Before
            fun parseTheAddress() {
                address = ServerAddress.parse(input)
            }

            @Test
            fun `should accept it, with the root path`() {
                assertEquals(case, AddressResult.Valid("http://192.168.1.10:8765/".toHttpUrl()), address)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun urls(): List<Array<Any>> = listOf(
                    arrayOf("without a final slash", "http://192.168.1.10:8765"),
                    arrayOf("with a final slash", "http://192.168.1.10:8765/"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheSchemeIsMissing(
            private val case: String,
            private val input: String,
            private val expected: String,
        ) {
            private lateinit var address: AddressResult

            @Before
            fun parseTheAddress() {
                address = ServerAddress.parse(input)
            }

            @Test
            fun `should default to http, which the server uses on a local network`() {
                assertEquals(case, AddressResult.Valid(expected.toHttpUrl()), address)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun hosts(): List<Array<Any>> = listOf(
                    arrayOf("an IP address, between spaces", "  192.168.1.10:8765 ", "http://192.168.1.10:8765/"),
                    arrayOf("a host name", "pc.local:8765", "http://pc.local:8765/"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheAddressIsSecureHttpOrOnIpVersion6(
            private val case: String,
            private val input: String,
            private val expected: String,
        ) {
            private lateinit var address: AddressResult

            @Before
            fun parseTheAddress() {
                address = ServerAddress.parse(input)
            }

            @Test
            fun `should accept it`() {
                assertEquals(case, AddressResult.Valid(expected.toHttpUrl()), address)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun kinds(): List<Array<Any>> = listOf(
                    arrayOf("https, in capitals", "HTTPS://scan.example.org", "https://scan.example.org/"),
                    arrayOf("an IPv6 host", "http://[fd00::1]:8765", "http://[fd00::1]:8765/"),
                )
            }
        }

        class WhenTheInputIsBlank {
            private lateinit var address: AddressResult

            @Before
            fun parseTheAddress() {
                address = ServerAddress.parse("   ")
            }

            @Test
            fun `should refuse it as empty`() {
                assertEquals(AddressResult.Invalid(AddressError.EMPTY), address)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheSchemeIsNeitherPlainNorSecureHttp(private val case: String, private val input: String) {
            private lateinit var address: AddressResult

            @Before
            fun parseTheAddress() {
                address = ServerAddress.parse(input)
            }

            @Test
            fun `should refuse it as an unsupported scheme`() {
                assertEquals(case, AddressResult.Invalid(AddressError.UNSUPPORTED_SCHEME), address)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun schemes(): List<Array<Any>> = listOf(
                    arrayOf("ftp", "ftp://192.168.1.10"),
                    arrayOf("a pairing code", "scanmylib://pair?url=x&token=y"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheAddressIsMalformed(private val case: String, private val input: String) {
            private lateinit var address: AddressResult

            @Before
            fun parseTheAddress() {
                address = ServerAddress.parse(input)
            }

            @Test
            fun `should refuse it as malformed`() {
                assertEquals(case, AddressResult.Invalid(AddressError.MALFORMED), address)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun flaws(): List<Array<Any>> = listOf(
                    arrayOf("no host", "http://"),
                    arrayOf("a port out of range", "192.168.1.10:99999"),
                    arrayOf("a space in the host", "http://bad host:8765"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheAddressIsMoreThanTheServerRoot(private val case: String, private val input: String) {
            private lateinit var address: AddressResult

            @Before
            fun parseTheAddress() {
                address = ServerAddress.parse(input)
            }

            @Test
            fun `should refuse it, since only the root of the server is its address`() {
                assertEquals(case, AddressResult.Invalid(AddressError.NOT_A_ROOT_URL), address)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun extras(): List<Array<Any>> = listOf(
                    arrayOf("a path", "http://192.168.1.10:8765/api"),
                    arrayOf("a query", "http://192.168.1.10:8765/?debug=1"),
                    arrayOf("a fragment", "http://192.168.1.10:8765/#top"),
                    arrayOf("credentials", "http://user:secret@192.168.1.10:8765"),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheIsValidTokenFunction {
        @RunWith(Parameterized::class)
        class WhenTheTokenCanTravelInAHeader(private val case: String, private val token: String) {
            private var isValid by Delegates.notNull<Boolean>()

            @Before
            fun checkTheToken() {
                isValid = isValidToken(token)
            }

            @Test
            fun `should accept it`() {
                assertTrue(case, isValid)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun tokens(): List<Array<Any>> = listOf(
                    arrayOf("a generated token", "q9Xz-Lm_3vT0aBcDeFgHiJkLmNoPqRsTuVwXyZ01234"),
                    arrayOf("a custom token with punctuation", "custom!token~"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheTokenCannotTravelInAHeader(private val case: String, private val token: String) {
            private var isValid by Delegates.notNull<Boolean>()

            @Before
            fun checkTheToken() {
                isValid = isValidToken(token)
            }

            @Test
            fun `should refuse it`() {
                assertFalse(case, isValid)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun flaws(): List<Array<Any>> = listOf(
                    arrayOf("empty", ""),
                    arrayOf("a space", "with space"),
                    arrayOf("a character outside ASCII", "token€"),
                    arrayOf("a line break", "line\nbreak"),
                    arrayOf("513 characters, over the limit of 512", "x".repeat(513)),
                )
            }
        }
    }
}
