package fr.scanmylib.ui.theme

import android.graphics.Color
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.LocalActivity
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * The bars' icons follow the app's theme, which may differ from the phone's. Applied with the
 * frame, before the effects of the screen, such as the camera's light icons, which a later
 * coroutine would override.
 */
@Composable
internal fun ThemedSystemBars(isDark: Boolean) {
    val activity = LocalActivity.current as? ComponentActivity ?: return
    DisposableEffect(activity, isDark) {
        activity.enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT) { isDark },
            navigationBarStyle = SystemBarStyle.auto(LIGHT_SCRIM, DARK_SCRIM) { isDark },
        )
        onDispose {}
    }
}

@Composable
internal fun LightSystemBarIcons() {
    val window = LocalActivity.current?.window ?: return
    val view = LocalView.current
    DisposableEffect(window, view) {
        val bars = WindowCompat.getInsetsController(window, view)
        val wereStatusBarsLight = bars.isAppearanceLightStatusBars
        val wereNavigationBarsLight = bars.isAppearanceLightNavigationBars
        bars.isAppearanceLightStatusBars = false
        bars.isAppearanceLightNavigationBars = false
        onDispose {
            bars.isAppearanceLightStatusBars = wereStatusBarsLight
            bars.isAppearanceLightNavigationBars = wereNavigationBarsLight
        }
    }
}

// The scrims enableEdgeToEdge() puts behind the three-button navigation by default.
private const val LIGHT_SCRIM = 0xE6FFFFFF.toInt()
private const val DARK_SCRIM = 0x801B1B1B.toInt()
