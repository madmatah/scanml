package fr.scanmylib.library

/** Written as the server writes its coverage label, which [parsePageRanges] reads back. */
fun formatPageRanges(ranges: List<List<Int>>): String = ranges.mapNotNull { range ->
    when {
        range.size != 2 -> null
        range[0] == range[1] -> "${range[0]}"
        else -> "${range[0]}–${range[1]}"
    }
}.joinToString(", ")

/**
 * The label comes from the PC: only one written exactly as the server writes it, ranges ascending
 * and apart, is read, so that a label of another form never suggests a wrong page number.
 */
fun parsePageRanges(label: String): List<IntRange>? {
    if (label.isEmpty()) return emptyList()
    val ranges = label.split(RANGE_SEPARATOR).map { text -> parsePageRange(text) ?: return null }
    val isAscendingAndApart = ranges.zipWithNext().all { (previous, next) -> next.first - 1 > previous.last }
    return ranges.takeIf { isAscendingAndApart }
}

private fun parsePageRange(text: String): IntRange? {
    val bounds = text.split(PAGE_SEPARATOR).map { bound -> parsePage(bound) ?: return null }
    return when (bounds.size) {
        1 -> bounds[0]..bounds[0]
        2 -> (bounds[0]..bounds[1]).takeIf { bounds[0] < bounds[1] }
        else -> null
    }
}

private fun parsePage(text: String): Int? = text.takeIf { it.isNotEmpty() && it.all { char -> char in '0'..'9' } }
    ?.toIntOrNull()

private const val RANGE_SEPARATOR = ", "
private const val PAGE_SEPARATOR = "–"
