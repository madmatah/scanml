package fr.scanmylib.ui.components

import fr.scanmylib.api.OcrStatus
import fr.scanmylib.api.ServerStatus
import kotlin.properties.Delegates
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ReadingUnavailableTest {
    @RunWith(Enclosed::class)
    class TheReadingUnavailableProperty {
        @RunWith(Parameterized::class)
        class WhenTheEngineIsUnreachableOrFailing(private val case: String, private val status: ServerStatus) {
            private var isReadingUnavailable by Delegates.notNull<Boolean>()

            @Before
            fun readTheStatus() {
                isReadingUnavailable = status.readingUnavailable
            }

            @Test
            fun `should say that text recognition is unavailable, whatever the PC says of its last error`() {
                assertTrue(case, isReadingUnavailable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun engines(): List<Array<Any>> = buildStatuses(listOf("unreachable", "error"))
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheEngineWorks(private val case: String, private val status: ServerStatus) {
            private var isReadingUnavailable by Delegates.notNull<Boolean>()

            @Before
            fun readTheStatus() {
                isReadingUnavailable = status.readingUnavailable
            }

            @Test
            fun `should say that text recognition is available, whatever the PC says of its last error`() {
                assertFalse(case, isReadingUnavailable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun engines(): List<Array<Any>> = buildStatuses(listOf("idle", "starting", "ready", "stopping"))
            }
        }
    }
}

private val LAST_ERRORS = listOf(null, "engine failed to start")

private fun buildStatuses(engineStates: List<String>): List<Array<Any>> = engineStates.flatMap { state ->
    LAST_ERRORS.map { lastError ->
        arrayOf(
            "$state, last error: $lastError",
            ServerStatus(version = "0.2.3", ocr = OcrStatus(state = state, lastError = lastError)),
        )
    }
}
