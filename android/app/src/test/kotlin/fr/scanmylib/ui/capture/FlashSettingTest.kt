package fr.scanmylib.ui.capture

import androidx.camera.core.ImageCapture
import org.junit.Assert.assertEquals
import org.junit.Test

class FlashSettingTest {

    @Test
    fun `the flash button cycles off, auto, on`() {
        assertEquals(FlashSetting.AUTO, FlashSetting.OFF.next)
        assertEquals(FlashSetting.ON, FlashSetting.AUTO.next)
        assertEquals(FlashSetting.OFF, FlashSetting.ON.next)
        assertEquals(FlashSetting.OFF, CaptureUiState().flash)
    }

    @Test
    fun `each setting is the matching CameraX flash mode`() {
        assertEquals(ImageCapture.FLASH_MODE_OFF, FlashSetting.OFF.imageCaptureMode)
        assertEquals(ImageCapture.FLASH_MODE_AUTO, FlashSetting.AUTO.imageCaptureMode)
        assertEquals(ImageCapture.FLASH_MODE_ON, FlashSetting.ON.imageCaptureMode)
    }
}
