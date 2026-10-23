package fr.scanmylib.ui.document

import androidx.compose.ui.unit.IntSize
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class StagedPagePagerTest {
    @RunWith(Enclosed::class)
    class ThePickDecodeSizeFunction {
        class WhenThePageIsNotZoomedIn {
            private lateinit var decodeSizes: List<IntSize?>

            @Before
            fun pickTheSize() {
                decodeSizes = listOf(pickDecodeSize(VIEWPORT, isZoomedIn = false))
            }

            @Test
            fun `should decode at the viewport's size until zoomed in, so that a page holds no more than it shows`() {
                assertEquals(listOf(VIEWPORT), decodeSizes)
            }
        }

        class WhenThePageIsZoomedIn {
            private lateinit var decodeSizes: List<IntSize?>

            @Before
            fun pickTheSize() {
                decodeSizes = listOf(pickDecodeSize(VIEWPORT, isZoomedIn = true))
            }

            @Test
            fun `should decode at twice the viewport, so that the page stays sharp at 2x`() {
                assertEquals(listOf(IntSize(2_160, 4_000)), decodeSizes)
            }
        }

        class WhenTheViewportIsEmpty {
            private lateinit var decodeSizes: List<IntSize?>

            @Before
            fun pickTheSize() {
                decodeSizes = listOf(pickDecodeSize(IntSize(0, 2_000), isZoomedIn = true))
            }

            @Test
            fun `should decode nothing, since Coil refuses a size of 0`() {
                assertEquals(listOf(null), decodeSizes)
            }
        }
    }
}

private val VIEWPORT = IntSize(1_080, 2_000)
