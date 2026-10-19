package fr.scanmylib.model

import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ThemeModeTest {
    @RunWith(Enclosed::class)
    class TheIsDarkMethod {
        @RunWith(Parameterized::class)
        class WhenThePhoneIsLightOrDark(
            private val choice: String,
            private val mode: ThemeMode,
            private val phoneIsDark: Boolean,
            private val expected: Boolean,
        ) {
            private var isDark by Delegates.notNull<Boolean>()

            @Before
            fun applyTheChoice() {
                isDark = mode.isDark(phoneIsDark)
            }

            @Test
            fun `should give the theme the user chose`() {
                assertEquals(choice, expected, isDark)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun choices(): List<Array<Any>> = listOf(
                    arrayOf("same as a light phone: light", ThemeMode.SAME_AS_PHONE, false, false),
                    arrayOf("same as a dark phone: dark", ThemeMode.SAME_AS_PHONE, true, true),
                    arrayOf("light on a dark phone: light", ThemeMode.LIGHT, true, false),
                    arrayOf("dark on a light phone: dark", ThemeMode.DARK, false, true),
                )
            }
        }
    }
}
