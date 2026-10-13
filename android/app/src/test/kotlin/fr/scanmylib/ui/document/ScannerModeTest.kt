package fr.scanmylib.ui.document

import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import fr.scanmylib.model.ScannerMode
import org.junit.Assert.assertEquals
import org.junit.Test

class ScannerModeTest {

    @Test
    fun `each setting opens Google's scanner in the matching mode`() {
        assertEquals(GmsDocumentScannerOptions.SCANNER_MODE_BASE, ScannerMode.CROP_ONLY.gmsScannerMode())
        assertEquals(GmsDocumentScannerOptions.SCANNER_MODE_BASE_WITH_FILTER, ScannerMode.FILTERS.gmsScannerMode())
        assertEquals(GmsDocumentScannerOptions.SCANNER_MODE_FULL, ScannerMode.FULL.gmsScannerMode())
    }

    @Test
    fun `by default the scanner only crops`() {
        assertEquals(GmsDocumentScannerOptions.SCANNER_MODE_BASE, ScannerMode.DEFAULT.gmsScannerMode())
    }
}
