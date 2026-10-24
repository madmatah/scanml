package fr.scanmylib.library

/** The server reads page numbers of up to four digits, and refuses the upload of a larger hint for good (HTTP 422). */
const val MAX_PAGE_NUMBER = 9999

/**
 * What the user chose for the number of one page to send. Only that choice is stored, in the
 * page's file name: the numbers that follow on from it are derived ([hintPages]), so that one
 * choice changes one file.
 */
sealed interface PageNumbering {
    data object NotGiven : PageNumbering

    data class Given(val number: Int, val nextPagesFollowOn: Boolean) : PageNumbering {
        init {
            require(number in 1..MAX_PAGE_NUMBER) { "invalid page number: $number" }
        }
    }

    data object Cleared : PageNumbering
}

sealed interface PageHint {
    val number: Int?

    data object Auto : PageHint {
        override val number: Int? get() = null
    }

    data class Given(override val number: Int) : PageHint

    data class FollowingOn(override val number: Int) : PageHint
}

sealed interface PageNumberInput {
    data object Empty : PageNumberInput

    data class Valid(val number: Int) : PageNumberInput

    data object Invalid : PageNumberInput
}

fun hintPages(numberings: List<PageNumbering>): List<PageHint> {
    var runningNumber: Int? = null
    return numberings.map { numbering ->
        when (numbering) {
            is PageNumbering.Given -> {
                runningNumber = numbering.number.takeIf { numbering.nextPagesFollowOn }
                PageHint.Given(numbering.number)
            }

            PageNumbering.Cleared -> {
                runningNumber = null
                PageHint.Auto
            }

            PageNumbering.NotGiven -> {
                val number = runningNumber?.plus(1)?.takeIf { it <= MAX_PAGE_NUMBER }
                runningNumber = number
                if (number == null) PageHint.Auto else PageHint.FollowingOn(number)
            }
        }
    }
}

/** A page that would take [number] anyway follows on, so that validating it unchanged renames nothing. */
fun chooseNumbering(
    numberings: List<PageNumbering>,
    index: Int,
    number: Int?,
    nextPagesFollowOn: Boolean,
): PageNumbering {
    val runningNumber = findRunningNumber(numberings, index)
    return when {
        number == null -> if (runningNumber == null) PageNumbering.NotGiven else PageNumbering.Cleared
        number == runningNumber && nextPagesFollowOn -> PageNumbering.NotGiven
        else -> PageNumbering.Given(number, nextPagesFollowOn)
    }
}

fun findNextPages(numberings: List<PageNumbering>, index: Int): IntRange {
    val end = (index + 1 until numberings.size).firstOrNull { numberings[it] != PageNumbering.NotGiven }
    return index + 1 until (end ?: numberings.size)
}

fun readPageNumber(text: String): PageNumberInput {
    val trimmedText = text.trim()
    if (trimmedText.isEmpty()) return PageNumberInput.Empty
    val number = trimmedText.toIntOrNull()?.takeIf { it in 1..MAX_PAGE_NUMBER } ?: return PageNumberInput.Invalid
    return PageNumberInput.Valid(number)
}

private fun findRunningNumber(numberings: List<PageNumbering>, index: Int): Int? =
    hintPages(numberings.take(index) + PageNumbering.NotGiven)[index].number
