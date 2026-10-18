package fr.scanmylib.ui.document

import fr.scanmylib.model.ScanSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraChoiceTest {

    @Test
    fun `Scan opens the default camera`() {
        assertEquals(ScanSource.GOOGLE_SCANNER, ScanUiState().camera)
        assertEquals(ScanSource.CAMERA, ScanUiState(defaultCamera = ScanSource.CAMERA).camera)
    }

    @Test
    fun `while Google's scanner does not start, Scan opens the app's camera`() {
        val scan = ScanUiState(defaultCamera = ScanSource.GOOGLE_SCANNER, googleScannerUnavailable = true)
        assertEquals(ScanSource.CAMERA, scan.camera)
        // The default stays: once the scanner starts again, Scan opens it again.
        assertEquals(ScanSource.GOOGLE_SCANNER, scan.copy(googleScannerUnavailable = false).camera)
    }

    @Test
    fun `without a camera, Scan opens Google's scanner, even after it failed`() {
        assertEquals(
            ScanSource.GOOGLE_SCANNER,
            ScanUiState(defaultCamera = ScanSource.CAMERA, hasCamera = false).camera,
        )
        assertEquals(
            ScanSource.GOOGLE_SCANNER,
            ScanUiState(googleScannerUnavailable = true, hasCamera = false).camera,
        )
    }

    @Test
    fun `an empty scanner result is only reported when the storage is nearly full`() {
        assertTrue(isStorageLow(0))
        assertTrue(isStorageLow(20L * 1024 * 1024))
        assertFalse(isStorageLow(2L * 1024 * 1024 * 1024))
    }
}
