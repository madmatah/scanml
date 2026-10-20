package fr.scanmylib.library

sealed interface PageLabel {
    data object Unnumbered : PageLabel

    data class OnePage(val page: String) : PageLabel

    data class Spread(val firstPage: String, val lastPage: String) : PageLabel
}

fun parsePageLabel(label: String): PageLabel {
    if (label.isBlank()) return PageLabel.Unnumbered
    val sides = label.split(SPREAD_SEPARATOR)
    return if (sides.size == 2 && sides.none(String::isBlank)) {
        PageLabel.Spread(sides[0], sides[1])
    } else {
        PageLabel.OnePage(label)
    }
}

private const val SPREAD_SEPARATOR = "–"
