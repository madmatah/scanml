package fr.scanmylib.ui.theme

import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ContrastTest {
    @RunWith(Enclosed::class)
    class ThePickContrastFunction {
        @RunWith(Parameterized::class)
        class WhenGivenTheLevelOfThePhone(
            private val setting: String,
            private val level: Float,
            private val expected: Contrast,
        ) {
            private lateinit var contrast: Contrast

            @Before
            fun readTheLevel() {
                contrast = pickContrast(level)
            }

            @Test
            fun `should pick the variant of the colors that the setting asks for`() {
                assertEquals(setting, expected, contrast)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun levels(): List<Array<Any>> = listOf(
                    arrayOf("standard, 0, gives the standard colors", 0f, Contrast.STANDARD),
                    arrayOf("medium, 0.5, gives the medium-contrast colors", 0.5f, Contrast.MEDIUM),
                    arrayOf("high, 1, gives the high-contrast colors", 1f, Contrast.HIGH),
                    arrayOf("a level below standard gives the standard colors", -1f, Contrast.STANDARD),
                )
            }
        }
    }
}
