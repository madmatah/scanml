package fr.scanmylib.model

/** Where the pages of a scanning run come from. All sources end in the same upload queue. */
enum class ScanSource {
    /** Google's document scanner (ML Kit): pages cropped and straightened, as set in the settings. */
    GOOGLE_SCANNER,

    /** The app's camera screen: original photos, taken one after the other. */
    CAMERA,

    /** Photos already taken, chosen with the system photo picker: the "Import" action. */
    PHOTO_PICKER,
    ;

    /** Takes the photos now: one of the cameras the "Scan" action can open. */
    val isCamera: Boolean get() = this != PHOTO_PICKER

    companion object {
        /** The default camera, until the user chooses another: no camera permission needed. */
        val DEFAULT = GOOGLE_SCANNER

        /** The cameras "Scan" can open, in the order they are offered. */
        val CAMERAS = entries.filter { it.isCamera }
    }
}
