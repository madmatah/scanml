package fr.scanmylib.ui.settings

import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelected
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.github.takahirom.roborazzi.ExperimentalRoborazziApi
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureRoboImage
import com.github.takahirom.roborazzi.captureScreenRoboImage
import fr.scanmylib.library.KeptCopies
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.model.ThemeMode
import fr.scanmylib.settings.AppSettings
import fr.scanmylib.ui.theme.ScanMyLibTheme
import fr.scanmylib.update.UpdateState
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(Enclosed::class)
class SettingsScreenTest {
    @RunWith(Enclosed::class)
    class TheSettingsContentFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenScrolledToTheAppearance(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheAppearance() {
                compose.setContent { ScanMyLibTheme(dark = dark) { SettingsContentOf(SETTINGS) } }
                compose.onNodeWithText(ABOUT).performScrollTo()
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/settings-appearance-$theme.png")
            }

            @Test
            fun `should show the theme the app follows`() {
                compose.onNodeWithText(SAME_AS_PHONE).assertIsDisplayed()
            }

            @Test
            fun `should offer the wallpaper's colors, which Android 12 and later give`() {
                compose.onNodeWithText(WALLPAPER_COLORS).assertIsDisplayed()
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenChoosingTheTheme(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalRoborazziApi::class)
            @Before
            fun openTheChoice() {
                compose.setContent { ScanMyLibTheme(dark = dark) { SettingsContentOf(SETTINGS) } }
                compose.onNodeWithText(THEME).performScrollTo().performClick()
                compose.waitForIdle()
                // The whole screen: the dialog has a window of its own.
                captureScreenRoboImage("build/outputs/roborazzi/settings-theme-choice-$theme.png")
            }

            @Test
            fun `should offer a light and a dark theme`() {
                compose.onNodeWithText(LIGHT).assertIsDisplayed()
                compose.onNodeWithText(DARK).assertIsDisplayed()
            }

            @Test
            fun `should mark the current choice`() {
                compose.onNode(hasText(SAME_AS_PHONE) and isSelected()).assertIsDisplayed()
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheDarkThemeIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var chosenModes: MutableList<ThemeMode>

            @Before
            fun tapTheDarkTheme() {
                chosenModes = mutableListOf()
                compose.setContent { ScanMyLibTheme { SettingsContentOf(SETTINGS, onThemeMode = chosenModes::add) } }
                compose.onNodeWithText(THEME).performScrollTo().performClick()
                compose.onNodeWithText(DARK).performClick()
            }

            @Test
            fun `should apply it at once`() {
                assertEquals(listOf(ThemeMode.DARK), chosenModes)
            }

            @Test
            fun `should close the choice`() {
                compose.onNodeWithText(LIGHT).assertDoesNotExist()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheChoiceOfTheThemeIsCanceled {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var chosenModes: MutableList<ThemeMode>

            @Before
            fun cancelTheChoice() {
                chosenModes = mutableListOf()
                compose.setContent { ScanMyLibTheme { SettingsContentOf(SETTINGS, onThemeMode = chosenModes::add) } }
                compose.onNodeWithText(THEME).performScrollTo().performClick()
                compose.onNodeWithText(CANCEL).performClick()
            }

            @Test
            fun `should keep the theme`() {
                assertEquals(emptyList<ThemeMode>(), chosenModes)
            }

            @Test
            fun `should close the choice`() {
                compose.onNodeWithText(LIGHT).assertDoesNotExist()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheWallpaperColorsRowIsTappedWhileTheyAreOff {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var wallpaperColorChoices: MutableList<Boolean>

            @Before
            fun tapTheRow() {
                wallpaperColorChoices = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { SettingsContentOf(SETTINGS, onUsesWallpaperColors = wallpaperColorChoices::add) }
                }
                compose.onNodeWithText(WALLPAPER_COLORS).performScrollTo().performClick()
            }

            @Test
            fun `should ask for the wallpaper's colors`() {
                assertEquals(listOf(true), wallpaperColorChoices)
            }
        }
    }
}

private const val THEME = "Theme"
private const val SAME_AS_PHONE = "Same as the phone"
private const val LIGHT = "Light"
private const val DARK = "Dark"
private const val WALLPAPER_COLORS = "Wallpaper colors"
private const val ABOUT = "About"
private const val CANCEL = "Cancel"

private val THEMES = listOf(arrayOf<Any>("light", false), arrayOf<Any>("dark", true))

private val SETTINGS = SettingsUiState(
    settings = AppSettings(
        server = ServerConfig("http://192.168.1.10:8765/".toHttpUrl(), token = "example-token"),
        wifiOnly = true,
        keepLocalCopies = false,
        scannerMode = ScannerMode.CROP_ONLY,
        defaultCamera = ScanSource.GOOGLE_SCANNER,
        googleScannerUnavailable = false,
        themeMode = ThemeMode.SAME_AS_PHONE,
        usesWallpaperColors = false,
    ),
    keptCopies = KeptCopies(count = 0, bytes = 0),
)

@Composable
private fun SettingsContentOf(
    state: SettingsUiState,
    onThemeMode: (ThemeMode) -> Unit = {},
    onUsesWallpaperColors: (Boolean) -> Unit = {},
) {
    SettingsContent(
        state = state,
        update = UpdateState.UpToDate,
        snackbarHostState = SnackbarHostState(),
        onBack = {},
        onChangeServer = {},
        onTestConnection = {},
        onUnpair = {},
        onWifiOnly = {},
        onKeepLocalCopies = {},
        onDeleteKeptCopies = {},
        onDefaultCamera = {},
        onScannerMode = {},
        onThemeMode = onThemeMode,
        onUsesWallpaperColors = onUsesWallpaperColors,
        onCheckForUpdate = {},
        onInstallUpdate = {},
        onCancelUpdate = {},
    )
}
