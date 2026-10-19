package fr.scanmylib.ui.document

import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import fr.scanmylib.model.ScannerMode
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ScannerModeTest {
    @RunWith(Enclosed::class)
    class TheGmsScannerModeFunction {
        @RunWith(Parameterized::class)
        class WhenGivenASetting(
            private val case: String,
            private val setting: ScannerMode,
            private val expected: Int,
        ) {
            private var scannerMode by Delegates.notNull<Int>()

            @Before
            fun pickTheScannerMode() {
                scannerMode = setting.gmsScannerMode()
            }

            @Test
            fun `should open Google's scanner in the matching mode`() {
                assertEquals(case, expected, scannerMode)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun settings(): List<Array<Any>> = listOf(
                    arrayOf(
                        "crop only: the base mode",
                        ScannerMode.CROP_ONLY,
                        GmsDocumentScannerOptions.SCANNER_MODE_BASE,
                    ),
                    arrayOf(
                        "filters: the base mode with filters",
                        ScannerMode.FILTERS,
                        GmsDocumentScannerOptions.SCANNER_MODE_BASE_WITH_FILTER,
                    ),
                    arrayOf("full: the full mode", ScannerMode.FULL, GmsDocumentScannerOptions.SCANNER_MODE_FULL),
                )
            }
        }

        class WhenGivenTheDefaultSetting {
            private var scannerMode by Delegates.notNull<Int>()

            @Before
            fun pickTheScannerMode() {
                scannerMode = ScannerMode.DEFAULT.gmsScannerMode()
            }

            @Test
            fun `should only crop`() {
                assertEquals(GmsDocumentScannerOptions.SCANNER_MODE_BASE, scannerMode)
            }
        }
    }
}
