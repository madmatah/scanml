package fr.scanmylib.ui.text

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Test
import org.w3c.dom.Element

/** The typography of the UI text, in the catalogs (unit tests run from the app module). */
class TypographyTest {

    /** Each string and plural item of [catalog], by name ("name" or "name/quantity"). */
    private fun texts(catalog: String): Map<String, String> {
        val file = File("src/main/res/$catalog/strings.xml")
        val document = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file)
        val texts = mutableMapOf<String, String>()
        val strings = document.getElementsByTagName("string")
        for (i in 0 until strings.length) {
            val string = strings.item(i) as Element
            texts[string.getAttribute("name")] = string.textContent
        }
        val items = document.getElementsByTagName("item")
        for (i in 0 until items.length) {
            val item = items.item(i) as Element
            val plural = item.parentNode as Element
            texts["${plural.getAttribute("name")}/${item.getAttribute("quantity")}"] = item.textContent
        }
        return texts
    }

    @Test
    fun `French text has non-breaking spaces where French typography wants them`() {
        val problems = texts("values-fr").flatMap { (name, text) ->
            buildList {
                // A space before : ; ? ! % and inside « », always non-breaking (U+00A0 or U+202F).
                Regex("""(?<=\S)[:;?!»%]|(?<=[ ])[:;?!»%]""").findAll(text).forEach { match ->
                    val before = text.getOrNull(match.range.first - 1)
                    // Not in an address: "http://", "192.168.1.10:8765".
                    val next = text.getOrNull(match.range.first + 1)
                    val isUrl = match.value == ":" && (text.startsWith("//", match.range.first + 1) || next?.isDigit() == true)
                    val isFormat = match.value == "%" && (before == '%' || next in FORMAT_CHARS)
                    if (!isUrl && !isFormat && before != NBSP && before != NNBSP) {
                        add("$name: no non-breaking space before «${match.value}» in «$text»")
                    }
                }
                Regex("""«(?![  ])""").findAll(text).forEach { add("$name: no non-breaking space after « in «$text»") }
            }
        }
        assertEquals(emptyList<String>(), problems)
    }

    @Test
    fun `apostrophes and ellipses are typographic in both languages`() {
        val problems = listOf("values", "values-fr").flatMap { catalog ->
            texts(catalog).flatMap { (name, text) ->
                buildList {
                    if ('\'' in text) add("$catalog/$name: straight apostrophe in «$text»")
                    if ("..." in text) add("$catalog/$name: three dots instead of … in «$text»")
                }
            }
        }
        assertEquals(emptyList<String>(), problems)
    }

    private companion object {
        const val NBSP = ' '
        const val NNBSP = ' '

        /** What follows % in a format argument: %d, %1\$s, %%. */
        val FORMAT_CHARS = setOf('d', 's', '1', '2', '3', '4', '5', '6', '7', '8', '9')
    }
}
