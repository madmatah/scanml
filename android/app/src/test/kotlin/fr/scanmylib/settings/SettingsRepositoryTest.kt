package fr.scanmylib.settings

import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import java.io.File
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class SettingsRepositoryTest {

    @get:Rule
    val folder = TemporaryFolder()

    @Test
    fun `Google's scanner only crops until the user asks for more`() = runTest {
        val settings = SettingsRepository(
            PreferenceDataStoreFactory.create(scope = backgroundScope) {
                File(folder.root, "settings.preferences_pb")
            },
        )
        assertEquals(ScannerMode.CROP_ONLY, settings.current().scannerMode)
        assertEquals(ScanSource.GOOGLE_SCANNER, settings.current().scanSource)

        settings.setScannerMode(ScannerMode.FULL)
        settings.setScanSource(ScanSource.CAMERA)
        assertEquals(ScannerMode.FULL, settings.current().scannerMode)
        assertEquals(ScanSource.CAMERA, settings.current().scanSource)
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
