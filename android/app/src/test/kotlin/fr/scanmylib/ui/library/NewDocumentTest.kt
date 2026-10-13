package fr.scanmylib.ui.library

import org.junit.Assert.assertEquals
import org.junit.Test

class NewDocumentTest {

    @Test
    fun `titles and authors stay within what the server accepts`() {
        // The server refuses more than 300 characters (HTTP 422): the document would never be created.
        assertEquals(300, NewDocument.MAX_TEXT_LENGTH)
        assertEquals("x".repeat(300), NewDocument.fieldText("x".repeat(301)))
        assertEquals("€".repeat(300), NewDocument.fieldText("€".repeat(5000)))
        assertEquals("Example Book", NewDocument.fieldText("Example Book"))
    }
}
