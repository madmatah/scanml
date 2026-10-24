package fr.scanmylib.library

import fr.scanmylib.library.PageNumbering.Cleared
import fr.scanmylib.library.PageNumbering.Given
import fr.scanmylib.library.PageNumbering.NotGiven
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class PageNumberingTest {
    @RunWith(Enclosed::class)
    class TheGivenConstructor {
        class WhenTheNumberIsZero {
            private lateinit var numberPageZero: () -> PageNumbering

            @Before
            fun keepTheNumbering() {
                numberPageZero = { Given(0, nextPagesFollowOn = true) }
            }

            @Test
            fun `should refuse it, since no page is numbered 0`() {
                val error = assertThrows(IllegalArgumentException::class.java) { numberPageZero() }
                assertEquals("invalid page number: 0", error.message)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheHintPagesFunction {
        class WhenTheFirstPageIsGivenWithTheNextPages {
            private lateinit var numbers: List<Int?>

            @Before
            fun hintFourPages() {
                val first = Given(13, nextPagesFollowOn = true)
                val pages = listOf(first) + List(3) { NotGiven }
                numbers = hintPages(pages).map { it.number }
            }

            @Test
            fun `should number the next pages on from it`() {
                assertEquals(listOf(13, 14, 15, 16), numbers)
            }
        }

        @RunWith(Parameterized::class)
        class WhenARunIsNumberedPageByPage(
            private val run: String,
            private val numberings: List<PageNumbering>,
            private val expected: List<PageHint>,
        ) {
            private lateinit var hints: List<PageHint>

            @Before
            fun hintThePages() {
                hints = hintPages(numberings)
            }

            @Test
            fun `should hint each page as the numbers given and following on say`() {
                assertEquals(run, expected, hints)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun runs(): List<Array<Any>> = listOf(
                    arrayOf(
                        "with no number given, every page is Auto, for the PC to read",
                        List(3) { NotGiven },
                        List(3) { PageHint.Auto },
                    ),
                    arrayOf(
                        "32 on page 1 with the next pages gives pages 2 to 4 the numbers 33 to 35",
                        listOf(Given(32, nextPagesFollowOn = true), NotGiven, NotGiven, NotGiven),
                        listOf(
                            PageHint.Given(32),
                            PageHint.FollowingOn(33),
                            PageHint.FollowingOn(34),
                            PageHint.FollowingOn(35),
                        ),
                    ),
                    arrayOf(
                        "then 40 on page 4 changes only page 4",
                        listOf(
                            Given(32, nextPagesFollowOn = true),
                            NotGiven,
                            NotGiven,
                            Given(40, nextPagesFollowOn = true),
                        ),
                        listOf(
                            PageHint.Given(32),
                            PageHint.FollowingOn(33),
                            PageHint.FollowingOn(34),
                            PageHint.Given(40),
                        ),
                    ),
                    arrayOf(
                        "a number given alone leaves the next pages Auto",
                        listOf(Given(45, nextPagesFollowOn = false), NotGiven, NotGiven),
                        listOf(PageHint.Given(45), PageHint.Auto, PageHint.Auto),
                    ),
                    arrayOf(
                        "a cleared page stops the number running on",
                        listOf(Given(32, nextPagesFollowOn = true), NotGiven, Cleared, NotGiven),
                        listOf(PageHint.Given(32), PageHint.FollowingOn(33), PageHint.Auto, PageHint.Auto),
                    ),
                    arrayOf(
                        "a page given further on takes over",
                        listOf(
                            Given(32, nextPagesFollowOn = true),
                            NotGiven,
                            Given(40, nextPagesFollowOn = true),
                            NotGiven,
                        ),
                        listOf(
                            PageHint.Given(32),
                            PageHint.FollowingOn(33),
                            PageHint.Given(40),
                            PageHint.FollowingOn(41),
                        ),
                    ),
                    arrayOf(
                        "a number running on stops at 9999, past which the server refuses for good with HTTP 422",
                        listOf(Given(9998, nextPagesFollowOn = true), NotGiven, NotGiven, NotGiven),
                        listOf(PageHint.Given(9998), PageHint.FollowingOn(9999), PageHint.Auto, PageHint.Auto),
                    ),
                    arrayOf(
                        "the pages before the first number given are Auto",
                        listOf(NotGiven, Given(12, nextPagesFollowOn = true), NotGiven),
                        listOf(PageHint.Auto, PageHint.Given(12), PageHint.FollowingOn(13)),
                    ),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheChooseNumberingFunction {
        @RunWith(Parameterized::class)
        class WhenTheUserValidatesANumber(
            private val choice: String,
            private val numberings: List<PageNumbering>,
            private val index: Int,
            private val typed: NumberTyped,
            private val nextPagesFollowOn: Boolean,
            private val expected: PageNumbering,
        ) {
            private lateinit var numbering: PageNumbering

            @Before
            fun chooseTheNumbering() {
                numbering = chooseNumbering(numberings, index, typed.number, nextPagesFollowOn)
            }

            @Test
            fun `should give the page the numbering that choice means`() {
                assertEquals(choice, expected, numbering)
            }

            companion object {
                private val UNNUMBERED_RUN = List(4) { NotGiven }
                private val RUN_FROM_32 = listOf(Given(32, nextPagesFollowOn = true), NotGiven, NotGiven, NotGiven)

                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun choices(): List<Array<Any>> = listOf(
                    arrayOf(
                        "a number on a page no number reaches, with the next pages",
                        UNNUMBERED_RUN,
                        0,
                        NumberTyped(32),
                        true,
                        Given(32, nextPagesFollowOn = true),
                    ),
                    arrayOf(
                        "a number on a page no number reaches, alone",
                        UNNUMBERED_RUN,
                        0,
                        NumberTyped(32),
                        false,
                        Given(32, nextPagesFollowOn = false),
                    ),
                    arrayOf(
                        "no number where none runs on is no number given",
                        UNNUMBERED_RUN,
                        2,
                        NumberTyped(null),
                        true,
                        NotGiven,
                    ),
                    arrayOf(
                        "clearing the first page of a run leaves it no number given, so that it goes back to Auto",
                        RUN_FROM_32,
                        0,
                        NumberTyped(null),
                        true,
                        NotGiven,
                    ),
                    arrayOf(
                        "no number where one runs on clears the page, so that it goes back to Auto",
                        RUN_FROM_32,
                        2,
                        NumberTyped(null),
                        true,
                        Cleared,
                    ),
                    arrayOf(
                        "a page that follows on, validated unchanged, still follows on",
                        RUN_FROM_32,
                        1,
                        NumberTyped(33),
                        true,
                        NotGiven,
                    ),
                    arrayOf(
                        "the number running into a page, with the next pages left alone, is given",
                        RUN_FROM_32,
                        1,
                        NumberTyped(33),
                        false,
                        Given(33, nextPagesFollowOn = false),
                    ),
                    arrayOf(
                        "a given page that gets the number running into it follows on again",
                        listOf(Given(32, nextPagesFollowOn = true), Given(40, nextPagesFollowOn = true), NotGiven),
                        1,
                        NumberTyped(33),
                        true,
                        NotGiven,
                    ),
                    arrayOf(
                        "a cleared page that gets the number running into it follows on again",
                        listOf(Given(32, nextPagesFollowOn = true), Cleared, NotGiven),
                        1,
                        NumberTyped(33),
                        true,
                        NotGiven,
                    ),
                    arrayOf(
                        "another number where one runs on is given",
                        RUN_FROM_32,
                        1,
                        NumberTyped(40),
                        true,
                        Given(40, nextPagesFollowOn = true),
                    ),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheRenumberPageFunction {
        class WhenTheSecondOfFourPagesIsGiven40 {
            private lateinit var numberings: List<PageNumbering>

            @Before
            fun renumberIt() {
                val run = listOf(FROM_32, NotGiven, NotGiven, NotGiven)
                numberings = renumberPage(run, SECOND_PAGE, GIVEN_NUMBER, nextPagesFollowOn = true)
            }

            @Test
            fun `should change that page's numbering only, since the next pages follow from it`() {
                assertEquals(listOf(FROM_32, FROM_40, NotGiven, NotGiven), numberings)
            }

            companion object {
                private val FROM_32 = Given(32, nextPagesFollowOn = true)
                private const val GIVEN_NUMBER = 40
                private val FROM_40 = Given(GIVEN_NUMBER, nextPagesFollowOn = true)
                private const val SECOND_PAGE = 1
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheFindNextPagesFunction {
        @RunWith(Parameterized::class)
        class WhenAPageIsNumbered(
            private val run: String,
            private val numberings: List<PageNumbering>,
            private val index: Int,
            private val expected: List<Int>,
        ) {
            private lateinit var nextPages: List<Int>

            @Before
            fun findTheNextPages() {
                nextPages = findNextPages(numberings, index).toList()
            }

            @Test
            fun `should give the pages whose number follows from it`() {
                assertEquals(run, expected, nextPages)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun runs(): List<Array<Any>> = listOf(
                    arrayOf(
                        "down to the end of the run, so that pages added later follow on too",
                        listOf(Given(32, nextPagesFollowOn = true), NotGiven, NotGiven, NotGiven),
                        0,
                        listOf(1, 2, 3),
                    ),
                    arrayOf(
                        "down to the next page given a number",
                        listOf(NotGiven, NotGiven, Given(40, nextPagesFollowOn = true), NotGiven),
                        0,
                        listOf(1),
                    ),
                    arrayOf(
                        "down to the next page cleared",
                        listOf(NotGiven, NotGiven, Cleared),
                        0,
                        listOf(1),
                    ),
                    arrayOf("none after the last page", listOf(NotGiven, NotGiven), 1, emptyList<Int>()),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheReadPageNumberFunction {
        @RunWith(Parameterized::class)
        class WhenANumberIsTyped(
            private val field: String,
            private val text: String,
            private val expected: PageNumberInput,
        ) {
            private lateinit var input: PageNumberInput

            @Before
            fun readTheField() {
                input = readPageNumber(text)
            }

            @Test
            fun `should read what the field asks for`() {
                assertEquals(field, expected, input)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun fields(): List<Array<Any>> = listOf(
                    arrayOf("an empty field asks for no number", "", PageNumberInput.Empty),
                    arrayOf("a blank field asks for no number", "  ", PageNumberInput.Empty),
                    arrayOf("a number is read", "32", PageNumberInput.Valid(32)),
                    arrayOf("a number is read without its spaces", " 12 ", PageNumberInput.Valid(12)),
                    arrayOf("9999, the last page the server accepts, is read", "9999", PageNumberInput.Valid(9999)),
                    arrayOf("0 is refused, since no page is numbered 0", "0", PageNumberInput.Invalid),
                    arrayOf("10000 is refused, past the last page the server takes", "10000", PageNumberInput.Invalid),
                    arrayOf("a number followed by a letter is refused", "3a", PageNumberInput.Invalid),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSuggestPageNumberFunction {
        @RunWith(Parameterized::class)
        class WhenThePageHasNoNumber(
            private val situation: String,
            private val hints: List<PageHint>,
            private val index: Int,
            private val scannedPages: List<IntRange>,
            private val expected: SuggestedNumber,
        ) {
            private lateinit var suggestion: SuggestedNumber

            @Before
            fun suggestANumber() {
                suggestion = SuggestedNumber(suggestPageNumber(index, hints, scannedPages))
            }

            @Test
            fun `should suggest the number the page most likely has`() {
                assertEquals(situation, expected, suggestion)
            }

            companion object {
                private val PAGES_12_TO_31_AND_88_TO_90 = listOf(12..31, 88..90)
                private val PAGES_1_TO_12 = listOf(1..12)

                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun situations(): List<Array<Any>> = listOf(
                    arrayOf(
                        "after a page given a number, the next number, before what the PC holds",
                        listOf(PageHint.Given(40), PageHint.Auto),
                        1,
                        PAGES_12_TO_31_AND_88_TO_90,
                        SuggestedNumber(41),
                    ),
                    arrayOf(
                        "after a page that follows on, the next number",
                        listOf(PageHint.Given(40), PageHint.FollowingOn(41), PageHint.Auto),
                        2,
                        PAGES_12_TO_31_AND_88_TO_90,
                        SuggestedNumber(42),
                    ),
                    arrayOf(
                        "after a page without a number, the first page missing between the PC's ranges",
                        listOf(PageHint.Auto, PageHint.Auto),
                        1,
                        PAGES_12_TO_31_AND_88_TO_90,
                        SuggestedNumber(32),
                    ),
                    arrayOf(
                        "on the first page of the run, the first page missing between the PC's ranges",
                        listOf(PageHint.Auto),
                        0,
                        PAGES_12_TO_31_AND_88_TO_90,
                        SuggestedNumber(32),
                    ),
                    arrayOf(
                        "with no gap between the PC's ranges, the page after its highest",
                        listOf(PageHint.Auto),
                        0,
                        PAGES_1_TO_12,
                        SuggestedNumber(13),
                    ),
                    arrayOf(
                        "with no page on the PC, none",
                        listOf(PageHint.Auto),
                        0,
                        emptyList<IntRange>(),
                        SuggestedNumber(null),
                    ),
                    arrayOf(
                        "after page 9999, the last the server takes, what the PC holds",
                        listOf(PageHint.Given(9999), PageHint.Auto),
                        1,
                        PAGES_1_TO_12,
                        SuggestedNumber(13),
                    ),
                    arrayOf(
                        "after the PC's page 9999, none",
                        listOf(PageHint.Auto),
                        0,
                        listOf(1..9999),
                        SuggestedNumber(null),
                    ),
                )
            }
        }
    }
}

/** A number typed, or none, held in a non-null value so that a row can carry it. */
data class NumberTyped(val number: Int?)

/** A number suggested, or none, held in a non-null value so that a row can carry it. */
data class SuggestedNumber(val number: Int?)
