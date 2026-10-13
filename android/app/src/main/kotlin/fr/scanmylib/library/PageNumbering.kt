package fr.scanmylib.library

/**
 * Page-number hints for the pages of one scanner run, sent as `page_number_hint`. The server
 * prefers numbers it detects itself; hints help with pages whose number is not printed.
 *
 * @property firstPage number of the first scanned page, if the user gave one.
 * @property consecutive whether the following pages are numbered on from [firstPage];
 *   otherwise only the first page gets a hint.
 */
data class PageNumbering(val firstPage: Int?, val consecutive: Boolean) {

    init {
        require(firstPage == null || firstPage in 1..MAX_FIRST_PAGE) { "invalid first page: $firstPage" }
    }

    /**
     * Hint for the page at [index] (0-based) in the run. Never above [MAX_FIRST_PAGE]: the server
     * refuses the upload of a page with a larger hint (HTTP 422), so such pages get no hint.
     */
    fun hintFor(index: Int): Int? = when {
        firstPage == null -> null
        index == 0 -> firstPage
        consecutive -> (firstPage + index).takeIf { it <= MAX_FIRST_PAGE }
        else -> null
    }

    /** The highest hint of a run of [pageCount] pages (at least one), or null if it has none. */
    fun lastHint(pageCount: Int): Int? = (pageCount - 1 downTo 0).firstNotNullOfOrNull(::hintFor)

    /**
     * The first page of the next run when scanning on in order: the page after the last one
     * numbered here, or null if this run did not number its pages consecutively.
     */
    fun nextFirstPage(pageCount: Int): Int? =
        if (firstPage != null && consecutive) (firstPage + pageCount).takeIf { it <= MAX_FIRST_PAGE } else null

    companion object {
        /** The server detects page numbers of up to four digits. */
        const val MAX_FIRST_PAGE = 9999

        /**
         * Reads the "first page" field: blank means no hint, otherwise a number from 1 to
         * [MAX_FIRST_PAGE]. Returns null when the input is invalid.
         */
        fun fromInput(firstPageInput: String, consecutive: Boolean): PageNumbering? {
            val text = firstPageInput.trim()
            if (text.isEmpty()) return PageNumbering(firstPage = null, consecutive = consecutive)
            val number = text.toIntOrNull()?.takeIf { it in 1..MAX_FIRST_PAGE } ?: return null
            return PageNumbering(number, consecutive)
        }
    }
}
