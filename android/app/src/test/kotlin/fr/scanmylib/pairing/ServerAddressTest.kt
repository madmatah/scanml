package fr.scanmylib.pairing

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ServerAddressTest {

    private fun valid(input: String): String = (ServerAddress.parse(input) as AddressResult.Valid).url.toString()

    private fun error(input: String): AddressError = (ServerAddress.parse(input) as AddressResult.Invalid).error

    @Test
    fun `accepts the root URL of the server`() {
        assertEquals("http://192.168.1.10:8765/", valid("http://192.168.1.10:8765"))
        assertEquals("http://192.168.1.10:8765/", valid("http://192.168.1.10:8765/"))
    }

    @Test
    fun `defaults to http when the scheme is missing`() {
        assertEquals("http://192.168.1.10:8765/", valid("  192.168.1.10:8765 "))
        assertEquals("http://pc.local:8765/", valid("pc.local:8765"))
    }

    @Test
    fun `accepts https and IPv6 hosts`() {
        assertEquals("https://scan.example.org/", valid("HTTPS://scan.example.org"))
        assertEquals("http://[fd00::1]:8765/", valid("http://[fd00::1]:8765"))
    }

    @Test
    fun `rejects empty input`() {
        assertEquals(AddressError.EMPTY, error("   "))
    }

    @Test
    fun `rejects schemes other than http and https`() {
        assertEquals(AddressError.UNSUPPORTED_SCHEME, error("ftp://192.168.1.10"))
        assertEquals(AddressError.UNSUPPORTED_SCHEME, error("scanmylib://pair?url=x&token=y"))
    }

    @Test
    fun `rejects malformed addresses`() {
        assertEquals(AddressError.MALFORMED, error("http://"))
        assertEquals(AddressError.MALFORMED, error("192.168.1.10:99999"))
        assertEquals(AddressError.MALFORMED, error("http://bad host:8765"))
    }

    @Test
    fun `rejects anything but the server root`() {
        assertEquals(AddressError.NOT_A_ROOT_URL, error("http://192.168.1.10:8765/api"))
        assertEquals(AddressError.NOT_A_ROOT_URL, error("http://192.168.1.10:8765/?debug=1"))
        assertEquals(AddressError.NOT_A_ROOT_URL, error("http://192.168.1.10:8765/#top"))
        assertEquals(AddressError.NOT_A_ROOT_URL, error("http://user:secret@192.168.1.10:8765"))
    }

    @Test
    fun `tokens are printable ASCII without spaces`() {
        assertTrue(isValidToken("q9Xz-Lm_3vT0aBcDeFgHiJkLmNoPqRsTuVwXyZ01234"))
        assertTrue(isValidToken("custom!token~"))
        assertFalse(isValidToken(""))
        assertFalse(isValidToken("with space"))
        assertFalse(isValidToken("token€"))
        assertFalse(isValidToken("line\nbreak"))
        assertFalse(isValidToken("x".repeat(513)))
    }
}
