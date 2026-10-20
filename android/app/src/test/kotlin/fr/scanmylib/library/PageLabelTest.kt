package fr.scanmylib.library

import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class PageLabelTest {
    @RunWith(Enclosed::class)
    class TheParsePageLabelFunction {
        @RunWith(Parameterized::class)
        class WhenGivenALabel(private val name: String, private val label: String, private val expected: PageLabel) {
            private lateinit var parsed: PageLabel

            @Before
            fun parseTheLabel() {
                parsed = parsePageLabel(label)
            }

            @Test
            fun `should name the pages the label numbers`() {
                assertEquals(name, expected, parsed)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun labels(): List<Array<Any>> = listOf(
                    arrayOf("a spread names its two pages", "42–43", PageLabel.Spread("42", "43")),
                    arrayOf("a roman number names one page", "xii", PageLabel.OnePage("xii")),
                    arrayOf("a spread with a side missing names one page, as written", "42–", PageLabel.OnePage("42–")),
                    arrayOf("a blank label names no page", " ", PageLabel.Unnumbered),
                )
            }
        }
    }
}
