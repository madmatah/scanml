package fr.scanmylib.ui.document

import androidx.compose.runtime.Composable
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.isToggleable
import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performImeAction
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.text.TextRange
import com.github.takahirom.roborazzi.ExperimentalRoborazziApi
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureScreenRoboImage
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.ui.isShownWholeInItsWindow
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
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(Enclosed::class)
class PageNumberSheetTest {
    @RunWith(Enclosed::class)
    class ThePageNumberSheetFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItOpensOnAPageWithoutANumber(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalRoborazziApi::class)
            @Before
            fun openIt() {
                compose.setContent { ScanMyLibTheme(dark = dark) { SheetOf(FOUR_UNNUMBERED_PAGES, SECOND_PAGE) } }
                compose.waitForIdle()
                // The whole screen: the sheet has a window of its own.
                captureScreenRoboImage("build/outputs/roborazzi/number-sheet-$theme.png")
            }

            @Test
            fun `should say which page it numbers, as a heading`() {
                compose.onNode(hasText(NUMBER_OF_PAGE_2) and isHeading()).assertIsDisplayed()
            }

            @Test
            fun `should put the focus in the field, for the keyboard to open at once`() {
                compose.onNode(hasSetTextAction()).assertIsFocused()
            }

            @Test
            fun `should offer no Clear, since the page has no number`() {
                assertEquals(0, compose.onAllNodesWithText(CLEAR).fetchSemanticsNodes().size)
            }

            @Test
            fun `should not let the next pages follow on before a number is typed`() {
                compose.onNode(isToggleable()).assertIsNotEnabled()
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone, fontScale = 2f)
        class When32IsTypedOnTheFirstOfFourPagesAndTheTextIsTwiceItsSize(
            private val theme: String,
            private val dark: Boolean,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalRoborazziApi::class)
            @Before
            fun typeANumber() {
                compose.setContent { ScanMyLibTheme(dark = dark) { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE) } }
                compose.onNode(hasSetTextAction()).performTextInput(TYPED_32)
                compose.waitForIdle()
                captureScreenRoboImage("build/outputs/roborazzi/number-sheet-large-text-$theme.png")
            }

            @Test
            fun `should show Done whole`() {
                assertTrue(isShownWholeInItsWindow(compose, DONE))
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class When32IsTypedOnTheFirstOfFourPages {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun typeIt() {
                compose.setContent { ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE) } }
                type32(compose)
            }

            @Test
            fun `should say the numbers the next pages get`() {
                compose.onNodeWithText(PAGES_2_TO_4_FROM_33, substring = true).assertIsDisplayed()
            }

            companion object {
                private const val PAGES_2_TO_4_FROM_33 = "Pages 2 to 4: 33 to 35"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class When32IsTypedOnTheFirstOfFourPagesAndDoneIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var validations: MutableList<Validation>

            @Before
            fun tapDone() {
                validations = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE, onDone = recordIn(validations)) }
                }
                type32(compose)
                tapDone(compose)
            }

            @Test
            fun `should give the page 32, with the next pages following on`() {
                assertEquals(listOf(Validation(NUMBER_32, nextPagesFollowOn = true)), validations)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class When32IsTypedOnTheFirstOfFourPagesAndTheSwitchIsTurnedOff {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun turnTheSwitchOff() {
                compose.setContent { ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE) } }
                type32(compose)
                turnTheSwitchOff(compose)
            }

            @Test
            fun `should say that the next pages get no number`() {
                compose.onNodeWithText(PAGES_2_TO_4_AUTO, substring = true).assertIsDisplayed()
            }

            companion object {
                private const val PAGES_2_TO_4_AUTO = "Pages 2 to 4: Auto"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class When32IsTypedOnTheFirstOfFourPagesAndTheSwitchIsTurnedOffAndDoneIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var validations: MutableList<Validation>

            @Before
            fun tapDone() {
                validations = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE, onDone = recordIn(validations)) }
                }
                type32(compose)
                turnTheSwitchOff(compose)
                tapDone(compose)
            }

            @Test
            fun `should give the page 32 alone`() {
                assertEquals(listOf(Validation(NUMBER_32, nextPagesFollowOn = false)), validations)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class When9998IsTypedOnTheFirstOfFourPages {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var liveLine: List<String>

            @Before
            fun typeIt() {
                compose.setContent { ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE) } }
                compose.onNode(hasSetTextAction()).performTextInput(TYPED_9998)
                liveLine = readTheSwitchTexts(compose).drop(1)
            }

            @Test
            fun `should say which pages get a number and which, past 9999, get none`() {
                assertEquals(listOf("Page 2: 9999\nPages 3 to 4: Auto"), liveLine)
            }

            companion object {
                private const val TYPED_9998 = "9998"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class When0IsTyped {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun typeIt() {
                compose.setContent { ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE) } }
                compose.onNode(hasSetTextAction()).performTextInput(TYPED_0)
            }

            @Test
            fun `should say which numbers it takes`() {
                compose.onNodeWithText(FROM_1_TO_9999, substring = true).assertIsDisplayed()
            }

            @Test
            fun `should not let it be validated, since no page is numbered 0`() {
                compose.onNodeWithText(DONE).assertIsNotEnabled()
            }

            companion object {
                private const val TYPED_0 = "0"
                private const val FROM_1_TO_9999 = "A number from 1 to 9999"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItOpensOnAGivenPage {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var fieldText: String
            private var selection by Delegates.notNull<TextRange>()

            @Before
            fun openIt() {
                compose.setContent { ScanMyLibTheme { SheetOf(FOUR_PAGES_FROM_32, FIRST_PAGE) } }
                fieldText = readTheField(compose)
                selection = readTheSelection(compose)
            }

            @Test
            fun `should start from its number`() {
                assertEquals(TYPED_32, fieldText)
            }

            @Test
            fun `should put the cursor after it, so that typing goes on from it`() {
                assertEquals(TextRange(TYPED_32.length), selection)
            }

            @Test
            fun `should offer to clear it`() {
                compose.onNodeWithText(CLEAR).assertIsDisplayed()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItOpensOnAGivenPageAndClearIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var validations: MutableList<Validation>

            @Before
            fun tapClear() {
                validations = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { SheetOf(FOUR_PAGES_FROM_32, FIRST_PAGE, onDone = recordIn(validations)) }
                }
                compose.onNodeWithText(CLEAR).performClick()
                compose.waitForIdle()
            }

            @Test
            fun `should give the page no number`() {
                assertEquals(listOf(Validation(number = null, nextPagesFollowOn = true)), validations)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItOpensOnAPageThatFollowsOn {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var fieldText: String

            @Before
            fun openIt() {
                compose.setContent { ScanMyLibTheme { SheetOf(FOUR_PAGES_FROM_32, SECOND_PAGE) } }
                fieldText = readTheField(compose)
            }

            @Test
            fun `should start from the number it follows on with`() {
                assertEquals(TYPED_33, fieldText)
            }

            companion object {
                private const val TYPED_33 = "33"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItOpensOnTheLastPage {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var switchTexts: List<String>

            @Before
            fun typeANumber() {
                compose.setContent { ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, LAST_PAGE) } }
                type32(compose)
                switchTexts = readTheSwitchTexts(compose)
            }

            @Test
            fun `should say nothing of the next pages, since there are none`() {
                assertEquals(listOf(NEXT_PAGES_IN_SEQUENCE), switchTexts)
            }

            companion object {
                private const val LAST_PAGE = 3
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheKeyboardsDoneKeyIsPressed {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var validations: MutableList<Validation>

            @Before
            fun pressDone() {
                validations = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { SheetOf(FOUR_UNNUMBERED_PAGES, FIRST_PAGE, onDone = recordIn(validations)) }
                }
                type32(compose)
                compose.onNode(hasSetTextAction()).performImeAction()
                compose.waitForIdle()
            }

            @Test
            fun `should validate the number, as Done does`() {
                assertEquals(listOf(Validation(NUMBER_32, nextPagesFollowOn = true)), validations)
            }
        }
    }
}

private const val FIRST_PAGE = 0
private const val SECOND_PAGE = 1
private const val NUMBER_32 = 32
private const val TYPED_32 = "32"
private const val NUMBER_OF_PAGE_2 = "Number of page 2"
private const val NEXT_PAGES_IN_SEQUENCE = "Number the following pages in sequence"
private const val CLEAR = "Clear"
private const val DONE = "Done"

private val THEMES = listOf(arrayOf<Any>("light", false), arrayOf<Any>("dark", true))

private val FOUR_UNNUMBERED_PAGES = List(4) { PageNumbering.NotGiven }
private val FOUR_PAGES_FROM_32 = listOf(PageNumbering.Given(NUMBER_32, nextPagesFollowOn = true)) +
    List(3) { PageNumbering.NotGiven }

private data class Validation(val number: Int?, val nextPagesFollowOn: Boolean)

private fun recordIn(validations: MutableList<Validation>): (Int?, Boolean) -> Unit =
    { number, nextPagesFollowOn -> validations += Validation(number, nextPagesFollowOn) }

@Composable
private fun SheetOf(
    numberings: List<PageNumbering>,
    index: Int,
    onDone: (number: Int?, nextPagesFollowOn: Boolean) -> Unit = { _, _ -> },
) {
    PageNumberSheet(numberings = numberings, index = index, onDone = onDone, onDismiss = {})
}

private fun type32(screen: SemanticsNodeInteractionsProvider) {
    screen.onNode(hasSetTextAction()).performTextInput(TYPED_32)
}

private fun turnTheSwitchOff(screen: SemanticsNodeInteractionsProvider) {
    screen.onNode(isToggleable()).performClick()
}

private fun tapDone(compose: ComposeContentTestRule) {
    compose.onNodeWithText(DONE).performClick()
    compose.waitForIdle()
}

private fun readTheSwitchTexts(screen: SemanticsNodeInteractionsProvider): List<String> =
    screen.onNode(isToggleable()).fetchSemanticsNode().config.getOrNull(SemanticsProperties.Text).orEmpty()
        .map { it.text }

private fun readTheField(screen: SemanticsNodeInteractionsProvider): String =
    screen.onNode(hasSetTextAction()).fetchSemanticsNode().config.getOrNull(SemanticsProperties.EditableText)
        ?.text.orEmpty()

private fun readTheSelection(screen: SemanticsNodeInteractionsProvider): TextRange =
    screen.onNode(hasSetTextAction()).fetchSemanticsNode().config[SemanticsProperties.TextSelectionRange]
