package fr.scanmylib.ui.library

import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class NewDocumentTest {
    class TheMaxTextLengthConstant {
        @Test
        fun `should be the 300 characters the server accepts, since it refuses to create a document with more`() {
            assertEquals(300, NewDocument.MAX_TEXT_LENGTH)
        }
    }

    @RunWith(Enclosed::class)
    class TheFieldTextFunction {
        @RunWith(Parameterized::class)
        class WhenTheTextIsTooLong(private val case: String, private val input: String, private val expected: String) {
            private lateinit var fieldText: String

            @Before
            fun typeTheText() {
                fieldText = NewDocument.fieldText(input)
            }

            @Test
            fun `should keep its first 300 characters, so that the server creates the document`() {
                assertEquals(case, expected, fieldText)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun texts(): List<Array<Any>> = listOf(
                    arrayOf("301 letters", "x".repeat(301), "x".repeat(300)),
                    arrayOf("5000 euro signs", "€".repeat(5000), "€".repeat(300)),
                )
            }
        }

        class WhenTheTextFits {
            private val title = "Example Book"
            private lateinit var fieldText: String

            @Before
            fun typeTheText() {
                fieldText = NewDocument.fieldText(title)
            }

            @Test
            fun `should keep it whole`() {
                assertEquals(title, fieldText)
            }
        }
    }
}
