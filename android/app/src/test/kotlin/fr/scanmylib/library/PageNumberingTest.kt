package fr.scanmylib.library

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class PageNumberingTest {
    @RunWith(Enclosed::class)
    class TheConstructor {
        class WhenTheFirstPageIsZero {
            private lateinit var numberFromZero: () -> PageNumbering

            @Before
            fun keepTheNumbering() {
                numberFromZero = { PageNumbering(firstPage = 0, consecutive = true) }
            }

            @Test
            fun `should refuse it, since no page is numbered 0`() {
                val error = assertThrows(IllegalArgumentException::class.java) { numberFromZero() }
                assertEquals("invalid first page: 0", error.message)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheHintForMethod {
        class WhenNoFirstPageIsGiven {
            private lateinit var hints: List<Int?>

            @Before
            fun hintThreePages() {
                hints = List(3, PageNumbering(firstPage = null, consecutive = true)::hintFor)
            }

            @Test
            fun `should hint no page`() {
                assertEquals(listOf(null, null, null), hints)
            }
        }

        class WhenThePagesAreConsecutive {
            private lateinit var hints: List<Int?>

            @Before
            fun hintFourPages() {
                hints = List(4, PageNumbering(firstPage = 13, consecutive = true)::hintFor)
            }

            @Test
            fun `should number the pages on from the first one`() {
                assertEquals(listOf(13, 14, 15, 16), hints)
            }
        }

        class WhenThePagesAreNotConsecutive {
            private lateinit var hints: List<Int?>

            @Before
            fun hintThreePages() {
                hints = List(3, PageNumbering(firstPage = 45, consecutive = false)::hintFor)
            }

            @Test
            fun `should hint only the first page`() {
                assertEquals(listOf(45, null, null), hints)
            }
        }

        class WhenTheConsecutivePagesGoPastTheLastPageTheServerAccepts {
            private lateinit var hints: List<Int?>

            @Before
            fun hintFourPages() {
                hints = List(4, PageNumbering(firstPage = 9998, consecutive = true)::hintFor)
            }

            @Test
            fun `should hint no page past 9999, which the server refuses for good with HTTP 422`() {
                assertEquals(listOf(9998, 9999, null, null), hints)
            }
        }

        class WhenTheFirstPageIsTheLastPageTheServerAccepts {
            private lateinit var hints: List<Int?>

            @Before
            fun hintTwoPages() {
                hints = List(2, PageNumbering(firstPage = 9999, consecutive = true)::hintFor)
            }

            @Test
            fun `should hint only the first page, which the server accepts`() {
                assertEquals(listOf(9999, null), hints)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheLastHintMethod {
        @RunWith(Parameterized::class)
        class WhenARunHasAHint(
            private val run: String,
            private val numbering: PageNumbering,
            private val pageCount: Int,
            private val expected: Int,
        ) {
            private lateinit var lastHint: PageNumberHint

            @Before
            fun readTheLastHint() {
                lastHint = PageNumberHint(numbering.lastHint(pageCount))
            }

            @Test
            fun `should give the highest hint of the run`() {
                assertEquals(run, expected, lastHint.number)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun runs(): List<Array<Any>> = listOf(
                    arrayOf("4 consecutive pages from 13 end at 16", PageNumbering(13, consecutive = true), 4, 16),
                    arrayOf("a single page from 13 ends at 13", PageNumbering(13, consecutive = true), 1, 13),
                    arrayOf(
                        "pages that are not consecutive end at the first",
                        PageNumbering(45, consecutive = false),
                        3,
                        45,
                    ),
                    arrayOf(
                        "consecutive pages end at 9999, the last page the server accepts",
                        PageNumbering(9998, consecutive = true),
                        4,
                        9999,
                    ),
                )
            }
        }

        class WhenNoFirstPageIsGiven {
            private lateinit var lastHint: PageNumberHint

            @Before
            fun readTheLastHint() {
                lastHint = PageNumberHint(PageNumbering(null, consecutive = true).lastHint(pageCount = 3))
            }

            @Test
            fun `should give no hint`() {
                assertNull(lastHint.number)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheNextFirstPageMethod {
        class WhenTheRunIsConsecutive {
            private lateinit var nextFirstPage: PageNumberHint

            @Before
            fun continueAfterEightPages() {
                nextFirstPage = PageNumberHint(PageNumbering(13, consecutive = true).nextFirstPage(pageCount = 8))
            }

            @Test
            fun `should continue after the last page of the run`() {
                assertEquals(21, nextFirstPage.number)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheNextRunCannotBeNumberedOn(private val run: String, private val numbering: PageNumbering) {
            private lateinit var nextFirstPage: PageNumberHint

            @Before
            fun continueAfterEightPages() {
                nextFirstPage = PageNumberHint(numbering.nextFirstPage(pageCount = 8))
            }

            @Test
            fun `should give no first page`() {
                assertNull(run, nextFirstPage.number)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun runs(): List<Array<Any>> = listOf(
                    arrayOf("pages that are not consecutive", PageNumbering(13, consecutive = false)),
                    arrayOf("a run without a first page", PageNumbering(null, consecutive = true)),
                    arrayOf(
                        "a run that ends past 9999, the last page the server accepts",
                        PageNumbering(9995, consecutive = true),
                    ),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheFromInputMethod {
        @RunWith(Parameterized::class)
        class WhenTheFirstPageFieldIsValid(
            private val field: String,
            private val firstPageInput: String,
            private val consecutive: Boolean,
            private val expected: PageNumbering,
        ) {
            private lateinit var reading: FirstPageReading

            @Before
            fun readTheField() {
                reading = FirstPageReading(PageNumbering.fromInput(firstPageInput, consecutive))
            }

            @Test
            fun `should give the numbering it asks for`() {
                assertEquals(field, expected, reading.numbering)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun fields(): List<Array<Any>> = listOf(
                    arrayOf("a blank field asks for no hint", "  ", true, PageNumbering(null, consecutive = true)),
                    arrayOf(
                        "a number is read without its spaces",
                        " 12 ",
                        false,
                        PageNumbering(12, consecutive = false),
                    ),
                    arrayOf(
                        "9999, the last page the server accepts, is read",
                        "9999",
                        true,
                        PageNumbering(9999, consecutive = true),
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheFirstPageFieldIsInvalid(private val field: String, private val firstPageInput: String) {
            private lateinit var reading: FirstPageReading

            @Before
            fun readTheField() {
                reading = FirstPageReading(PageNumbering.fromInput(firstPageInput, consecutive = true))
            }

            @Test
            fun `should refuse it`() {
                assertNull(field, reading.numbering)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun fields(): List<Array<Any>> = listOf(
                    arrayOf("0, since no page is numbered 0", "0"),
                    arrayOf("10000, past the last page the server accepts", "10000"),
                    arrayOf("a number followed by letters", "12a"),
                    arrayOf("a negative number", "-3"),
                )
            }
        }
    }
}

/** A hint that may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class PageNumberHint(val number: Int?)

/** What the first page field gives, null when it is invalid, held as [PageNumberHint] is. */
private data class FirstPageReading(val numbering: PageNumbering?)
