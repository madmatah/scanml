package fr.scanmylib.ui.components

import android.graphics.Color as AndroidColor
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureRoboImage
import fr.scanmylib.R
import fr.scanmylib.ui.PathRecord
import fr.scanmylib.ui.PixelPosition
import fr.scanmylib.ui.Translation
import fr.scanmylib.ui.drawOnBitmap
import fr.scanmylib.ui.findMostFrequentColor
import fr.scanmylib.ui.gatherDrawnPixels
import fr.scanmylib.ui.readVectorDrawing
import fr.scanmylib.ui.repaintIn
import fr.scanmylib.ui.shiftBy
import fr.scanmylib.ui.theme.ScanMyLibTheme
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(Enclosed::class)
class BrandMarkTest {
    @RunWith(Enclosed::class)
    class TheBrandMarkFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheAppShowsIt(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var colors: ColorScheme
            private var markColor by Delegates.notNull<Color>()

            @Before
            fun drawTheMark() {
                compose.setContent {
                    ScanMyLibTheme(dark = dark) {
                        colors = MaterialTheme.colorScheme
                        Box(
                            Modifier
                                .testTag(MARK)
                                .background(MaterialTheme.colorScheme.background)
                                .padding(MARGIN),
                        ) {
                            BrandMark()
                        }
                    }
                }
                val mark = compose.onNodeWithTag(MARK).captureToImage()
                mark.asAndroidBitmap().captureRoboImage("build/outputs/roborazzi/brand-mark-$theme.png")
                markColor = findMostFrequentColor(mark.toPixelMap(), colors.background)
            }

            @Test
            fun `should draw the mark in the theme's primary color`() {
                assertEquals(colors.primary, markColor)
            }

            @Test
            fun `should stay silent for accessibility services, as an image that only decorates`() {
                compose.onAllNodes(DESCRIBED_INSIDE_THE_MARK, useUnmergedTree = true).assertCountEquals(0)
            }

            companion object {
                private const val MARK = "mark"
                private val MARGIN = 16.dp
                private val DESCRIBED_INSIDE_THE_MARK = hasAnyAncestor(hasTestTag(MARK)) and
                    SemanticsMatcher.keyIsDefined(SemanticsProperties.ContentDescription)

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = listOf(arrayOf("light", false), arrayOf("dark", true))
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheBrandMarkDrawable {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenReadBesideTheLauncherIcon {
            private lateinit var brandMark: Map<PathRecord, Int>
            private lateinit var launcherMarkShifted: Map<PathRecord, Int>
            private var launcherRecordCount by Delegates.notNull<Int>()

            @Before
            fun readBothMarks() {
                val brandMarkRecords = readVectorDrawing(R.drawable.brand_mark).records
                val launcherRecords = readVectorDrawing(R.drawable.ic_launcher_foreground).records
                brandMark = brandMarkRecords.map { it.repaintIn(COLORS_ASIDE) }.groupingBy { it }.eachCount()
                launcherMarkShifted = launcherRecords
                    .map { it.repaintIn(COLORS_ASIDE).shiftBy(BRAND_MARK_SHIFT_UNITS) }
                    .groupingBy { it }
                    .eachCount()
                launcherRecordCount = launcherRecords.size
            }

            @Test
            fun `should hold the launcher icon's paths, shifted by its group, colors aside, since the app tints it`() {
                assertEquals(launcherMarkShifted, brandMark)
                assertTrue(launcherRecordCount > 0)
            }

            companion object {
                private const val COLORS_ASIDE = AndroidColor.BLACK
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenItsViewportFramesTheLauncherMark {
            private lateinit var launcherPixelsOutsideTheViewport: List<PixelPosition>
            private lateinit var gapPixelsByEdge: Map<String, Int?>
            private var launcherPixelCount by Delegates.notNull<Int>()

            @Before
            fun drawTheLauncherMarkAndReadTheViewport() {
                val brandMark = readVectorDrawing(R.drawable.brand_mark)
                val launcherLayer = drawOnBitmap(
                    checkNotNull(RuntimeEnvironment.getApplication().getDrawable(R.drawable.ic_launcher_foreground)),
                    LAUNCHER_LAYER_PIXELS,
                )
                val columns = computeViewportPixelRange(-BRAND_MARK_SHIFT_UNITS.x, brandMark.viewportWidthUnits)
                val rows = computeViewportPixelRange(-BRAND_MARK_SHIFT_UNITS.y, brandMark.viewportHeightUnits)
                val launcherPixels = gatherDrawnPixels(launcherLayer)
                launcherPixelsOutsideTheViewport = launcherPixels.filter { it.x !in columns || it.y !in rows }
                gapPixelsByEdge = mapOf(
                    "left" to launcherPixels.minOfOrNull { it.x }?.minus(columns.first),
                    "right" to launcherPixels.maxOfOrNull { it.x }?.let { columns.last - it },
                    "top" to launcherPixels.minOfOrNull { it.y }?.minus(rows.first),
                    "bottom" to launcherPixels.maxOfOrNull { it.y }?.let { rows.last - it },
                )
                launcherPixelCount = launcherPixels.size
            }

            @Test
            fun `should hold the whole mark inside its viewport, so that none of it is cut`() {
                assertEquals(emptyList<PixelPosition>(), launcherPixelsOutsideTheViewport)
                assertTrue(launcherPixelCount > 0)
            }

            @Test
            fun `should frame the mark within a unit of each edge, so that the app shows it at the size it gives it`() {
                assertEquals(
                    emptyMap<String, Int?>(),
                    gapPixelsByEdge.filterValues { it == null || it > PIXELS_PER_UNIT },
                )
            }

            companion object {
                private const val PIXELS_PER_UNIT = 4
                private const val LAUNCHER_LAYER_PIXELS = 108 * PIXELS_PER_UNIT

                private fun computeViewportPixelRange(startUnits: Float, lengthUnits: Float): IntRange =
                    (startUnits * PIXELS_PER_UNIT).toInt() until ((startUnits + lengthUnits) * PIXELS_PER_UNIT).toInt()
            }
        }
    }
}

private val BRAND_MARK_SHIFT_UNITS = Translation(-30f, -30f)
