package fr.scanmylib.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class ColorTest {
    @RunWith(Enclosed::class)
    class ThePickColorSchemeFunction {
        @RunWith(Parameterized::class)
        class WhenGivenAThemeAndAContrast(
            private val variant: String,
            private val dark: Boolean,
            private val contrast: Contrast,
            private val minimumTextRatio: Float,
            private val minimumOutlineRatio: Float,
        ) {
            private lateinit var colors: ColorScheme

            @Before
            fun pickTheColors() {
                colors = pickColorScheme(isDark = dark, contrast)
            }

            @Test
            fun `should draw the dark theme with light text on a dark background, and the light one the other way`() {
                assertEquals(variant, dark, colors.background.luminance() < colors.onSurface.luminance())
            }

            @Test
            fun `should keep every text readable on the colors it is drawn on`() {
                val measured = TEXT_COMBINATIONS.map { it.measure(colors) }
                assertTrue("nothing measured", measured.isNotEmpty())
                assertEquals(variant, emptyList<Measure>(), measured.filter { it.ratio < minimumTextRatio })
            }

            @Test
            fun `should give body text at least 7 to 1 on every surface, for long reading`() {
                val measured = BODY_TEXT_COMBINATIONS.map { it.measure(colors) }
                assertTrue("nothing measured", measured.isNotEmpty())
                assertEquals(variant, emptyList<Measure>(), measured.filter { it.ratio < BODY_TEXT_RATIO })
            }

            @Test
            fun `should keep outlines and ranges visible on the surfaces they are drawn on`() {
                val measured = OUTLINE_COMBINATIONS.map { it.measure(colors) }
                assertTrue("nothing measured", measured.isNotEmpty())
                assertEquals(variant, emptyList<Measure>(), measured.filter { it.ratio < minimumOutlineRatio })
            }

            companion object {
                // WCAG 2.2: text at 4.5:1 (1.4.3) or 7:1 (1.4.6), the parts of a control at 3:1 (1.4.11).
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun variants(): List<Array<Any>> = listOf(
                    arrayOf("light, standard contrast: text 4.5:1, outlines 3:1", false, Contrast.STANDARD, 4.5f, 3f),
                    arrayOf("light, medium contrast: text 7:1, outlines 4.5:1", false, Contrast.MEDIUM, 7f, 4.5f),
                    arrayOf("light, high contrast: text 7:1, outlines 4.5:1", false, Contrast.HIGH, 7f, 4.5f),
                    arrayOf("dark, standard contrast: text 4.5:1, outlines 3:1", true, Contrast.STANDARD, 4.5f, 3f),
                    arrayOf("dark, medium contrast: text 7:1, outlines 4.5:1", true, Contrast.MEDIUM, 7f, 4.5f),
                    arrayOf("dark, high contrast: text 7:1, outlines 4.5:1", true, Contrast.HIGH, 7f, 4.5f),
                )
            }
        }
    }
}

private const val BODY_TEXT_RATIO = 7f

private class Role(val name: String, val color: (ColorScheme) -> Color)

private class ColorCombination(val foreground: Role, val background: Role) {
    fun measure(colors: ColorScheme) = Measure(
        "${foreground.name} on ${background.name}",
        measureContrastRatio(foreground.color(colors), background.color(colors)),
    )
}

private data class Measure(val combination: String, val ratio: Float)

/** WCAG 2.2's contrast ratio, from 1 to 21. */
private fun measureContrastRatio(first: Color, second: Color): Float {
    val lighter = maxOf(first.luminance(), second.luminance())
    val darker = minOf(first.luminance(), second.luminance())
    return (lighter + 0.05f) / (darker + 0.05f)
}

private val BACKGROUND = Role("background") { it.background }
private val SURFACE_CONTAINER_LOWEST = Role("surfaceContainerLowest") { it.surfaceContainerLowest }
private val SURFACE_CONTAINER_LOW = Role("surfaceContainerLow") { it.surfaceContainerLow }
private val SURFACE_CONTAINER = Role("surfaceContainer") { it.surfaceContainer }
private val SURFACE_CONTAINER_HIGH = Role("surfaceContainerHigh") { it.surfaceContainerHigh }
private val SURFACE_CONTAINER_HIGHEST = Role("surfaceContainerHighest") { it.surfaceContainerHighest }

/** Every surface: screens, cards, sheets, dialogs and menus, badges and tracks. */
private val SURFACES = listOf(
    BACKGROUND,
    SURFACE_CONTAINER_LOWEST,
    SURFACE_CONTAINER_LOW,
    SURFACE_CONTAINER,
    SURFACE_CONTAINER_HIGH,
    SURFACE_CONTAINER_HIGHEST,
)

/** Where accent text goes: links and buttons on screens, cards, sheets and dialogs. */
private val CONTENT_SURFACES = listOf(BACKGROUND, SURFACE_CONTAINER_LOW, SURFACE_CONTAINER, SURFACE_CONTAINER_HIGH)

private val ON_SURFACE = Role("onSurface") { it.onSurface }
private val ON_SURFACE_VARIANT = Role("onSurfaceVariant") { it.onSurfaceVariant }
private val PRIMARY = Role("primary") { it.primary }
private val SECONDARY = Role("secondary") { it.secondary }
private val TERTIARY = Role("tertiary") { it.tertiary }
private val ERROR = Role("error") { it.error }
private val INVERSE_SURFACE = Role("inverseSurface") { it.inverseSurface }
private val OUTLINE = Role("outline") { it.outline }

private val BODY_TEXT_COMBINATIONS = SURFACES.map { ColorCombination(ON_SURFACE, it) }

private val TEXT_COMBINATIONS = BODY_TEXT_COMBINATIONS +
    SURFACES.map { ColorCombination(ON_SURFACE_VARIANT, it) } +
    listOf(PRIMARY, TERTIARY, ERROR).flatMap { accent -> CONTENT_SURFACES.map { ColorCombination(accent, it) } } +
    listOf(
        ColorCombination(Role("onPrimary") { it.onPrimary }, PRIMARY),
        ColorCombination(Role("onSecondary") { it.onSecondary }, SECONDARY),
        ColorCombination(Role("onTertiary") { it.onTertiary }, TERTIARY),
        ColorCombination(Role("onError") { it.onError }, ERROR),
        ColorCombination(
            Role("onPrimaryContainer") { it.onPrimaryContainer },
            Role("primaryContainer") { it.primaryContainer },
        ),
        ColorCombination(
            Role("onSecondaryContainer") { it.onSecondaryContainer },
            Role("secondaryContainer") { it.secondaryContainer },
        ),
        ColorCombination(
            Role("onTertiaryContainer") { it.onTertiaryContainer },
            Role("tertiaryContainer") { it.tertiaryContainer },
        ),
        ColorCombination(
            Role("onErrorContainer") { it.onErrorContainer },
            Role("errorContainer") { it.errorContainer },
        ),
        ColorCombination(Role("inverseOnSurface") { it.inverseOnSurface }, INVERSE_SURFACE),
        ColorCombination(Role("inversePrimary") { it.inversePrimary }, INVERSE_SURFACE),
    )

/** Field and chip borders on screens, sheets and dialogs; the scanned ranges on their track. */
private val OUTLINE_COMBINATIONS =
    listOf(BACKGROUND, SURFACE_CONTAINER_LOW, SURFACE_CONTAINER_HIGH).map { ColorCombination(OUTLINE, it) } +
        ColorCombination(PRIMARY, SURFACE_CONTAINER_HIGHEST)
