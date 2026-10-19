package fr.scanmylib.settings

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.model.ThemeMode
import java.io.File
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class SettingsRepositoryTest {
    @RunWith(Enclosed::class)
    class TheCurrentMethod {
        class WhenNothingIsStored {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun readTheSettings() = runTest {
                storedSettings = createRepository(folder).current()
            }

            @Test
            fun `should have Google's scanner only crop the pages, until the user asks for more`() {
                assertEquals(ScannerMode.CROP_ONLY, storedSettings.scannerMode)
            }

            @Test
            fun `should open Google's scanner`() {
                assertEquals(ScanSource.GOOGLE_SCANNER, storedSettings.defaultCamera)
            }

            @Test
            fun `should take Google's scanner for available`() {
                assertFalse(storedSettings.googleScannerUnavailable)
            }

            @Test
            fun `should follow the theme of the phone`() {
                assertEquals(ThemeMode.SAME_AS_PHONE, storedSettings.themeMode)
            }

            @Test
            fun `should keep the colors of ScanMyLib`() {
                assertFalse(storedSettings.usesWallpaperColors)
            }
        }

        class WhenAnOlderVersionStoredThePhotoPicker {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun readTheSettings() = runTest {
                val dataStore = createDataStore(folder)
                storeThePhotoPickerAsAnOlderVersionDid(dataStore)
                storedSettings = SettingsRepository(dataStore).current()
            }

            @Test
            fun `should open the default camera, since the photo picker is never one`() {
                assertEquals(ScanSource.GOOGLE_SCANNER, storedSettings.defaultCamera)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSetScannerModeMethod {
        class WhenTheUserChoosesTheFullMode {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun chooseTheMode() = runTest {
                val repository = createRepository(folder)
                chooseTheFullMode(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should keep the mode chosen`() {
                assertEquals(ScannerMode.FULL, storedSettings.scannerMode)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSetDefaultCameraMethod {
        class WhenTheUserChoosesTheAppsCamera {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun chooseTheCamera() = runTest {
                val repository = createRepository(folder)
                chooseTheAppsCamera(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should keep the camera chosen`() {
                assertEquals(ScanSource.CAMERA, storedSettings.defaultCamera)
            }
        }

        class WhenTheUserChoseTheFullModeAndChoosesTheAppsCamera {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun chooseTheCamera() = runTest {
                val repository = createRepository(folder)
                chooseTheFullMode(repository)
                chooseTheAppsCamera(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should keep the scanner mode chosen`() {
                assertEquals(ScannerMode.FULL, storedSettings.scannerMode)
            }
        }

        class WhenGivenThePhotoPicker {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var chooseThePhotoPicker: suspend TestScope.() -> Unit

            @Before
            fun keepTheChoice() {
                chooseThePhotoPicker = { createRepository(folder).setDefaultCamera(ScanSource.PHOTO_PICKER) }
            }

            @Test
            fun `should refuse it, since the photo picker is no camera`() = runTest {
                val failure = runCatching { chooseThePhotoPicker() }.exceptionOrNull()
                assertEquals(IllegalArgumentException::class.java, failure?.javaClass)
                assertEquals("not a camera: PHOTO_PICKER", failure?.message)
            }
        }

        class WhenTheUserChoseTheAppsCameraAndTriesThePhotoPicker {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun tryThePhotoPicker() = runTest {
                val repository = createRepository(folder)
                chooseTheAppsCamera(repository)
                tryToChooseThePhotoPicker(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should keep the app's camera, since the photo picker is refused before anything is stored`() {
                assertEquals(ScanSource.CAMERA, storedSettings.defaultCamera)
            }
        }

        class WhenGoogleScannerFailedToStartAndTheAppsCameraIsChosen {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun chooseTheCamera() = runTest {
                val repository = createRepository(folder)
                markGoogleScannerUnavailable(repository)
                chooseTheAppsCamera(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should still remember Google's scanner unavailable`() {
                assertTrue(storedSettings.googleScannerUnavailable)
            }
        }

        class WhenGoogleScannerFailedToStartAndIsChosenAgainAfterTheAppsCamera {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun chooseGoogleScannerAgain() = runTest {
                val repository = createRepository(folder)
                markGoogleScannerUnavailable(repository)
                chooseTheAppsCamera(repository)
                chooseGoogleScanner(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should give Google's scanner another try`() {
                assertFalse(storedSettings.googleScannerUnavailable)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSetGoogleScannerUnavailableMethod {
        class WhenGoogleScannerFailsToStart {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun failToStart() = runTest {
                val repository = createRepository(folder)
                markGoogleScannerUnavailable(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should remember it unavailable`() {
                assertTrue(storedSettings.googleScannerUnavailable)
            }
        }

        class WhenGoogleScannerFailedToStartAndStartsAgain {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun startAgain() = runTest {
                val repository = createRepository(folder)
                markGoogleScannerUnavailable(repository)
                markGoogleScannerStartedAgain(repository)
                storedSettings = repository.current()
            }

            @Test
            fun `should forget it was unavailable`() {
                assertFalse(storedSettings.googleScannerUnavailable)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSetThemeModeMethod {
        class WhenTheUserChoosesTheDarkTheme {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun chooseTheDarkTheme() = runTest {
                val repository = createRepository(folder)
                repository.setThemeMode(ThemeMode.DARK)
                storedSettings = repository.current()
            }

            @Test
            fun `should keep the theme chosen`() {
                assertEquals(ThemeMode.DARK, storedSettings.themeMode)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSetUsesWallpaperColorsMethod {
        class WhenTheUserAsksForTheColorsOfTheWallpaper {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var storedSettings: AppSettings

            @Before
            fun askForTheWallpaperColors() = runTest {
                val repository = createRepository(folder)
                repository.setUsesWallpaperColors(true)
                storedSettings = repository.current()
            }

            @Test
            fun `should use them`() {
                assertTrue(storedSettings.usesWallpaperColors)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheStoredEnumFunction {
        @RunWith(Parameterized::class)
        class WhenGivenTheNameOfAScannerMode(private val mode: ScannerMode) {
            private lateinit var storedMode: ScannerMode

            @Before
            fun readTheName() {
                storedMode = storedEnum(mode.name, ScannerMode.DEFAULT)
            }

            @Test
            fun `should read the mode back`() {
                assertEquals(mode, storedMode)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun modes(): List<Array<Any>> = ScannerMode.entries.map { arrayOf(it) }
            }
        }

        @RunWith(Parameterized::class)
        class WhenGivenTheNameOfASource(private val source: ScanSource) {
            private lateinit var storedSource: ScanSource

            @Before
            fun readTheName() {
                storedSource = storedEnum(source.name, ScanSource.DEFAULT)
            }

            @Test
            fun `should read the source back`() {
                assertEquals(source, storedSource)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun sources(): List<Array<Any>> = ScanSource.entries.map { arrayOf(it) }
            }
        }

        @RunWith(Parameterized::class)
        class WhenGivenTheNameOfAThemeMode(private val mode: ThemeMode) {
            private lateinit var storedMode: ThemeMode

            @Before
            fun readTheName() {
                storedMode = storedEnum(mode.name, ThemeMode.DEFAULT)
            }

            @Test
            fun `should read the mode back`() {
                assertEquals(mode, storedMode)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun modes(): List<Array<Any>> = ThemeMode.entries.map { arrayOf(it) }
            }
        }

        class WhenNoNameIsStored {
            private lateinit var storedMode: ScannerMode

            @Before
            fun readNoName() {
                storedMode = storedEnum(null, ScannerMode.DEFAULT)
            }

            @Test
            fun `should give the default`() {
                assertEquals(ScannerMode.CROP_ONLY, storedMode)
            }
        }

        class WhenTheNameIsNoLongerAConstant {
            private lateinit var storedMode: ScannerMode

            @Before
            fun readTheName() {
                storedMode = storedEnum("SCANNER_MODE_FULL", ScannerMode.DEFAULT)
            }

            @Test
            fun `should give the default`() {
                assertEquals(ScannerMode.CROP_ONLY, storedMode)
            }
        }

        class WhenTheNameDiffersInCase {
            private lateinit var storedSource: ScanSource

            @Before
            fun readTheName() {
                storedSource = storedEnum("camera", ScanSource.DEFAULT)
            }

            @Test
            fun `should give the default`() {
                assertEquals(ScanSource.GOOGLE_SCANNER, storedSource)
            }
        }
    }
}

private fun TestScope.createDataStore(folder: TemporaryFolder): DataStore<Preferences> =
    PreferenceDataStoreFactory.create(scope = backgroundScope) { File(folder.root, "settings.preferences_pb") }

private fun TestScope.createRepository(folder: TemporaryFolder) = SettingsRepository(createDataStore(folder))

private suspend fun storeThePhotoPickerAsAnOlderVersionDid(dataStore: DataStore<Preferences>) {
    dataStore.edit { it[stringPreferencesKey("scan_source")] = ScanSource.PHOTO_PICKER.name }
}

private suspend fun chooseTheFullMode(repository: SettingsRepository) {
    repository.setScannerMode(ScannerMode.FULL)
}

private suspend fun chooseTheAppsCamera(repository: SettingsRepository) {
    repository.setDefaultCamera(ScanSource.CAMERA)
}

private suspend fun tryToChooseThePhotoPicker(repository: SettingsRepository): IllegalArgumentException? = try {
    repository.setDefaultCamera(ScanSource.PHOTO_PICKER)
    null
} catch (e: IllegalArgumentException) {
    e
}

private suspend fun chooseGoogleScanner(repository: SettingsRepository) {
    repository.setDefaultCamera(ScanSource.GOOGLE_SCANNER)
}

private suspend fun markGoogleScannerUnavailable(repository: SettingsRepository) {
    repository.setGoogleScannerUnavailable(true)
}

private suspend fun markGoogleScannerStartedAgain(repository: SettingsRepository) {
    repository.setGoogleScannerUnavailable(false)
}
