package fr.scanmylib.pairing

import fr.scanmylib.model.ServerConfig
import org.junit.Assert.assertEquals
import org.junit.Test

class PairingUriTest {

    private fun valid(text: String): ServerConfig = (PairingUri.parse(text) as PairingResult.Valid).server

    private fun error(text: String): PairingError = (PairingUri.parse(text) as PairingResult.Invalid).error

    @Test
    fun `parses the pairing URI shown by the server`() {
        val server = valid("scanmylib://pair?url=http%3A%2F%2F192.168.1.10%3A8765&token=q9Xz-Lm_3vT0")
        assertEquals("http://192.168.1.10:8765/", server.baseUrl.toString())
        assertEquals("q9Xz-Lm_3vT0", server.token)
    }

    @Test
    fun `accepts unencoded URLs, any parameter order and unknown parameters`() {
        val server = valid("scanmylib://pair?v=2&token=abc&url=http://10.0.0.2:8765/")
        assertEquals("http://10.0.0.2:8765/", server.baseUrl.toString())
        assertEquals("abc", server.token)
    }

    @Test
    fun `scheme and host are case-insensitive, surrounding spaces ignored`() {
        val server = valid("  SCANMYLIB://Pair?url=http%3A%2F%2Fpc.local%3A8765&token=abc\n")
        assertEquals("http://pc.local:8765/", server.baseUrl.toString())
    }

    @Test
    fun `decodes form-encoded tokens`() {
        assertEquals("a+b/c=", valid("scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token=a%2Bb%2Fc%3D").token)
    }

    @Test
    fun `rejects QR codes that are not pairing codes`() {
        assertEquals(PairingError.NOT_A_PAIRING_CODE, error("http://192.168.1.10:8765/download/scanmylib.apk"))
        assertEquals(PairingError.NOT_A_PAIRING_CODE, error("scanmylib://other?url=http%3A%2F%2Fpc%3A1&token=abc"))
        assertEquals(PairingError.NOT_A_PAIRING_CODE, error("scanmylib:pair?url=http%3A%2F%2Fpc%3A1&token=abc"))
        assertEquals(PairingError.NOT_A_PAIRING_CODE, error("hello"))
        assertEquals(PairingError.NOT_A_PAIRING_CODE, error(""))
    }

    @Test
    fun `rejects damaged or ambiguous queries`() {
        assertEquals(PairingError.NOT_A_PAIRING_CODE, error("scanmylib://pair?url=%zz&token=abc"))
        assertEquals(
            PairingError.NOT_A_PAIRING_CODE,
            error("scanmylib://pair?url=http%3A%2F%2Fa%3A1&url=http%3A%2F%2Fb%3A1&token=abc"),
        )
    }

    @Test
    fun `rejects a missing or invalid server URL`() {
        assertEquals(PairingError.INVALID_URL, error("scanmylib://pair?token=abc"))
        assertEquals(PairingError.INVALID_URL, error("scanmylib://pair?url=&token=abc"))
        assertEquals(PairingError.INVALID_URL, error("scanmylib://pair?url=ftp%3A%2F%2Fpc&token=abc"))
        assertEquals(PairingError.INVALID_URL, error("scanmylib://pair?url=http%3A%2F%2Fpc%3A1%2Fapi&token=abc"))
    }

    @Test
    fun `rejects a missing or invalid token`() {
        assertEquals(PairingError.INVALID_TOKEN, error("scanmylib://pair?url=http%3A%2F%2Fpc%3A1"))
        assertEquals(PairingError.INVALID_TOKEN, error("scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token="))
        assertEquals(PairingError.INVALID_TOKEN, error("scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token=a%20b"))
        assertEquals(PairingError.INVALID_TOKEN, error("scanmylib://pair?url=http%3A%2F%2Fpc%3A1&token=token%E2%82%AC"))
    }
}
