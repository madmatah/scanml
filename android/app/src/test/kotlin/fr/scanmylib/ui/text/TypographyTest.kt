package fr.scanmylib.ui.text

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized
import org.w3c.dom.Element

@RunWith(Enclosed::class)
class TypographyTest {
    class TheFrenchCatalog {
        private lateinit var texts: Map<String, String>

        @Before
        fun readTheCatalog() {
            texts = readTexts("values-fr")
        }

        @Test
        fun `should put a non-breaking space before high punctuation and percent signs, and inside guillemets`() {
            assertTrue("no text read", texts.isNotEmpty())
            assertEquals(emptyList<String>(), findMissingNonBreakingSpaces(texts))
        }
    }

    @RunWith(Parameterized::class)
    class TheCatalogs(private val catalog: String) {
        private lateinit var texts: Map<String, String>

        @Before
        fun readTheCatalog() {
            texts = readTexts(catalog)
        }

        @Test
        fun `should write typographic apostrophes`() {
            assertTrue("no text read", texts.isNotEmpty())
            assertEquals(
                emptyList<String>(),
                texts.filterValues { '\'' in it }
                    .map { (name, text) -> "$catalog/$name: straight apostrophe in «$text»" },
            )
        }

        @Test
        fun `should write an ellipsis as one character`() {
            assertTrue("no text read", texts.isNotEmpty())
            assertEquals(
                emptyList<String>(),
                texts.filterValues { "..." in it }
                    .map { (name, text) -> "$catalog/$name: three dots instead of … in «$text»" },
            )
        }

        companion object {
            @JvmStatic
            @Parameterized.Parameters(name = "{0}")
            fun catalogs(): List<Array<Any>> = listOf(arrayOf("values"), arrayOf("values-fr"))
        }
    }
}

private const val NO_BREAK_SPACE = '\u00A0'
private const val NARROW_NO_BREAK_SPACE = '\u202F'

private val CHARACTERS_AFTER_PERCENT_IN_A_FORMAT = setOf('d', 's', '1', '2', '3', '4', '5', '6', '7', '8', '9')

private val HIGH_PUNCTUATION = Regex("""(?<=\S)[:;?!»%]|(?<=[ ])[:;?!»%]""")
private val OPENING_GUILLEMET_WITHOUT_NON_BREAKING_SPACE = Regex("«(?![$NO_BREAK_SPACE$NARROW_NO_BREAK_SPACE])")

private fun readTexts(catalog: String): Map<String, String> {
    // The unit tests run from the app module.
    val file = File("src/main/res/$catalog/strings.xml")
    val document = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file)
    val strings = document.getElementsByTagName("string")
    val items = document.getElementsByTagName("item")
    val stringTexts = (0 until strings.length).map { index -> strings.item(index) as Element }
        .associate { string -> string.getAttribute("name") to string.textContent }
    val pluralTexts = (0 until items.length).map { index -> items.item(index) as Element }
        .associate { item ->
            val plural = item.parentNode as Element
            "${plural.getAttribute("name")}/${item.getAttribute("quantity")}" to item.textContent
        }
    return stringTexts + pluralTexts
}

private fun findMissingNonBreakingSpaces(texts: Map<String, String>): List<String> = texts.flatMap { (name, text) ->
    buildList {
        HIGH_PUNCTUATION.findAll(text).forEach { match ->
            val before = text.getOrNull(match.range.first - 1)
            val next = text.getOrNull(match.range.first + 1)
            val isInAddress =
                match.value == ":" && (text.startsWith("//", match.range.first + 1) || next?.isDigit() == true)
            val isFormat = match.value == "%" && (before == '%' || next in CHARACTERS_AFTER_PERCENT_IN_A_FORMAT)
            if (!isInAddress && !isFormat && before != NO_BREAK_SPACE && before != NARROW_NO_BREAK_SPACE) {
                add("$name: no non-breaking space before «${match.value}» in «$text»")
            }
        }
        OPENING_GUILLEMET_WITHOUT_NON_BREAKING_SPACE.findAll(text).forEach {
            add("$name: no non-breaking space after « in «$text»")
        }
    }
}
