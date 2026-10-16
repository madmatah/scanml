package fr.scanmylib.ui.components

import fr.scanmylib.api.OcrStatus
import fr.scanmylib.api.ServerStatus
import org.junit.Assert.assertEquals
import org.junit.Test

class ReadingUnavailableTest {

    @Test
    fun `text recognition is unavailable when the engine is unreachable or failing, whatever the PC says about it`() {
        val unavailable = listOf("unreachable", "error").associateWith { true }
        val available = listOf("idle", "starting", "ready", "stopping").associateWith { false }
        for ((state, expected) in unavailable + available) {
            for (lastError in listOf(null, "engine failed to start")) {
                val status = ServerStatus(version = "0.2.3", ocr = OcrStatus(state = state, lastError = lastError))
                assertEquals("$state, $lastError", expected, status.readingUnavailable)
            }
        }
    }
}
