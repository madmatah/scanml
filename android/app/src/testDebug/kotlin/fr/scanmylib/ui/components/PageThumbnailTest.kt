package fr.scanmylib.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toPixelMap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.library.PageLabel
import fr.scanmylib.ui.hasRole
import fr.scanmylib.ui.theme.ScanMyLibTheme
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(Enclosed::class)
class PageThumbnailTest {
    @RunWith(Enclosed::class)
    class ThePageThumbnailFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThePageIsNumbered {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePage() {
                compose.setContent { ScanMyLibTheme { PageThumbnailOf(PAGE_TWELVE, FAILED_IN_FULL, badge = FAILED) } }
            }

            @Test
            fun `should read its number in words, with its full status`() {
                compose.onAllNodesWithContentDescription("Page 12, $FAILED_IN_FULL").assertCountEquals(1)
            }

            @Test
            fun `should not read the words drawn over its image as well`() {
                compose.onAllNodesWithText("p. 12").assertCountEquals(0)
            }

            @Test
            fun `should read as a button`() {
                compose.onNodeWithContentDescription("Page 12, $FAILED_IN_FULL").assert(hasRole(Role.Button))
            }

            @Test
            fun `should say that a tap opens the page`() {
                val page = compose.onNodeWithContentDescription("Page 12, $FAILED_IN_FULL").fetchSemanticsNode()
                assertEquals(OPEN_THE_PAGE, page.config.getOrNull(SemanticsActions.OnClick)?.label)
            }

            companion object {
                private const val FAILED_IN_FULL = "Couldn’t read the text"
                private const val OPEN_THE_PAGE = "Open the page"
                private val FAILED = PageBadge(R.string.page_badge_failed, R.drawable.ic_error, StatusTone.FAILURE)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThePageIsASpread {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePage() {
                compose.setContent { ScanMyLibTheme { PageThumbnailOf(PageLabel.Spread("42", "43"), TEXT_READY) } }
            }

            @Test
            fun `should read both of its pages`() {
                compose.onAllNodesWithContentDescription("Pages 42 and 43, $TEXT_READY").assertCountEquals(1)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThePageIsUnnumbered {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePage() {
                compose.setContent { ScanMyLibTheme { PageThumbnailOf(PageLabel.Unnumbered, TEXT_READY) } }
            }

            @Test
            fun `should say it has no number`() {
                compose.onAllNodesWithContentDescription("Unnumbered page, $TEXT_READY").assertCountEquals(1)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenThePageIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var openings: MutableList<Unit>

            @Before
            fun tapThePage() {
                openings = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { PageThumbnailOf(PAGE_TWELVE, TEXT_READY, onClick = { openings += Unit }) }
                }
                compose.onNodeWithContentDescription("Page 12, $TEXT_READY").performClick()
            }

            @Test
            fun `should open it`() {
                assertEquals(1, openings.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenAnAccessibilityServiceOpensThePage {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var openings: MutableList<Unit>

            @Before
            fun performTheOpening() {
                openings = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { PageThumbnailOf(PAGE_TWELVE, TEXT_READY, onClick = { openings += Unit }) }
                }
                compose.onNodeWithContentDescription("Page 12, $TEXT_READY")
                    .performSemanticsAction(SemanticsActions.OnClick)
            }

            @Test
            fun `should open it once`() {
                assertEquals(1, openings.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenOnePageIsSetAsideAndAnotherIsNot {
            @get:Rule
            val compose = createComposeRule()

            private var setAsideRed by Delegates.notNull<Float>()
            private var keptRed by Delegates.notNull<Float>()

            @Before
            fun drawBothPages() {
                compose.setContent {
                    ScanMyLibTheme(dark = false) {
                        Row(Modifier.background(Color.White)) {
                            BlackPage(SET_ASIDE, isSetAside = true)
                            BlackPage(KEPT, isSetAside = false)
                        }
                    }
                }
                setAsideRed = readCenterRed(SET_ASIDE)
                keptRed = readCenterRed(KEPT)
            }

            @Test
            fun `should show the image of the page set aside at half its strength`() {
                assertEquals(HALF, setAsideRed - keptRed, TOLERANCE)
            }

            private fun readCenterRed(tag: String): Float {
                val pixels = compose.onNodeWithTag(tag).captureToImage().toPixelMap()
                return pixels[pixels.width / 2, pixels.height / 2].red
            }

            companion object {
                private const val SET_ASIDE = "set aside"
                private const val KEPT = "kept"
                private const val HALF = 0.5f
                private const val TOLERANCE = 0.05f
            }
        }
    }
}

private const val TEXT_READY = "Text ready"
private val PAGE_TWELVE = PageLabel.OnePage("12")

@Composable
private fun PageThumbnailOf(label: PageLabel, status: String, badge: PageBadge? = null, onClick: () -> Unit = {}) {
    PageThumbnail(label = label, status = status, onClick = onClick, badge = badge, image = {})
}

@Composable
private fun BlackPage(tag: String, isSetAside: Boolean) {
    Box(Modifier.testTag(tag).width(PAGE_WIDTH)) {
        PageThumbnail(
            label = PAGE_TWELVE,
            status = TEXT_READY,
            onClick = {},
            isSetAside = isSetAside,
            image = { modifier -> Box(modifier.background(Color.Black)) },
        )
    }
}

private val PAGE_WIDTH = 120.dp
