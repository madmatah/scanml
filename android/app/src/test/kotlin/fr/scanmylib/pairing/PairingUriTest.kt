package fr.scanmylib.pairing

import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class PairingUriTest {
    @RunWith(Enclosed::class)
    class TheParseMethod {
        class WhenGivenThePairingUriTheServerShows {
            private val code = "scanmylib://pair?url=http%3A%2F%2F192.168.1.10%3A8765&token=q9Xz-Lm_3vT0"
            private lateinit var outcome: PairingOutcome

            @Before
            fun parseTheCode() {
                outcome = readPairingOutcome(PairingUri.parse(code))
            }

            @Test
            fun `should read the address of the server and its token`() {
                assertEquals(PairingOutcome.Paired("http://192.168.1.10:8765/", "q9Xz-Lm_3vT0"), outcome)
            }
        }

        class WhenTheUrlIsNotEncodedAndTheParametersComeInAnyOrderWithUnknownOnes {
            private val code = "scanmylib://pair?v=2&token=abc&url=http://10.0.0.2:8765/"
            private lateinit var outcome: PairingOutcome

            @Before
            fun parseTheCode() {
                outcome = readPairingOutcome(PairingUri.parse(code))
            }

            @Test
            fun `should read the address of the server and its token`() {
                assertEquals(PairingOutcome.Paired("http://10.0.0.2:8765/", "abc"), outcome)
            }
        }

        class WhenTheSchemeAndTheHostAreInCapitalsAndSurroundedBySpaces {
            private val code = "  SCANMYLIB://Pair?url=http%3A%2F%2Fpc.local%3A8765&token=abc\n"
            private lateinit var outcome: PairingOutcome

            @Before
            fun parseTheCode() {
                outcome = readPairingOutcome(PairingUri.parse(code))
            }

            @Test
            fun `should read the code, since its scheme and its host ignore case`() {
                assertEquals(PairingOutcome.Paired("http://pc.local:8765/", "abc"), outcome)
            }
        }

        class WhenTheTokenIsFormEncoded {
            private val code = "scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token=a%2Bb%2Fc%3D"
            private lateinit var outcome: PairingOutcome

            @Before
            fun parseTheCode() {
                outcome = readPairingOutcome(PairingUri.parse(code))
            }

            @Test
            fun `should decode it`() {
                assertEquals(PairingOutcome.Paired("http://pc:1/", "a+b/c="), outcome)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheCodeIsNoPairingCode(private val case: String, private val text: String) {
            private lateinit var pairing: PairingResult

            @Before
            fun parseTheCode() {
                pairing = PairingUri.parse(text)
            }

            @Test
            fun `should refuse it as no pairing code`() {
                assertEquals(case, PairingResult.Invalid(PairingError.NOT_A_PAIRING_CODE), pairing)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun codes(): List<Array<Any>> = listOf(
                    arrayOf("the download address of the app", "http://192.168.1.10:8765/download/scanmylib.apk"),
                    arrayOf("another host than pair", "scanmylib://other?url=http%3A%2F%2Fpc%3A1&token=abc"),
                    arrayOf("no authority", "scanmylib:pair?url=http%3A%2F%2Fpc%3A1&token=abc"),
                    arrayOf("a word", "hello"),
                    arrayOf("nothing", ""),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheQueryIsDamagedOrAmbiguous(private val case: String, private val text: String) {
            private lateinit var pairing: PairingResult

            @Before
            fun parseTheCode() {
                pairing = PairingUri.parse(text)
            }

            @Test
            fun `should refuse it as no pairing code`() {
                assertEquals(case, PairingResult.Invalid(PairingError.NOT_A_PAIRING_CODE), pairing)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun queries(): List<Array<Any>> = listOf(
                    arrayOf("a malformed escape", "scanmylib://pair?url=%zz&token=abc"),
                    arrayOf("two URLs", "scanmylib://pair?url=http%3A%2F%2Fa%3A1&url=http%3A%2F%2Fb%3A1&token=abc"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheServerUrlIsMissingOrInvalid(private val case: String, private val text: String) {
            private lateinit var pairing: PairingResult

            @Before
            fun parseTheCode() {
                pairing = PairingUri.parse(text)
            }

            @Test
            fun `should refuse the URL`() {
                assertEquals(case, PairingResult.Invalid(PairingError.INVALID_URL), pairing)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun urls(): List<Array<Any>> = listOf(
                    arrayOf("missing", "scanmylib://pair?token=abc"),
                    arrayOf("empty", "scanmylib://pair?url=&token=abc"),
                    arrayOf("another scheme", "scanmylib://pair?url=ftp%3A%2F%2Fpc&token=abc"),
                    arrayOf("not the root of the server", "scanmylib://pair?url=http%3A%2F%2Fpc%3A1%2Fapi&token=abc"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheTokenIsMissingOrInvalid(private val case: String, private val text: String) {
            private lateinit var pairing: PairingResult

            @Before
            fun parseTheCode() {
                pairing = PairingUri.parse(text)
            }

            @Test
            fun `should refuse the token`() {
                assertEquals(case, PairingResult.Invalid(PairingError.INVALID_TOKEN), pairing)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun tokens(): List<Array<Any>> = listOf(
                    arrayOf("missing", "scanmylib://pair?url=http%3A%2F%2Fpc%3A1"),
                    arrayOf("empty", "scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token="),
                    arrayOf("with a space", "scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token=a%20b"),
                    arrayOf(
                        "with a character outside ASCII",
                        "scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token=token%E2%82%AC",
                    ),
                )
            }
        }
    }
}

private sealed interface PairingOutcome {
    data class Paired(val serverUrl: String, val token: String) : PairingOutcome

    data class Refused(val error: PairingError) : PairingOutcome
}

private fun readPairingOutcome(pairing: PairingResult): PairingOutcome = when (pairing) {
    is PairingResult.Valid -> PairingOutcome.Paired(pairing.server.baseUrl.toString(), pairing.server.token)
    is PairingResult.Invalid -> PairingOutcome.Refused(pairing.error)
}
