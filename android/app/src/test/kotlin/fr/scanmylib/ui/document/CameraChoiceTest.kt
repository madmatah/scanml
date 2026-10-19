package fr.scanmylib.ui.document

import fr.scanmylib.model.ScanSource
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class CameraChoiceTest {
    @RunWith(Enclosed::class)
    class TheCameraProperty {
        @RunWith(Parameterized::class)
        class WhenGivenTheDefaultCamera(
            private val case: String,
            private val scan: ScanUiState,
            private val expected: ScanSource,
        ) {
            private lateinit var camera: ScanSource

            @Before
            fun chooseTheCamera() {
                camera = scan.camera
            }

            @Test
            fun `should open it`() {
                assertEquals(case, expected, camera)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun defaultCameras(): List<Array<Any>> = listOf(
                    arrayOf("Google's scanner, the default one", ScanUiState(), ScanSource.GOOGLE_SCANNER),
                    arrayOf("the app's camera", ScanUiState(defaultCamera = ScanSource.CAMERA), ScanSource.CAMERA),
                )
            }
        }

        class WhenGoogleScannerDoesNotStart {
            private lateinit var camera: ScanSource

            @Before
            fun chooseTheCamera() {
                camera = SCANNER_UNAVAILABLE.camera
            }

            @Test
            fun `should open the app's camera`() {
                assertEquals(ScanSource.CAMERA, camera)
            }
        }

        class WhenGoogleScannerStartsAgain {
            private lateinit var camera: ScanSource

            @Before
            fun chooseTheCamera() {
                camera = SCANNER_UNAVAILABLE.copy(googleScannerUnavailable = false).camera
            }

            @Test
            fun `should open Google's scanner again, since it stayed the default camera`() {
                assertEquals(ScanSource.GOOGLE_SCANNER, camera)
            }
        }

        @RunWith(Parameterized::class)
        class WhenThePhoneHasNoCamera(private val case: String, private val scan: ScanUiState) {
            private lateinit var camera: ScanSource

            @Before
            fun chooseTheCamera() {
                camera = scan.camera
            }

            @Test
            fun `should open Google's scanner, even after it failed to start`() {
                assertEquals(case, ScanSource.GOOGLE_SCANNER, camera)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun choices(): List<Array<Any>> = listOf(
                    arrayOf(
                        "the app's camera chosen",
                        ScanUiState(defaultCamera = ScanSource.CAMERA, hasCamera = false),
                    ),
                    arrayOf(
                        "Google's scanner failed to start",
                        ScanUiState(googleScannerUnavailable = true, hasCamera = false),
                    ),
                )
            }
        }
    }
}

private val SCANNER_UNAVAILABLE =
    ScanUiState(defaultCamera = ScanSource.GOOGLE_SCANNER, googleScannerUnavailable = true)
