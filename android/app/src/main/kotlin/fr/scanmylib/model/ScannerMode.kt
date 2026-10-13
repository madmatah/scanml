package fr.scanmylib.model

/**
 * How much Google's document scanner retouches the pages. Whatever the mode, it never returns the
 * original photo: it always crops and straightens the page, and saves it as a new JPEG.
 */
enum class ScannerMode {
    /** Crop and straighten only. */
    CROP_ONLY,

    /** Also offers filters (grayscale, automatic enhancement...), which change colors and contrast. */
    FILTERS,

    /** Filters, plus the automatic removal of fingers and stains, which can erase page details too. */
    FULL,
    ;

    companion object {
        /** The least destructive mode: the user asked for photos that keep their information. */
        val DEFAULT = CROP_ONLY
    }
}
