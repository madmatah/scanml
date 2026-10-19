package fr.scanmylib.ui.theme

import androidx.activity.ComponentActivity
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.core.view.WindowCompat
import kotlin.properties.Delegates
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class SystemBarsTest {
    @RunWith(Enclosed::class)
    class TheThemedSystemBarsFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = "night")
        class WhenTheAppIsLightOnADarkPhone {
            @get:Rule
            val compose = createAndroidComposeRule<ComponentActivity>()

            private var hasDarkStatusBarIcons by Delegates.notNull<Boolean>()
            private var hasDarkNavigationBarIcons by Delegates.notNull<Boolean>()

            @Before
            fun drawTheBars() {
                compose.setContent { ThemedSystemBars(isDark = false) }
                compose.waitForIdle()
                hasDarkStatusBarIcons = compose.activity.hasDarkStatusBarIcons()
                hasDarkNavigationBarIcons = compose.activity.hasDarkNavigationBarIcons()
            }

            @Test
            fun `should give the status bar dark icons, following the app's theme rather than the phone's`() {
                assertTrue(hasDarkStatusBarIcons)
            }

            @Test
            fun `should give the navigation bar dark icons, following the app's theme rather than the phone's`() {
                assertTrue(hasDarkNavigationBarIcons)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheLightSystemBarIconsFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheCameraOpensInTheLightTheme {
            @get:Rule
            val compose = createAndroidComposeRule<ComponentActivity>()

            private var hasDarkStatusBarIcons by Delegates.notNull<Boolean>()
            private var hasDarkNavigationBarIcons by Delegates.notNull<Boolean>()

            @Before
            fun openTheCameraInTheLightTheme() {
                compose.openTheCamera(isDark = false)
                hasDarkStatusBarIcons = compose.activity.hasDarkStatusBarIcons()
                hasDarkNavigationBarIcons = compose.activity.hasDarkNavigationBarIcons()
            }

            @Test
            fun `should give the status bar light icons over the camera's black screen`() {
                assertFalse(hasDarkStatusBarIcons)
            }

            @Test
            fun `should give the navigation bar light icons over the camera's black screen`() {
                assertFalse(hasDarkNavigationBarIcons)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = "night")
        class WhenTheCameraOpensAndClosesInTheLightThemeOnADarkPhone {
            @get:Rule
            val compose = createAndroidComposeRule<ComponentActivity>()

            private var hasDarkStatusBarIcons by Delegates.notNull<Boolean>()
            private var hasDarkNavigationBarIcons by Delegates.notNull<Boolean>()

            @Before
            fun openAndCloseTheCamera() {
                val showsCamera = compose.openTheCamera(isDark = false)
                compose.closeTheCamera(showsCamera)
                hasDarkStatusBarIcons = compose.activity.hasDarkStatusBarIcons()
                hasDarkNavigationBarIcons = compose.activity.hasDarkNavigationBarIcons()
            }

            @Test
            fun `should give the status bar the light theme's dark icons back`() {
                assertTrue(hasDarkStatusBarIcons)
            }

            @Test
            fun `should give the navigation bar the light theme's dark icons back`() {
                assertTrue(hasDarkNavigationBarIcons)
            }
        }
    }
}

private fun ComposeContentTestRule.openTheCamera(isDark: Boolean): MutableState<Boolean> {
    val showsCamera = mutableStateOf(true)
    setContent {
        ThemedSystemBars(isDark)
        if (showsCamera.value) LightSystemBarIcons()
    }
    waitForIdle()
    return showsCamera
}

private fun ComposeContentTestRule.closeTheCamera(showsCamera: MutableState<Boolean>) {
    showsCamera.value = false
    waitForIdle()
}

private fun ComponentActivity.hasDarkStatusBarIcons(): Boolean =
    WindowCompat.getInsetsController(window, window.decorView).isAppearanceLightStatusBars

private fun ComponentActivity.hasDarkNavigationBarIcons(): Boolean =
    WindowCompat.getInsetsController(window, window.decorView).isAppearanceLightNavigationBars
