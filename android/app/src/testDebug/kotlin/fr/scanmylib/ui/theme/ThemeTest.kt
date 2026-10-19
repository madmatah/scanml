package fr.scanmylib.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.test.junit4.v2.createComposeRule
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class ThemeTest {
    @RunWith(Enclosed::class)
    class TheScanMyLibThemeFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheThemeIsLight {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var colors: ColorScheme
            private var cardColor by Delegates.notNull<Color>()

            @Before
            fun drawTheTheme() {
                compose.setContent {
                    ScanMyLibTheme(dark = false, contrast = Contrast.STANDARD) {
                        colors = MaterialTheme.colorScheme
                        cardColor = MaterialTheme.cardColor
                    }
                }
                compose.waitForIdle()
            }

            @Test
            fun `should draw ScanMyLib's own colors until the wallpaper's are asked for`() {
                assertSame(pickColorScheme(isDark = false, Contrast.STANDARD), colors)
            }

            @Test
            fun `should lift cards one surface level from the background`() {
                assertEquals(colors.surfaceContainerLow, cardColor)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheThemeIsDark {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var colors: ColorScheme
            private var cardColor by Delegates.notNull<Color>()

            @Before
            fun drawTheTheme() {
                compose.setContent {
                    ScanMyLibTheme(dark = true, contrast = Contrast.STANDARD) {
                        colors = MaterialTheme.colorScheme
                        cardColor = MaterialTheme.cardColor
                    }
                }
                compose.waitForIdle()
            }

            @Test
            fun `should lift cards two surface levels from the background, since one is too close to see`() {
                assertEquals(colors.surfaceContainer, cardColor)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAThemeInsideTheWallpaperColorsForcesTheDarkColors {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var colors: ColorScheme
            private lateinit var wallpaperDarkColors: ColorScheme

            @Before
            fun drawTheThemeInside() {
                compose.setContent {
                    wallpaperDarkColors = dynamicDarkColorScheme(LocalContext.current)
                    ScanMyLibTheme(dark = false, usesWallpaperColors = true) {
                        ScanMyLibTheme(dark = true) { colors = MaterialTheme.colorScheme }
                    }
                }
                compose.waitForIdle()
            }

            @Test
            fun `should keep the wallpaper's colors, so that the camera matches the app`() {
                assertEquals(wallpaperDarkColors.primary, colors.primary)
            }
        }
    }
}
