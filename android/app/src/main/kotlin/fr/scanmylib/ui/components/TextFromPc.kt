package fr.scanmylib.ui.components

import java.text.BreakIterator

const val MAX_TEXT_FROM_PC_GRAPHEMES = 300

const val MAX_PAGE_LABEL_GRAPHEMES = 16

private const val ELLIPSIS = "…"

// A character outside the Basic Multilingual Plane with a few marks fits in 8 code units, so that reading no more of a
// text keeps the grapheme it must show whole, and a huge text costs no more than a long one.
internal const val CODE_UNITS_READ_PER_GRAPHEME = 8

internal const val MAX_CODE_UNITS_PER_GRAPHEME = 24

internal const val MAX_JOINERS_PER_GRAPHEME = 3

private const val MAX_MARKS_IN_A_ROW = 4

private const val ZERO_WIDTH_NON_JOINER = 0x200C

private const val ZERO_WIDTH_JOINER = 0x200D

private val BLANK_LETTERS = setOf(0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800)

private val IGNORABLE_MARKS = listOf(0x034F..0x034F, 0x17B4..0x17B5, 0x180B..0x180F)

private val GLYPH_VARIATION_SELECTORS = listOf(0xFE00..0xFE0D, 0xE0100..0xE01EF)

/** Nothing else bounds what the PC sends, such as an error message: a long one would fill the screen. */
fun sanitizeTextFromPc(text: String, maxGraphemes: Int = MAX_TEXT_FROM_PC_GRAPHEMES): String {
    require(maxGraphemes > 1) { "no room for a grapheme before the ellipsis" }
    val codeUnitsRead = maxGraphemes * CODE_UNITS_READ_PER_GRAPHEME
    val isCutShort = text.length > codeUnitsRead
    val startRead = if (isCutShort) readStartWithoutItsLastGrapheme(text, codeUnitsRead) else text
    val plain = replaceOversizedGraphemes(keepWhatAReaderSees(startRead))
    return cutToMaxGraphemes(plain, maxGraphemes, isCutShort)
}

private fun readStartWithoutItsLastGrapheme(text: String, codeUnitsRead: Int): String {
    val readEnd = if (text[codeUnitsRead - 1].isHighSurrogate()) codeUnitsRead + 1 else codeUnitsRead
    val textRead = text.substring(0, readEnd)
    val graphemes: BreakIterator = BreakIterator.getCharacterInstance().apply { setText(textRead) }
    graphemes.last()
    val lastStart = graphemes.previous()
    return if (lastStart == BreakIterator.DONE) "" else textRead.substring(0, lastStart)
}

private enum class KeptKind {
    NOTHING,
    SPACE,
    BASE,
    MARK,
    JOINER,
}

private fun keepWhatAReaderSees(text: String): String {
    val keptText = StringBuilder()
    var lastKept = KeptKind.NOTHING
    var marksInARow = 0
    var index = 0
    while (index < text.length) {
        val codePoint = text.codePointAt(index)
        index += Character.charCount(codePoint)
        val generalCategory = Character.getType(codePoint)
        val followsACharacter = lastKept != KeptKind.NOTHING && lastKept != KeptKind.SPACE
        when {
            isUnseen(codePoint, generalCategory) -> Unit

            isLineBreakControlOrSpace(generalCategory) -> {
                if (followsACharacter) {
                    keptText.append(' ')
                    lastKept = KeptKind.SPACE
                }
                marksInARow = 0
            }

            codePoint == ZERO_WIDTH_JOINER || codePoint == ZERO_WIDTH_NON_JOINER -> {
                if (lastKept == KeptKind.BASE || lastKept == KeptKind.MARK) {
                    keptText.appendCodePoint(codePoint)
                    lastKept = KeptKind.JOINER
                }
            }

            isMark(generalCategory) -> {
                if (followsACharacter && marksInARow < MAX_MARKS_IN_A_ROW) {
                    keptText.appendCodePoint(codePoint)
                    lastKept = KeptKind.MARK
                }
                marksInARow += 1
            }

            else -> {
                keptText.appendCodePoint(codePoint)
                marksInARow = 0
                lastKept = KeptKind.BASE
            }
        }
    }
    return keptText.toString().trimEnd()
}

private fun isUnseen(codePoint: Int, generalCategory: Int): Boolean = when (generalCategory) {
    Character.FORMAT.toInt() -> codePoint != ZERO_WIDTH_NON_JOINER && codePoint != ZERO_WIDTH_JOINER

    Character.PRIVATE_USE.toInt(), Character.UNASSIGNED.toInt(), Character.SURROGATE.toInt() -> true

    else -> {
        codePoint in BLANK_LETTERS ||
            IGNORABLE_MARKS.any { codePoint in it } ||
            GLYPH_VARIATION_SELECTORS.any { codePoint in it }
    }
}

private fun isLineBreakControlOrSpace(generalCategory: Int): Boolean = when (generalCategory) {
    Character.CONTROL.toInt(),
    Character.LINE_SEPARATOR.toInt(),
    Character.PARAGRAPH_SEPARATOR.toInt(),
    Character.SPACE_SEPARATOR.toInt(),
    -> true

    else -> false
}

private fun isMark(generalCategory: Int): Boolean = when (generalCategory) {
    Character.NON_SPACING_MARK.toInt(),
    Character.ENCLOSING_MARK.toInt(),
    Character.COMBINING_SPACING_MARK.toInt(),
    -> true

    else -> false
}

private fun replaceOversizedGraphemes(text: String): String {
    if (!isOversized(text, 0, text.length)) return text
    val graphemes: BreakIterator = BreakIterator.getCharacterInstance().apply { setText(text) }
    var shownText: StringBuilder? = null
    var start = graphemes.first()
    var end = graphemes.next()
    while (end != BreakIterator.DONE) {
        val isReplaced = isOversized(text, start, end)
        if (isReplaced && shownText == null) shownText = StringBuilder(text.length).append(text, 0, start)
        when {
            shownText == null -> Unit
            isReplaced -> if (endsWithACharacter(shownText)) shownText.append(' ')
            text[start] == ' ' -> if (endsWithACharacter(shownText)) shownText.append(text, start, end)
            else -> shownText.append(text, start, end)
        }
        start = end
        end = graphemes.next()
    }
    return shownText?.trimEnd()?.toString() ?: text
}

private fun isOversized(text: String, start: Int, end: Int): Boolean =
    end - start > MAX_CODE_UNITS_PER_GRAPHEME || countJoiners(text, start, end) > MAX_JOINERS_PER_GRAPHEME

private fun countJoiners(text: String, start: Int, end: Int): Int {
    var joinerCount = 0
    for (index in start until end) {
        val codeUnit = text[index].code
        if (codeUnit == ZERO_WIDTH_JOINER || codeUnit == ZERO_WIDTH_NON_JOINER) joinerCount += 1
    }
    return joinerCount
}

private fun endsWithACharacter(text: CharSequence): Boolean = text.isNotEmpty() && text.last() != ' '

private fun cutToMaxGraphemes(text: String, maxGraphemes: Int, isCutShort: Boolean): String {
    if (!isCutShort && text.length <= maxGraphemes) return text
    val graphemes: BreakIterator = BreakIterator.getCharacterInstance().apply { setText(text) }
    var graphemeCount = 0
    var keptEnd = text.length
    var end = graphemes.next()
    while (end != BreakIterator.DONE && graphemeCount <= maxGraphemes) {
        graphemeCount += 1
        if (graphemeCount == maxGraphemes - 1) keptEnd = end
        end = graphemes.next()
    }
    if (!isCutShort && graphemeCount <= maxGraphemes) return text
    return text.substring(0, keptEnd).trimEnd() + ELLIPSIS
}
