package fr.scanmylib.ui.theme

import android.app.UiModeManager
import android.os.Build
import androidx.annotation.RequiresApi
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext

enum class Contrast {
    STANDARD,
    MEDIUM,
    HIGH,
}

// The phone's level goes from -1 to 1, and its settings give 0 for standard, 0.5 for medium and 1
// for high: https://developer.android.com/reference/android/app/UiModeManager#getContrast()
internal fun pickContrast(level: Float): Contrast = when {
    level < MEDIUM_FROM -> Contrast.STANDARD
    level < HIGH_FROM -> Contrast.MEDIUM
    else -> Contrast.HIGH
}

private const val MEDIUM_FROM = 1f / 3
private const val HIGH_FROM = 2f / 3

/** Followed while it changes: the contrast is no part of the configuration, whose changes recreate the activity. */
@Composable
internal fun phoneContrast(): Contrast =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) contrastSetting() else Contrast.STANDARD

@RequiresApi(Build.VERSION_CODES.UPSIDE_DOWN_CAKE)
@Composable
private fun contrastSetting(): Contrast {
    val context = LocalContext.current
    val uiModeManager: UiModeManager = remember(context) {
        requireNotNull(context.getSystemService(UiModeManager::class.java)) { "every phone has a UiModeManager" }
    }
    var level by remember(uiModeManager) { mutableFloatStateOf(uiModeManager.contrast) }
    DisposableEffect(uiModeManager) {
        val listener = UiModeManager.ContrastChangeListener { level = it }
        uiModeManager.addContrastChangeListener(context.mainExecutor, listener)
        onDispose { uiModeManager.removeContrastChangeListener(listener) }
    }
    return pickContrast(level)
}
