package fr.scanmylib

import android.graphics.Bitmap
import android.graphics.Color as AndroidColor
import android.graphics.Paint
import android.graphics.drawable.AdaptiveIconDrawable
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.Drawable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.vector.addPathNodes
import com.github.takahirom.roborazzi.captureRoboImage
import fr.scanmylib.ui.PathPaint
import fr.scanmylib.ui.PathRecord
import fr.scanmylib.ui.PixelPosition
import fr.scanmylib.ui.Translation
import fr.scanmylib.ui.VectorDrawing
import fr.scanmylib.ui.drawOnBitmap
import fr.scanmylib.ui.drawRecords
import fr.scanmylib.ui.gatherDrawnPixels
import fr.scanmylib.ui.gatherPixelsNear
import fr.scanmylib.ui.readAdaptiveIconLayers
import fr.scanmylib.ui.repaintIn
import fr.scanmylib.ui.theme.Contrast
import fr.scanmylib.ui.theme.pickColorScheme
import java.lang.reflect.Modifier
import kotlin.math.hypot
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(Enclosed::class)
class LauncherIconTest {
    @RunWith(Enclosed::class)
    class TheLauncherIconPlaceholder {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheBuildTypeIsNotDev {
            private var icon by Delegates.notNull<Int>()

            @Before
            fun readTheAppIcon() {
                icon = RuntimeEnvironment.getApplication().applicationInfo.icon
            }

            @Test
            fun `should name the ic_launcher mipmap, so that the production app shows its own icon`() {
                assertEquals(R.mipmap.ic_launcher, icon)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheIcLauncherMipmap {
        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenALauncherDrawsIt {
            private lateinit var colors: ProbedColors

            @Before
            fun drawTheIcon() {
                val icon = drawOnBitmap(inflateAdaptiveIcon(R.mipmap.ic_launcher), LAUNCHER_ICON_PIXELS)
                icon.captureRoboImage("build/outputs/roborazzi/launcher-icon-production.png")
                colors = probeAsALauncher(icon)
            }

            @Test
            fun `should draw the mark in the light theme's colors, so that the app matches its icon`() {
                val lightColors = pickColorScheme(isDark = false, Contrast.STANDARD)
                assertEquals(ProbedColors(page = lightColors.primary, margin = lightColors.background), colors)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenALauncherThemesIt {
            private lateinit var colors: ProbedColors

            @Before
            fun drawTheThemedIcon() {
                val icon = drawOnBitmap(
                    themeAsALauncher(inflateAdaptiveIcon(R.mipmap.ic_launcher)),
                    LAUNCHER_ICON_PIXELS,
                )
                icon.captureRoboImage("build/outputs/roborazzi/launcher-icon-production-themed.png")
                colors = probeAsALauncher(icon)
            }

            @Test
            fun `should draw the page opaque and leave the margin clear, so that the launcher's colors show whole`() {
                assertEquals(ProbedColors(page = THEMED_ICON_FOREGROUND, margin = THEMED_ICON_BACKGROUND), colors)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheIcLauncherDevMipmap {
        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenALauncherDrawsIt {
            private lateinit var colors: ProbedColors

            @Before
            fun drawTheIcon() {
                val icon = drawOnBitmap(inflateAdaptiveIcon(R.mipmap.ic_launcher_dev), LAUNCHER_ICON_PIXELS)
                icon.captureRoboImage("build/outputs/roborazzi/launcher-icon-development.png")
                colors = probeAsALauncher(icon)
            }

            @Test
            fun `should draw the mark in paper cream on orange, so that the development app stands apart`() {
                assertEquals(ProbedColors(page = PAPER_CREAM, margin = ORANGE), colors)
            }

            companion object {
                private val ORANGE = Color(0xFFA84300)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenALauncherThemesIt {
            private lateinit var colors: ProbedColors

            @Before
            fun drawTheThemedIcon() {
                val icon = drawOnBitmap(
                    themeAsALauncher(inflateAdaptiveIcon(R.mipmap.ic_launcher_dev)),
                    LAUNCHER_ICON_PIXELS,
                )
                icon.captureRoboImage("build/outputs/roborazzi/launcher-icon-development-themed.png")
                colors = probeAsALauncher(icon)
            }

            @Test
            fun `should draw the page opaque and leave the margin clear, so that the launcher's colors show whole`() {
                assertEquals(ProbedColors(page = THEMED_ICON_FOREGROUND, margin = THEMED_ICON_BACKGROUND), colors)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsLayersAreReadBesideTheProductionOnes {
            private lateinit var productionForegroundInPaperCream: LayerStructure
            private lateinit var developmentForeground: LayerStructure
            private var productionForegroundRecordCount by Delegates.notNull<Int>()
            private lateinit var productionMonochromeWithoutTheLowerRightCorner: LayerStructure
            private lateinit var developmentMonochromeOutsideItsTag: LayerStructure
            private var productionMonochromeRecordCount by Delegates.notNull<Int>()
            private var productionMonochromeHasTheLowerRightCorner by Delegates.notNull<Boolean>()
            private lateinit var tagRecordsNotInThinStrokes: List<PathRecord>
            private lateinit var productionMonochromeRecordsInThinStrokes: List<PathRecord>
            private var tagRecordCount by Delegates.notNull<Int>()

            @Before
            fun readTheLayers() {
                val production = readAdaptiveIconLayers(R.mipmap.ic_launcher)
                val development = readAdaptiveIconLayers(R.mipmap.ic_launcher_dev)
                productionForegroundInPaperCream = readLayerStructure(
                    production.foreground,
                    production.foreground.records.map { it.repaintIn(PAPER_CREAM.toArgb()) },
                )
                developmentForeground = readLayerStructure(development.foreground, development.foreground.records)
                productionForegroundRecordCount = production.foreground.records.size
                val productionMonochrome = production.monochrome.records.map { it.repaintIn(COLORS_ASIDE) }
                val (tag, developmentMonochromeOutsideTheTag) =
                    development.monochrome.records.map { it.repaintIn(COLORS_ASIDE) }.partition(::isInTheTag)
                productionMonochromeWithoutTheLowerRightCorner =
                    readLayerStructure(production.monochrome, productionMonochrome - LOWER_RIGHT_CORNER)
                developmentMonochromeOutsideItsTag =
                    readLayerStructure(development.monochrome, developmentMonochromeOutsideTheTag)
                productionMonochromeRecordCount = productionMonochrome.size
                productionMonochromeHasTheLowerRightCorner = LOWER_RIGHT_CORNER in productionMonochrome
                tagRecordsNotInThinStrokes = tag.filterNot { isAThinStroke(it) }
                productionMonochromeRecordsInThinStrokes = productionMonochrome.filter { isAThinStroke(it) }
                tagRecordCount = tag.size
            }

            @Test
            fun `should draw the production foreground's paths, in paper cream, on the same viewport`() {
                assertEquals(productionForegroundInPaperCream, developmentForeground)
                assertTrue(productionForegroundRecordCount > 0)
            }

            @Test
            fun `should draw, outside its tag, the production monochrome but the tag's corner, on the same viewport`() {
                assertEquals(productionMonochromeWithoutTheLowerRightCorner, developmentMonochromeOutsideItsTag)
                assertTrue(productionMonochromeRecordCount > 0)
                assertTrue(productionMonochromeHasTheLowerRightCorner)
            }

            @Test
            fun `should draw its tag in thin strokes, unlike the mark, so that themed icons tell the two apps apart`() {
                assertEquals(emptyList<PathRecord>(), tagRecordsNotInThinStrokes)
                assertEquals(emptyList<PathRecord>(), productionMonochromeRecordsInThinStrokes)
                assertTrue(tagRecordCount > 0)
            }

            companion object {
                private const val COLORS_ASIDE = AndroidColor.BLACK
                private const val MARK_STROKE_WIDTH_UNITS = 4.5f
                private const val TAG_STROKE_WIDTH_UNITS = 1.5f
                private val LOWER_RIGHT_CORNER = PathRecord(
                    groupNames = emptyList(),
                    translationUnits = Translation(0f, 0f),
                    nodes = addPathNodes("M75 65v10H65"),
                    paint = PathPaint(
                        strokeColor = COLORS_ASIDE,
                        strokeWidthUnits = MARK_STROKE_WIDTH_UNITS,
                        strokeCap = Paint.Cap.ROUND,
                        strokeJoin = Paint.Join.ROUND,
                    ),
                )

                private fun isAThinStroke(record: PathRecord): Boolean =
                    record.paint.strokeWidthUnits == TAG_STROKE_WIDTH_UNITS && !record.paint.isFilled
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenItsTagIsDrawnApartFromTheRestOfItsMonochrome {
            private lateinit var tagPixelsNearTheRest: List<PixelPosition>
            private var tagPixelCount by Delegates.notNull<Int>()

            @Before
            fun drawTheTagAndTheRest() {
                val monochrome = readAdaptiveIconLayers(R.mipmap.ic_launcher_dev).monochrome
                val (tag, rest) = monochrome.records.partition(::isInTheTag)
                val tagPixels = drawRecords(tag, LAYER_PIXELS, LAYER_PIXELS_PER_UNIT.toFloat())
                val restPixels = drawRecords(rest, LAYER_PIXELS, LAYER_PIXELS_PER_UNIT.toFloat())
                val drawnTagPixels = gatherDrawnPixels(tagPixels)
                tagPixelsNearTheRest = gatherPixelsNear(drawnTagPixels, restPixels, CLEARANCE_PIXELS)
                tagPixelCount = drawnTagPixels.size
            }

            @Test
            fun `should keep its tag a unit and a half from the mark, so that the two never merge into one shape`() {
                assertEquals(emptyList<PixelPosition>(), tagPixelsNearTheRest)
                assertTrue(tagPixelCount > 0)
            }

            companion object {
                private const val CLEARANCE_PIXELS = 3 * LAYER_PIXELS_PER_UNIT / 2
            }
        }
    }

    @RunWith(ParameterizedRobolectricTestRunner::class)
    @GraphicsMode(GraphicsMode.Mode.NATIVE)
    @Config(sdk = [36])
    class TheLauncherLayer(
        private val name: String,
        private val mipmapId: Int,
        private val readLayer: (AdaptiveIconDrawable) -> Drawable,
    ) {
        private lateinit var pixelsOutsideTheSafeCircle: List<PixelPosition>
        private var drawnPixelCount by Delegates.notNull<Int>()

        @Before
        fun drawTheLayer() {
            val layer = drawLayerAlone(readLayer(inflateAdaptiveIcon(mipmapId)))
            val drawnPixels = gatherDrawnPixels(layer)
            drawnPixelCount = drawnPixels.size
            pixelsOutsideTheSafeCircle = drawnPixels.filter { isOutsideTheSafeCircle(it) }
        }

        @Test
        fun `should keep every pixel inside the safe circle, so that no launcher's mask cuts the mark`() {
            assertEquals("$name outside the safe circle", emptyList<PixelPosition>(), pixelsOutsideTheSafeCircle)
            assertTrue("$name draws nothing", drawnPixelCount > 0)
        }

        companion object {
            private const val SAFE_CIRCLE_RADIUS_PIXELS = 33 * LAYER_PIXELS_PER_UNIT
            private const val ANTI_ALIASING_PIXELS = 1

            @JvmStatic
            @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
            fun layers(): List<Array<Any>> {
                val mipmaps = R.mipmap::class.java.fields
                    .filter { Modifier.isStatic(it.modifiers) && it.type == Int::class.javaPrimitiveType }
                val mipmapIds = mipmaps.map { it.getInt(null) }
                check(R.mipmap.ic_launcher in mipmapIds && R.mipmap.ic_launcher_dev in mipmapIds) {
                    "the reflection on R.mipmap misses a launcher icon"
                }
                return mipmaps.flatMap { mipmap ->
                    LAYER_READERS.map { (layerName, readLayer) ->
                        arrayOf("${mipmap.name} $layerName", mipmap.getInt(null), readLayer)
                    }
                }
            }

            private val LAYER_READERS: Map<String, (AdaptiveIconDrawable) -> Drawable> = mapOf(
                "foreground" to { icon -> icon.foreground },
                "monochrome" to ::readMonochrome,
            )

            private fun isOutsideTheSafeCircle(pixel: PixelPosition): Boolean {
                val center = LAYER_PIXELS / 2.0
                val distance = hypot(pixel.x + 0.5 - center, pixel.y + 0.5 - center)
                return distance > SAFE_CIRCLE_RADIUS_PIXELS + ANTI_ALIASING_PIXELS
            }
        }
    }
}

private data class ProbedColors(val page: Color, val margin: Color)

private data class LayerStructure(
    val viewportWidthUnits: Float,
    val viewportHeightUnits: Float,
    val recordCounts: Map<PathRecord, Int>,
)

private data class CanvasPoint(val x: Float, val y: Float)

private const val LAUNCHER_ICON_PIXELS = 432
private const val LAYER_PIXELS = 432
private const val LAYER_PIXELS_PER_UNIT = 4
private const val CANVAS_UNITS = 108f
private const val VISIBLE_UNITS = 72f

private const val TAG_GROUP = "tag"

private val PAGE_POINT = CanvasPoint(46f, 56f)
private val MARGIN_POINT = CanvasPoint(54f, 40f)

private val THEMED_ICON_BACKGROUND = Color(0xFFE6E0F3)
private val THEMED_ICON_FOREGROUND = Color(0xFF2B2640)
private val PAPER_CREAM = Color(0xFFFBF8F1)

private fun inflateAdaptiveIcon(mipmapId: Int): AdaptiveIconDrawable =
    checkNotNull(RuntimeEnvironment.getApplication().getDrawable(mipmapId) as? AdaptiveIconDrawable) {
        "the mipmap is not an adaptive icon"
    }

private fun readMonochrome(icon: AdaptiveIconDrawable): Drawable = checkNotNull(icon.monochrome) {
    "the adaptive icon has no monochrome layer"
}

private fun themeAsALauncher(icon: AdaptiveIconDrawable): AdaptiveIconDrawable = AdaptiveIconDrawable(
    ColorDrawable(THEMED_ICON_BACKGROUND.toArgb()),
    readMonochrome(icon).mutate().apply { setTint(THEMED_ICON_FOREGROUND.toArgb()) },
)

private fun drawLayerAlone(layer: Drawable): Bitmap = drawOnBitmap(layer, LAYER_PIXELS)

private fun readLayerStructure(layer: VectorDrawing, records: List<PathRecord>): LayerStructure =
    LayerStructure(layer.viewportWidthUnits, layer.viewportHeightUnits, records.groupingBy { it }.eachCount())

private fun isInTheTag(record: PathRecord): Boolean = TAG_GROUP in record.groupNames

private fun probeAsALauncher(icon: Bitmap): ProbedColors =
    ProbedColors(page = readLauncherColor(icon, PAGE_POINT), margin = readLauncherColor(icon, MARGIN_POINT))

private fun readLauncherColor(icon: Bitmap, point: CanvasPoint): Color {
    val hiddenUnits = (CANVAS_UNITS - VISIBLE_UNITS) / 2
    val pixelsPerUnit = icon.width / VISIBLE_UNITS
    val column = ((point.x - hiddenUnits) * pixelsPerUnit).toInt()
    val row = ((point.y - hiddenUnits) * pixelsPerUnit).toInt()
    return Color(icon.getPixel(column, row))
}
