package fr.scanmylib.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

private val LocalCardColor = staticCompositionLocalOf { Color.Unspecified }

val MaterialTheme.cardColor: Color
    @Composable
    @ReadOnlyComposable
    get() = LocalCardColor.current

@Composable
fun ScanMyLibTheme(
    dark: Boolean = isSystemInDarkTheme(),
    contrast: Contrast = phoneContrast(),
    content: @Composable () -> Unit,
) {
    val colorScheme = pickColorScheme(isDark = dark, contrast)
    val cardColor = if (dark) colorScheme.surfaceContainer else colorScheme.surfaceContainerLow
    CompositionLocalProvider(LocalCardColor provides cardColor) {
        MaterialTheme(colorScheme = colorScheme, typography = ScanMyLibTypography, content = content)
    }
}
