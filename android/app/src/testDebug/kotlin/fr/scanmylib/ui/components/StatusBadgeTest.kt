package fr.scanmylib.ui.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.ui.theme.ScanMyLibTheme
import kotlin.properties.Delegates
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(Enclosed::class)
class StatusBadgeTest {
    @RunWith(Enclosed::class)
    class TheStatusBadgeFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsTextIsShortened {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheBadge() {
                compose.setContent {
                    ScanMyLibTheme {
                        StatusBadge(SHORT_TEXT, R.drawable.ic_error, StatusTone.FAILURE, fullText = FULL_TEXT)
                    }
                }
            }

            @Test
            fun `should give its full text to accessibility services`() {
                compose.onAllNodesWithContentDescription(FULL_TEXT).assertCountEquals(1)
            }

            @Test
            fun `should not read its short text as well`() {
                compose.onAllNodesWithText(SHORT_TEXT).assertCountEquals(0)
            }

            companion object {
                private const val SHORT_TEXT = "Failed"
                private const val FULL_TEXT = "Couldn’t read the text"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36])
        class WhenItsTextIsTooLongForOneLine {
            @get:Rule
            val compose = createComposeRule()

            private var oneLineHeightPixels by Delegates.notNull<Int>()
            private var longTextHeightPixels by Delegates.notNull<Int>()

            @Before
            fun drawAShortAndALongBadge() {
                compose.setContent {
                    ScanMyLibTheme {
                        Column {
                            NarrowBadge(SHORT_TEXT_TAG, SHORT_TEXT)
                            NarrowBadge(LONG_TEXT_TAG, LONG_TEXT)
                        }
                    }
                }
                oneLineHeightPixels = compose.onNodeWithTag(SHORT_TEXT_TAG).fetchSemanticsNode().size.height
                longTextHeightPixels = compose.onNodeWithTag(LONG_TEXT_TAG).fetchSemanticsNode().size.height
            }

            @Test
            fun `should wrap it on a second line rather than cut it`() {
                assertTrue(
                    "$longTextHeightPixels against $oneLineHeightPixels",
                    longTextHeightPixels >= oneLineHeightPixels * 3 / 2,
                )
            }

            companion object {
                private const val SHORT_TEXT_TAG = "short text"
                private const val LONG_TEXT_TAG = "long text"
                private const val SHORT_TEXT = "Failed"
                private const val LONG_TEXT = "Waiting to be read"
            }
        }
    }
}

@Composable
private fun NarrowBadge(tag: String, text: String) {
    Box(Modifier.testTag(tag).width(NARROW_WIDTH)) {
        StatusBadge(text, R.drawable.ic_schedule, StatusTone.NEUTRAL)
    }
}

private val NARROW_WIDTH = 96.dp
