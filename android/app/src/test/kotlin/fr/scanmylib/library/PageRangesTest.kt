package fr.scanmylib.library

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class PageRangesTest {
    @RunWith(Enclosed::class)
    class TheFormatPageRangesFunction {
        @RunWith(Parameterized::class)
        class WhenGivenPageRanges(
            private val ranges: String,
            private val pageRanges: List<List<Int>>,
            private val expected: String,
        ) {
            private lateinit var label: String

            @Before
            fun formatTheRanges() {
                label = formatPageRanges(pageRanges)
            }

            @Test
            fun `should write them as the server labels them`() {
                assertEquals(ranges, expected, label)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun ranges(): List<Array<Any>> = listOf(
                    arrayOf("a range is written with an en dash", listOf(listOf(13, 44)), "13–44"),
                    arrayOf("a single page is written alone", listOf(listOf(2, 2), listOf(5, 9)), "2, 5–9"),
                    arrayOf("no range gives an empty label", emptyList<List<Int>>(), ""),
                    arrayOf("what is not a pair of pages is left out", listOf(listOf(1, 2, 3), listOf(7, 7)), "7"),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheParsePageRangesFunction {
        @RunWith(Parameterized::class)
        class WhenTheLabelIsWrittenAsTheServerWritesIt(
            private val label: String,
            private val text: String,
            private val expected: List<IntRange>,
        ) {
            private lateinit var parsed: ParsedLabel

            @Before
            fun parseTheLabel() {
                parsed = ParsedLabel(parsePageRanges(text))
            }

            @Test
            fun `should read its ranges`() {
                assertEquals(label, ParsedLabel(expected), parsed)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun labels(): List<Array<Any>> = listOf(
                    arrayOf("an empty label names no page", "", emptyList<IntRange>()),
                    arrayOf("a single page", "12", listOf(12..12)),
                    arrayOf("ranges apart, in ascending order", "1–12, 45–60", listOf(1..12, 45..60)),
                    arrayOf("a single page after a range", "1–12, 45", listOf(1..12, 45..45)),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheLabelIsWrittenOtherwise(private val label: String, private val text: String) {
            private lateinit var parsed: ParsedLabel

            @Before
            fun parseTheLabel() {
                parsed = ParsedLabel(parsePageRanges(text))
            }

            @Test
            fun `should read no range, so that a label of another form never suggests a wrong number`() {
                assertNull(label, parsed.ranges)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun labels(): List<Array<Any>> = listOf(
                    arrayOf("a hyphen in place of the en dash", "1-12"),
                    arrayOf("a range of one page, which the server writes alone", "9–9"),
                    arrayOf("a descending range", "12–1"),
                    arrayOf("ranges that touch, which the server writes as one", "1–12, 13–20"),
                    arrayOf("ranges that overlap", "1–12, 10–20"),
                    arrayOf("ranges out of order", "45–60, 1–12"),
                    arrayOf("a roman numeral", "xii"),
                    arrayOf("a space before the label", " 12"),
                    arrayOf("a number beyond what an Int holds", "1–99999999999"),
                    arrayOf("ranges out of order after the largest page an Int holds", "2147483647, 5"),
                )
            }
        }

        class WhenWrittenByTheFormatPageRangesFunction {
            private lateinit var parsed: ParsedLabel

            @Before
            fun formatThenParse() {
                parsed = ParsedLabel(parsePageRanges(formatPageRanges(SCANNED_RANGES)))
            }

            @Test
            fun `should read back the ranges it was given`() {
                assertEquals(ParsedLabel(listOf(1..12, 45..45, 88..90)), parsed)
            }

            private companion object {
                val SCANNED_RANGES = listOf(listOf(1, 12), listOf(45, 45), listOf(88, 90))
            }
        }
    }
}

/** The ranges read from a label, or none, held in a non-null value, as `lateinit` asks. */
private data class ParsedLabel(val ranges: List<IntRange>?)
