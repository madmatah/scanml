package fr.scanmylib.library

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PageNumberingTest {

    private fun hints(numbering: PageNumbering, count: Int) = List(count, numbering::hintFor)

    @Test
    fun `no first page means no hints`() {
        assertEquals(listOf(null, null, null), hints(PageNumbering(firstPage = null, consecutive = true), 3))
    }

    @Test
    fun `consecutive pages are numbered on from the first one`() {
        assertEquals(listOf(13, 14, 15, 16), hints(PageNumbering(firstPage = 13, consecutive = true), 4))
    }

    @Test
    fun `non-consecutive pages only hint the first one`() {
        assertEquals(listOf(45, null, null), hints(PageNumbering(firstPage = 45, consecutive = false), 3))
    }

    @Test
    fun `hints never go past what the server accepts`() {
        // The server refuses page_number_hint > 9999 (HTTP 422): such a page would be refused for good.
        assertEquals(listOf(9998, 9999, null, null), hints(PageNumbering(firstPage = 9998, consecutive = true), 4))
        assertEquals(listOf(9999, null), hints(PageNumbering(firstPage = 9999, consecutive = true), 2))
    }

    @Test
    fun `the last hint of a run`() {
        assertEquals(16, PageNumbering(13, consecutive = true).lastHint(pageCount = 4))
        assertEquals(13, PageNumbering(13, consecutive = true).lastHint(pageCount = 1))
        assertEquals(45, PageNumbering(45, consecutive = false).lastHint(pageCount = 3))
        assertEquals(9999, PageNumbering(9998, consecutive = true).lastHint(pageCount = 4))
        assertNull(PageNumbering(null, consecutive = true).lastHint(pageCount = 3))
    }

    @Test
    fun `reads the first page field`() {
        assertEquals(PageNumbering(null, consecutive = true), PageNumbering.fromInput("  ", consecutive = true))
        assertEquals(PageNumbering(12, consecutive = false), PageNumbering.fromInput(" 12 ", consecutive = false))
        assertEquals(PageNumbering(9999, consecutive = true), PageNumbering.fromInput("9999", consecutive = true))
        assertNull(PageNumbering.fromInput("0", consecutive = true))
        assertNull(PageNumbering.fromInput("10000", consecutive = true))
        assertNull(PageNumbering.fromInput("12a", consecutive = true))
        assertNull(PageNumbering.fromInput("-3", consecutive = true))
    }

    @Test(expected = IllegalArgumentException::class)
    fun `rejects impossible first pages`() {
        PageNumbering(firstPage = 0, consecutive = true)
    }

    @Test
    fun `the next run continues after a consecutive run`() {
        assertEquals(21, PageNumbering(13, consecutive = true).nextFirstPage(pageCount = 8))
        assertNull(PageNumbering(13, consecutive = false).nextFirstPage(pageCount = 8))
        assertNull(PageNumbering(null, consecutive = true).nextFirstPage(pageCount = 8))
        assertNull(PageNumbering(9995, consecutive = true).nextFirstPage(pageCount = 8))
    }
}
