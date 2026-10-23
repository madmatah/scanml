package fr.scanmylib.ui.components

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class ZoomableImageTest {
    @RunWith(Enclosed::class)
    class TheClampScaleFunction {
        class WhenPinchedBeyondEitherBound {
            private var smallestScale by Delegates.notNull<Float>()
            private var largestScale by Delegates.notNull<Float>()

            @Before
            fun pinch() {
                smallestScale = clampScale(PINCHED_IN)
                largestScale = clampScale(PINCHED_OUT)
            }

            @Test
            fun `should keep the zoom from 1× to 2½×`() {
                assertEquals(1f, smallestScale, TOLERANCE)
                assertEquals(2.5f, largestScale, TOLERANCE)
            }
        }
    }

    @RunWith(Enclosed::class)
    class ThePickScaleAfterDoubleTapFunction {
        class WhenTheImageIsNotZoomedIn {
            private var scale by Delegates.notNull<Float>()

            @Before
            fun doubleTap() {
                scale = pickScaleAfterDoubleTap(1f)
            }

            @Test
            fun `should zoom in to 2×`() {
                assertEquals(2f, scale, TOLERANCE)
            }
        }

        class WhenTheImageIsZoomedIn {
            private var scale by Delegates.notNull<Float>()

            @Before
            fun doubleTap() {
                scale = pickScaleAfterDoubleTap(ZOOMED_IN)
            }

            @Test
            fun `should zoom back out to 1×`() {
                assertEquals(1f, scale, TOLERANCE)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheClampOffsetFunction {
        class WhenAnImageThatFillsTheViewportIsPannedFarBeyondItsEdges {
            private var offset by Delegates.notNull<Offset>()

            @Before
            fun pan() {
                offset = clampOffset(FAR_AWAY, scale = 2f, viewport = PORTRAIT_VIEWPORT, imageSize = PORTRAIT_PAGE)
            }

            @Test
            fun `should stop at its edges, so that none enters the viewport`() {
                assertEquals(500f, offset.x, TOLERANCE)
                assertEquals(-1000f, offset.y, TOLERANCE)
            }
        }

        class WhenAnImageShorterThanTheViewportIsPannedUpAndDown {
            private var offset by Delegates.notNull<Offset>()

            @Before
            fun pan() {
                offset = clampOffset(FAR_AWAY, scale = 1.5f, viewport = PORTRAIT_VIEWPORT, imageSize = SQUARE_PAGE)
            }

            @Test
            fun `should keep it centered vertically, where it fits, and stop at its edges sideways`() {
                assertEquals(250f, offset.x, TOLERANCE)
                assertEquals(0f, offset.y, TOLERANCE)
            }
        }

        class WhenTheImageSizeIsNotKnownYet {
            private var offset by Delegates.notNull<Offset>()

            @Before
            fun pan() {
                offset = clampOffset(FAR_AWAY, scale = 2f, viewport = PORTRAIT_VIEWPORT, imageSize = Size.Unspecified)
            }

            @Test
            fun `should take the image as filling the viewport`() {
                assertEquals(500f, offset.x, TOLERANCE)
                assertEquals(-1000f, offset.y, TOLERANCE)
            }
        }
    }
}

private const val TOLERANCE = 0.0001f
private const val PINCHED_IN = 0.4f
private const val PINCHED_OUT = 4f
private const val ZOOMED_IN = 1.3f
private val FAR_AWAY = Offset(5_000f, -5_000f)
private val PORTRAIT_VIEWPORT = Size(1_000f, 2_000f)
private val PORTRAIT_PAGE = Size(500f, 1_000f)
private val SQUARE_PAGE = Size(800f, 800f)
