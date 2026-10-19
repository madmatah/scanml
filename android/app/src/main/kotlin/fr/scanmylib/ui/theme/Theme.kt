package fr.scanmylib.ui.theme

import android.os.Build
import androidx.annotation.ChecksSdkIntAtLeast
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

@get:ChecksSdkIntAtLeast(api = Build.VERSION_CODES.S)
val canUseWallpaperColors: Boolean
    get() = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S

private val LocalUsesWallpaperColors = compositionLocalOf { false }

private val LocalCardColor = staticCompositionLocalOf { Color.Unspecified }

val MaterialTheme.cardColor: Color
    @Composable
    @ReadOnlyComposable
    get() = LocalCardColor.current

@Composable
fun ScanMyLibTheme(
    dark: Boolean = isSystemInDarkTheme(),
    usesWallpaperColors: Boolean = LocalUsesWallpaperColors.current,
    contrast: Contrast = phoneContrast(),
    content: @Composable () -> Unit,
) {
    val colorScheme = if (usesWallpaperColors && canUseWallpaperColors) {
        val context = LocalContext.current
        // The phone's own schemes follow its contrast setting already.
        if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
    } else {
        pickColorScheme(isDark = dark, contrast)
    }
    val cardColor = if (dark) colorScheme.surfaceContainer else colorScheme.surfaceContainerLow
    CompositionLocalProvider(
        LocalUsesWallpaperColors provides usesWallpaperColors,
        LocalCardColor provides cardColor,
    ) {
        MaterialTheme(colorScheme = colorScheme, typography = ScanMyLibTypography, content = content)
    }
}
