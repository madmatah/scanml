package fr.scanmylib.ui.capture

import androidx.camera.core.ImageCapture
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class FlashSettingTest {
    @RunWith(Enclosed::class)
    class TheNextProperty {
        @RunWith(Parameterized::class)
        class WhenTheFlashButtonIsTapped(
            private val case: String,
            private val setting: FlashSetting,
            private val expected: FlashSetting,
        ) {
            private lateinit var nextSetting: FlashSetting

            @Before
            fun tapTheFlashButton() {
                nextSetting = setting.next
            }

            @Test
            fun `should cycle off, auto, on`() {
                assertEquals(case, expected, nextSetting)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun taps(): List<Array<Any>> = listOf(
                    arrayOf("off to auto", FlashSetting.OFF, FlashSetting.AUTO),
                    arrayOf("auto to on", FlashSetting.AUTO, FlashSetting.ON),
                    arrayOf("on back to off", FlashSetting.ON, FlashSetting.OFF),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheImageCaptureModeProperty {
        @RunWith(Parameterized::class)
        class WhenGivenASetting(
            private val case: String,
            private val setting: FlashSetting,
            private val expected: Int,
        ) {
            @Test
            fun `should be the matching flash mode of CameraX`() {
                assertEquals(case, expected, setting.imageCaptureMode)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun settings(): List<Array<Any>> = listOf(
                    arrayOf("off", FlashSetting.OFF, ImageCapture.FLASH_MODE_OFF),
                    arrayOf("auto", FlashSetting.AUTO, ImageCapture.FLASH_MODE_AUTO),
                    arrayOf("on", FlashSetting.ON, ImageCapture.FLASH_MODE_ON),
                )
            }
        }
    }
}
