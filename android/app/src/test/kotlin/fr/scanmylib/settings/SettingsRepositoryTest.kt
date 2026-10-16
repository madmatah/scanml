package fr.scanmylib.settings

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import fr.scanmylib.expectFailure
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import java.io.File
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class SettingsRepositoryTest {

    @get:Rule
    val folder = TemporaryFolder()

    private fun TestScope.dataStore() = PreferenceDataStoreFactory.create(scope = backgroundScope) {
        File(folder.root, "settings.preferences_pb")
    }

    @Test
    fun `Google's scanner only crops until the user asks for more`() = runTest {
        val settings = SettingsRepository(dataStore())
        assertEquals(ScannerMode.CROP_ONLY, settings.current().scannerMode)
        assertEquals(ScanSource.GOOGLE_SCANNER, settings.current().defaultCamera)

        settings.setScannerMode(ScannerMode.FULL)
        settings.setDefaultCamera(ScanSource.CAMERA)
        assertEquals(ScannerMode.FULL, settings.current().scannerMode)
        assertEquals(ScanSource.CAMERA, settings.current().defaultCamera)
    }

    @Test
    fun `the photo picker is never the default camera`() = runTest {
        val dataStore = dataStore()
        // Stored by a version where the last source of a run became the default.
        dataStore.edit { it[stringPreferencesKey("scan_source")] = ScanSource.PHOTO_PICKER.name }
        val settings = SettingsRepository(dataStore)
        assertEquals(ScanSource.GOOGLE_SCANNER, settings.current().defaultCamera)

        expectFailure<IllegalArgumentException> { settings.setDefaultCamera(ScanSource.PHOTO_PICKER) }
        assertEquals(ScanSource.GOOGLE_SCANNER, settings.current().defaultCamera)
    }

    @Test
    fun `Google's scanner is remembered unavailable until it starts again`() = runTest {
        val settings = SettingsRepository(dataStore())
        assertFalse(settings.current().googleScannerUnavailable)
        settings.setGoogleScannerUnavailable(true)
        assertTrue(settings.current().googleScannerUnavailable)
        settings.setGoogleScannerUnavailable(false)
        assertFalse(settings.current().googleScannerUnavailable)

        // Choosing it again gives it another try; choosing the app's camera does not.
        settings.setGoogleScannerUnavailable(true)
        settings.setDefaultCamera(ScanSource.CAMERA)
        assertTrue(settings.current().googleScannerUnavailable)
        settings.setDefaultCamera(ScanSource.GOOGLE_SCANNER)
        assertFalse(settings.current().googleScannerUnavailable)
    }

    @Test
    fun `stored names are read back, unknown ones give the default`() {
        ScannerMode.entries.forEach { assertEquals(it, storedEnum(it.name, ScannerMode.DEFAULT)) }
        ScanSource.entries.forEach { assertEquals(it, storedEnum(it.name, ScanSource.DEFAULT)) }
        assertEquals(ScannerMode.CROP_ONLY, storedEnum(null, ScannerMode.DEFAULT))
        assertEquals(ScannerMode.CROP_ONLY, storedEnum("SCANNER_MODE_FULL", ScannerMode.DEFAULT))
        assertEquals(ScanSource.GOOGLE_SCANNER, storedEnum("camera", ScanSource.DEFAULT))
    }
}
