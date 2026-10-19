package fr.scanmylib.model

enum class ThemeMode {
    SAME_AS_PHONE,
    LIGHT,
    DARK,
    ;

    fun isDark(phoneIsDark: Boolean): Boolean = when (this) {
        SAME_AS_PHONE -> phoneIsDark
        LIGHT -> false
        DARK -> true
    }

    companion object {
        val DEFAULT = SAME_AS_PHONE
    }
}
