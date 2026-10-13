package fr.scanmylib.model

/** Where the pages of a scanning run come from. All sources end in the same upload queue. */
enum class ScanSource {
    /** Google's document scanner (ML Kit): pages cropped and straightened, as set in the settings. */
    GOOGLE_SCANNER,

    /** The app's camera screen: original photos, taken one after the other. */
    CAMERA,

    /** Photos already taken, chosen with the system photo picker. */
    PHOTO_PICKER,
    ;

    companion object {
        val DEFAULT = GOOGLE_SCANNER
    }
}
