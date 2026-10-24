package fr.scanmylib.ui.document

import android.app.Dialog
import android.net.Uri
import android.view.KeyEvent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.click
import androidx.compose.ui.test.hasAnyDescendant
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasScrollToKeyAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performCustomAccessibilityActionWithLabel
import androidx.compose.ui.test.performScrollToKey
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeLeft
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.compose.LocalLifecycleOwner
import coil3.memory.MemoryCache
import coil3.request.ImageRequest
import com.github.takahirom.roborazzi.ExperimentalRoborazziApi
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureRoboImage
import com.github.takahirom.roborazzi.captureScreenRoboImage
import fr.scanmylib.MainDispatcherRule
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.library.Preparation
import fr.scanmylib.library.PreparationOutcome
import fr.scanmylib.library.StagedPage
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.isPoliteLiveRegion
import fr.scanmylib.ui.theme.ScanMyLibTheme
import java.io.File
import java.time.Instant
import kotlin.math.roundToInt
import kotlin.properties.Delegates
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowDialog

@RunWith(Enclosed::class)
class ReviewScreenTest {
    @RunWith(Enclosed::class)
    class TheReviewContentFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenFourPagesWaitToBeSent(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(FOUR_PAGES) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-pages-$theme.png")
            }

            @Test
            fun `should say how many pages wait to be sent, as a heading`() {
                compose.onNode(hasText(FOUR_PAGES_TO_SEND) and isHeading()).assertIsDisplayed()
            }

            @Test
            fun `should offer to send the four pages`() {
                compose.onNodeWithText(SEND_FOUR_PAGES).assertIsEnabled()
            }

            @Test
            fun `should read each page's place and number in words`() {
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO).assertIsDisplayed()
            }

            @Test
            fun `should let TalkBack enlarge a page, by name`() {
                assertEquals(ENLARGE, readClickLabel(compose, SECOND_PAGE_AUTO))
            }

            @Test
            fun `should let TalkBack remove each page, since no icon is there to tap`() {
                assertEquals(
                    FOUR_PAGES.stagedPages.size,
                    compose.onAllNodes(hasRemoveAction()).fetchSemanticsNodes().size,
                )
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenFourPagesWaitAndScrolledToTheEnd(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheEnd() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(FOUR_PAGES) } }
                compose.onNode(hasScrollToKeyAction()).performScrollToKey(DELETE_KEY)
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-pages-end-$theme.png")
            }

            @Test
            fun `should offer to add pages with the camera, from the gallery, or with another camera`() {
                compose.onNodeWithText(SCAN).assertIsDisplayed()
                compose.onNodeWithText(IMPORT).assertIsDisplayed()
                compose.onNodeWithText(SCAN_WITH).assertIsDisplayed()
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
        class WhenFourPagesWaitAndTheTextIsTwiceItsSizeAndScrolledToTheEnd(
            private val theme: String,
            private val dark: Boolean,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheEnd() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(FOUR_PAGES) } }
                compose.onNode(hasScrollToKeyAction()).performScrollToKey(DELETE_KEY)
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-pages-large-text-end-$theme.png")
            }

            @Test
            fun `should offer to add pages with the camera, from the gallery, or with another camera`() {
                compose.onNodeWithText(SCAN).assertIsDisplayed()
                compose.onNodeWithText(IMPORT).assertIsDisplayed()
                compose.onNodeWithText(SCAN_WITH).assertIsDisplayed()
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
        class WhenFourPagesWaitAndTheTextIsTwiceItsSize(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(FOUR_PAGES) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-pages-large-text-$theme.png")
            }

            @Test
            fun `should lay the pages out in two columns, as large as the text allows`() {
                assertEquals(2, countColumnsOfTheFirstTwoPages(compose))
            }

            @Test
            fun `should show the send button whole`() {
                assertTrue(isShownWhole(compose, SEND_FOUR_PAGES))
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPagesAreBeingImportedIntoAnEmptyRun(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(IMPORTING_FOUR_PHOTOS) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-preparing-$theme.png")
            }

            @Test
            fun `should count the photos being imported among the pages to send`() {
                compose.onNodeWithText(FOUR_PAGES_TO_SEND).assertIsDisplayed()
            }

            @Test
            fun `should show the progress of the import`() {
                compose.onNodeWithText(PROGRESS).assertIsDisplayed()
            }

            @Test
            fun `should not send before the photos are in, so that none is left out`() {
                compose.onNodeWithText(PREPARING).assertIsNotEnabled()
            }

            @Test
            fun `should let the import be canceled`() {
                compose.onNodeWithText(CANCEL).assertIsDisplayed()
            }

            companion object {
                private const val PROGRESS = "Preparing pages: 2 of 4"
                private const val PREPARING = "Preparing…"

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPagesAreBeingImportedIntoAnEmptyRunAndScrolledToTheEnd {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheEnd() {
                compose.setContent { ScanMyLibTheme { ReviewContentOf(IMPORTING_FOUR_PHOTOS) } }
                compose.onNode(hasScrollToKeyAction()).performScrollToKey(DELETE_KEY)
            }

            @Test
            fun `should not delete the pages while the photos come in, which would join the run once deleted`() {
                compose.onNodeWithText(DELETE_THESE_PAGES).assertIsNotEnabled()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenScannedPagesAreBeingCopied {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                val preparation = Preparation(done = 2, total = 4, imagesToAdd = 4, isCancellable = false)
                compose.setContent {
                    ScanMyLibTheme { ReviewContentOf(IMPORTING_FOUR_PHOTOS.copy(preparation = preparation)) }
                }
            }

            @Test
            fun `should not offer to cancel, since the scanned pages exist nowhere else`() {
                assertEquals(0, compose.onAllNodesWithText(CANCEL).fetchSemanticsNodes().size)
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPhotosWereSkipped(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(PHOTOS_SKIPPED) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-photos-skipped-$theme.png")
            }

            @Test
            fun `should say so from a region that stays, so that it is read out`() {
                compose.onNode(isPoliteLiveRegion() and hasAnyDescendant(hasText(TWO_SKIPPED, substring = true)))
                    .assertExists()
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPhotosWereSkippedAndOkIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var dismissals: MutableList<Unit>

            @Before
            fun tapOk() {
                dismissals = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { ReviewContentOf(PHOTOS_SKIPPED, onDismissOutcome = { dismissals += Unit }) }
                }
                compose.onNodeWithText(OK).performClick()
            }

            @Test
            fun `should dismiss the banner`() {
                assertEquals(1, dismissals.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheAppWasClosedWhileAddingPages {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES.copy(wasAddingInterrupted = true)) } }
            }

            @Test
            fun `should ask to check the pages, and to add those missing`() {
                compose.onNode(isPoliteLiveRegion() and hasAnyDescendant(hasText(ADDING_INTERRUPTED))).assertExists()
            }

            companion object {
                private const val ADDING_INTERRUPTED = "The app was closed while pages were being added: " +
                    "check the pages waiting to be sent, and add any missing ones again."
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPagesWereNumbered(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(NUMBERED_PAGES) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-numbers-$theme.png")
            }

            @Test
            fun `should read the number given to a page`() {
                compose.onNodeWithContentDescription(FIRST_PAGE_32).assertIsDisplayed()
            }

            @Test
            fun `should read the number a page follows on with, as such`() {
                compose.onNodeWithContentDescription(SECOND_PAGE_33_IN_SEQUENCE).assertIsDisplayed()
            }

            @Test
            fun `should read a page without a number as auto`() {
                compose.onNodeWithContentDescription(THIRD_PAGE_AUTO).assertIsDisplayed()
            }

            @Test
            fun `should let TalkBack change the number of each page, since the chip is not a node of its own`() {
                assertEquals(
                    NUMBERED_PAGES.stagedPages.size,
                    compose.onAllNodes(hasCustomAction(CHANGE_THE_NUMBER)).fetchSemanticsNodes().size,
                )
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
        class WhenPagesWereNumberedAndTheTextIsTwiceItsSize(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(NUMBERED_PAGES) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-numbers-large-text-$theme.png")
            }

            @Test
            fun `should keep the pages in two columns`() {
                assertEquals(2, countColumns(compose, FIRST_PAGE_32, SECOND_PAGE_33_IN_SEQUENCE))
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheNumberOfTheSecondPageIsTapped {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun tapIt() {
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES) } }
                tapTheNumberChip(compose, SECOND_PAGE_AUTO)
            }

            @Test
            fun `should open the number sheet of that page`() {
                compose.onNode(hasText(NUMBER_OF_PAGE_2) and isHeading()).assertIsDisplayed()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheChangeTheNumberActionOfTheSecondTileIsInvoked {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun invokeIt() {
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES) } }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
            }

            @Test
            fun `should open the number sheet of that page`() {
                compose.onNode(hasText(NUMBER_OF_PAGE_2) and isHeading()).assertIsDisplayed()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheNumberSheetOpensWhileThePcHasPages12To31And88To90 {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun openIt() {
                val scan = FOUR_PAGES.copy(scannedPages = listOf(12..31, 88..90))
                compose.setContent { ScanMyLibTheme { ReviewContentOf(scan) } }
                compose.onNodeWithContentDescription(FIRST_PAGE_AUTO)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
            }

            @Test
            fun `should suggest the first page missing between the PC's ranges`() {
                compose.onNodeWithText(SUGGESTION_32).assertIsDisplayed()
            }

            companion object {
                private const val SUGGESTION_32 = "Suggestion: 32"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenANumberIsDone {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var numbered: MutableList<NumberedPage>

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun numberTheSecondPage() {
                numbered = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        ReviewContentOf(
                            FOUR_PAGES,
                            onNumberPage = { page, number, nextPagesFollowOn ->
                                numbered += NumberedPage(page, number, nextPagesFollowOn)
                            },
                        )
                    }
                }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
                compose.onNode(hasSetTextAction()).performTextInput(TYPED_33)
                compose.onNodeWithText(DONE).performClick()
                compose.waitForIdle()
            }

            @Test
            fun `should number that page`() {
                assertEquals(
                    listOf(NumberedPage(FOUR_PAGES.stagedPages[1], number = 33, nextPagesFollowOn = true)),
                    numbered,
                )
            }

            @Test
            fun `should close the sheet`() {
                assertEquals(0, compose.onAllNodesWithText(NUMBER_OF_PAGE_2).fetchSemanticsNodes().size)
            }

            @Test
            fun `should give the focus back to the page`() {
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO).assertIsFocused()
            }

            companion object {
                private const val TYPED_33 = "33"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenDoneIsTappedTwice {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var numbered: MutableList<NumberedPage>

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun numberTheSecondPage() {
                numbered = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        ReviewContentOf(
                            FOUR_PAGES,
                            onNumberPage = { page, number, nextPagesFollowOn ->
                                numbered += NumberedPage(page, number, nextPagesFollowOn)
                            },
                        )
                    }
                }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
                compose.onNode(hasSetTextAction()).performTextInput(TYPED_33)
                compose.waitForIdle()
                compose.mainClock.autoAdvance = false
                compose.onNodeWithText(DONE).performClick()
                compose.onNodeWithText(DONE).performClick()
                compose.mainClock.autoAdvance = true
                compose.waitForIdle()
            }

            @Test
            fun `should number that page once`() {
                assertEquals(1, numbered.size)
            }

            @Test
            fun `should give the focus back to the page`() {
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO).assertIsFocused()
            }

            companion object {
                private const val TYPED_33 = "33"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenDoneIsTappedThenBackIsPressed {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var numbered: MutableList<NumberedPage>

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun numberTheSecondPage() {
                numbered = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        ReviewContentOf(
                            FOUR_PAGES,
                            onNumberPage = { page, number, nextPagesFollowOn ->
                                numbered += NumberedPage(page, number, nextPagesFollowOn)
                            },
                        )
                    }
                }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
                compose.onNode(hasSetTextAction()).performTextInput(TYPED_33)
                compose.waitForIdle()
                compose.mainClock.autoAdvance = false
                compose.onNodeWithText(DONE).performClick()
                compose.mainClock.advanceTimeByFrame()
                compose.runOnUiThread { pressBack(ShadowDialog.getLatestDialog()) }
                compose.mainClock.autoAdvance = true
                compose.waitForIdle()
            }

            @Test
            fun `should number that page once`() {
                assertEquals(1, numbered.size)
            }

            @Test
            fun `should give the focus back to the page`() {
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO).assertIsFocused()
            }

            companion object {
                private const val TYPED_33 = "33"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePageOfTheOpenNumberSheetLeavesTheRun {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun removeThePage() {
                var scan by mutableStateOf(FOUR_PAGES)
                compose.setContent { ScanMyLibTheme { ReviewContentOf(scan) } }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
                compose.waitForIdle()
                scan = SECOND_PAGE_REMOVED
                compose.waitForIdle()
            }

            @Test
            fun `should close the sheet, which would number another page`() {
                assertEquals(0, compose.onAllNodesWithText(NUMBER_OF_PAGE_2).fetchSemanticsNodes().size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenANumberIsTypedAndTheScreenIsRecreated {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun recreateTheScreen() {
                val restoration = StateRestorationTester(compose)
                restoration.setContent { ScanMyLibTheme { ReviewContentOf(rememberTheRunOnceRead(FOUR_PAGES)) } }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
                compose.onNode(hasSetTextAction()).performTextInput(TYPED_33)
                restoration.emulateSavedInstanceStateRestore()
            }

            @Test
            fun `should keep the sheet open with the number typed, once the run is read again`() {
                compose.onNode(hasSetTextAction()).assert(hasText(TYPED_33))
            }

            companion object {
                private const val TYPED_33 = "33"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenSendIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var sends: MutableList<Unit>

            @Before
            fun tapSend() {
                sends = mutableListOf()
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES, onSend = { sends += Unit }) } }
                compose.onNodeWithText(SEND_FOUR_PAGES).performClick()
            }

            @Test
            fun `should send the pages at once, with no question`() {
                assertEquals(1, sends.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPagesAreBeingSent {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheReview() {
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES.copy(sending = true)) } }
            }

            @Test
            fun `should not close, so that the send ends the review`() {
                compose.onNode(hasContentDescription(CLOSE)).assertIsNotEnabled()
            }

            @Test
            fun `should not let TalkBack remove a page that is being sent`() {
                assertEquals(0, compose.onAllNodes(hasRemoveAction()).fetchSemanticsNodes().size)
            }

            @Test
            fun `should not let TalkBack change the number of a page that is being sent`() {
                assertEquals(0, compose.onAllNodes(hasCustomAction(CHANGE_THE_NUMBER)).fetchSemanticsNodes().size)
            }

            companion object {
                private const val CLOSE = "Close and keep the pages"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheRemoveActionOfTheSecondTileIsInvoked {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var removedPages: MutableList<StagedPage>

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun removeTheSecondPage() {
                removedPages = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { ReviewContentOf(FOUR_PAGES, onRemovePage = { removedPages += it }) }
                }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO).performCustomAccessibilityActionWithLabel(REMOVE)
            }

            @Test
            fun `should remove that page`() {
                assertEquals(listOf(FOUR_PAGES.stagedPages[1]), removedPages)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheSecondTileIsRemoved {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun removeTheSecondPage() {
                compose.setContent {
                    var scan by remember { mutableStateOf(FOUR_PAGES) }
                    ScanMyLibTheme {
                        ReviewContentOf(
                            scan,
                            onRemovePage = { page ->
                                scan = scan.copy(stagedPages = scan.stagedPages - page, removedPage = page)
                            },
                        )
                    }
                }
                compose.onNodeWithContentDescription(SECOND_PAGE_AUTO).performCustomAccessibilityActionWithLabel(REMOVE)
            }

            @Test
            fun `should give the focus to the page that takes its place`() {
                compose.onNodeWithContentDescription(SECOND_OF_THREE_AUTO).assertIsFocused()
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenAPageIsRemoved(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun waitNineSecondsAndAHalf() {
                compose.mainClock.autoAdvance = false
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(SECOND_PAGE_REMOVED) } }
                compose.mainClock.advanceTimeBy(UNDO_STILL_OFFERED_MILLISECONDS)
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-page-removed-$theme.png")
            }

            @Test
            fun `should still offer to undo the removal`() {
                compose.onNodeWithText(UNDO).assertIsDisplayed()
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenAPageIsRemovedWhileAMessageShows {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun removeAPage() {
                compose.mainClock.autoAdvance = false
                compose.setContent {
                    val snackbarHostState = remember { SnackbarHostState() }
                    var scan by remember { mutableStateOf(FOUR_PAGES) }
                    LaunchedEffect(Unit) {
                        launch { snackbarHostState.showSnackbar(EARLIER_MESSAGE, duration = SnackbarDuration.Long) }
                        delay(SNACKBAR_ANIMATION_MILLISECONDS)
                        scan = SECOND_PAGE_REMOVED
                    }
                    ScanMyLibTheme { ReviewContentOf(scan, snackbarHostState = snackbarHostState) }
                }
                compose.mainClock.advanceTimeBy(MESSAGE_SHOWN_THEN_REPLACED_BY_UNDO_MILLISECONDS)
            }

            @Test
            fun `should offer the undo at once, in place of the message`() {
                compose.onNodeWithText(UNDO).assertIsDisplayed()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenAPageIsRemovedAndUndoIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var restoredPages: MutableList<StagedPage>

            @Before
            fun tapUndo() {
                restoredPages = mutableListOf()
                compose.mainClock.autoAdvance = false
                compose.setContent {
                    ScanMyLibTheme { ReviewContentOf(SECOND_PAGE_REMOVED, onRestorePage = { restoredPages += it }) }
                }
                compose.mainClock.advanceTimeBy(UNDO_STILL_OFFERED_MILLISECONDS)
                compose.onNodeWithText(UNDO).performClick()
                compose.mainClock.advanceTimeBy(SNACKBAR_ANIMATION_MILLISECONDS)
            }

            @Test
            fun `should put the page back`() {
                assertEquals(listOf(FOUR_PAGES.stagedPages[1]), restoredPages)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheUndoRunsOut {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var deletedPages: MutableList<StagedPage>

            @Before
            fun waitTenSeconds() {
                deletedPages = mutableListOf()
                compose.mainClock.autoAdvance = false
                compose.setContent {
                    ScanMyLibTheme {
                        ReviewContentOf(SECOND_PAGE_REMOVED, onDeleteRemovedPage = { deletedPages += it })
                    }
                }
                compose.mainClock.advanceTimeBy(UNDO_OFFERED_MILLISECONDS + SNACKBAR_ANIMATION_MILLISECONDS)
            }

            @Test
            fun `should delete the page for good`() {
                assertEquals(listOf(FOUR_PAGES.stagedPages[1]), deletedPages)
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheSecondPageIsEnlarged(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun enlargeIt() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(FOUR_PAGES) } }
                enlargeTheSecondPage(compose)
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-page-$theme.png")
            }

            @Test
            fun `should say which page it shows, as a heading`() {
                compose.onNode(hasText(PAGE_2_OF_4) and isHeading()).assertIsDisplayed()
            }

            @Test
            fun `should let TalkBack zoom in, since a pinch needs two fingers`() {
                compose.onNode(hasCustomAction(ZOOM_IN)).assertExists()
            }

            @Test
            fun `should offer to remove the page`() {
                compose.onNodeWithText(REMOVE).assertIsDisplayed()
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
        class WhenTheSecondPageIsEnlargedAndTheTextIsTwiceItsSize(
            private val theme: String,
            private val dark: Boolean,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun enlargeIt() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(FOUR_PAGES) } }
                enlargeTheSecondPage(compose)
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/review-page-large-text-$theme.png")
            }

            @Test
            fun `should show the remove button whole`() {
                assertTrue(isShownWhole(compose, REMOVE))
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheEnlargedPageIsSwiped {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun swipeIt() {
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES) } }
                enlargeTheSecondPage(compose)
                swipeToTheNextPage(compose)
            }

            @Test
            fun `should show the next page`() {
                compose.onNodeWithText(PAGE_3_OF_4).assertIsDisplayed()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenRemoveIsTappedInThePager {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var removedPages: MutableList<StagedPage>

            @Before
            fun removeTheSecondPage() {
                removedPages = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { ReviewContentOf(FOUR_PAGES, onRemovePage = { removedPages += it }) }
                }
                enlargeTheSecondPage(compose)
                compose.onNodeWithText(REMOVE).performClick()
            }

            @Test
            fun `should remove the page shown`() {
                assertEquals(listOf(FOUR_PAGES.stagedPages[1]), removedPages)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePageShownInThePagerLeavesTheRun {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun removeTheSecondPage() {
                compose.setContent {
                    var scan by remember { mutableStateOf(FOUR_PAGES) }
                    ScanMyLibTheme {
                        ReviewContentOf(
                            scan,
                            onRemovePage = { page ->
                                scan = scan.copy(stagedPages = scan.stagedPages - page, removedPage = page)
                            },
                        )
                    }
                }
                enlargeTheSecondPage(compose)
                compose.onNodeWithText(REMOVE).performClick()
            }

            @Test
            fun `should go on with the page that takes its place`() {
                compose.onNode(hasText(PAGE_2_OF_3) and isHeading()).assertIsDisplayed()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePagerIsClosedOnTheThirdPage {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun closeIt() {
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES) } }
                enlargeTheSecondPage(compose)
                swipeToTheNextPage(compose)
                compose.onNodeWithContentDescription(BACK).performClick()
            }

            @Test
            fun `should give the focus to the tile of the page last shown`() {
                compose.onNodeWithContentDescription(THIRD_PAGE_AUTO).assertIsFocused()
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenDeleteTheseFourPagesIsTapped(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @OptIn(ExperimentalRoborazziApi::class)
            @Before
            fun tapDelete() {
                compose.setContent { ScanMyLibTheme(dark = dark) { ReviewContentOf(FOUR_PAGES) } }
                tapDeleteTheseFourPages(compose)
                compose.waitForIdle()
                // The whole screen: the dialog has a window of its own.
                captureScreenRoboImage("build/outputs/roborazzi/review-delete-$theme.png")
            }

            @Test
            fun `should ask first, since the pages exist nowhere else`() {
                compose.onNodeWithText(DELETE_FOUR_PAGES).assertIsDisplayed()
            }

            companion object {
                private const val DELETE_FOUR_PAGES = "Delete 4 pages?"

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenDeleteTheseFourPagesIsTappedAndConfirmed {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var deletions: MutableList<Unit>

            @Before
            fun confirmTheDeletion() {
                deletions = mutableListOf()
                compose.setContent { ScanMyLibTheme { ReviewContentOf(FOUR_PAGES, onDelete = { deletions += Unit }) } }
                tapDeleteTheseFourPages(compose)
                compose.onNodeWithText(DELETE).performClick()
            }

            @Test
            fun `should delete the pages`() {
                assertEquals(1, deletions.size)
            }

            companion object {
                private const val DELETE = "Delete"
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheReviewScreenFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheRunEmptiesWhileTheScreenIsOnlyStarted {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private var closingCount by Delegates.notNull<Int>()
            private lateinit var reviewEnds: List<ReviewEnd?>

            @Before
            fun emptyTheRun() = runTest {
                val review = showTheReview(compose, stageThreePages(folder))
                emptyTheRunElsewhere(compose, review)
                closingCount = review.closingCount
                reviewEnds = listOf(review.run.viewModel.scanState.value.reviewEnd)
            }

            @Test
            fun `should stay open, so that a source's launcher stays registered`() {
                assertEquals(0, closingCount)
            }

            @Test
            fun `should not end the review yet`() {
                assertEquals(listOf(null), reviewEnds)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheRunEmptiesWhileTheScreenIsOnlyStartedAndTheScreenResumes {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private var closingCount by Delegates.notNull<Int>()

            @Before
            fun resume() = runTest {
                val review = showTheReview(compose, stageThreePages(folder))
                emptyTheRunElsewhere(compose, review)
                resumeTheScreen(compose, review)
                closingCount = review.closingCount
            }

            @Test
            fun `should close, as nothing is left to review`() {
                assertEquals(1, closingCount)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheReviewEndsWhileTheScreenIsOnlyStarted {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private lateinit var closingCounts: List<Int>

            @Before
            fun sendThenResume() = runTest {
                val review = showTheReview(compose, stageThreePages(folder))
                review.run.viewModel.send()
                review.run.viewModel.scanState.first { it.reviewEnd != null }
                compose.waitForIdle()
                val closingCountWhileStarted = review.closingCount
                resumeTheScreen(compose, review)
                closingCounts = listOf(closingCountWhileStarted, review.closingCount)
            }

            @Test
            fun `should leave only once resumed`() {
                assertEquals(listOf(0, 1), closingCounts)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenDoneIsTappedUnchangedOnAPageThatFollowsOn {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private lateinit var fileName: String
            private lateinit var fileNameAfter: String

            @OptIn(ExperimentalTestApi::class)
            @Before
            fun validateItUnchanged() = runTest {
                val run = stageThreePages(folder)
                run.viewModel.numberPage(run.stagedPages[0], FIRST_PAGE_NUMBER, nextPagesFollowOn = true)
                run.viewModel.scanState.first { it.stagedPages[0].numbering is PageNumbering.Given }
                showTheReview(compose, run)
                fileName = run.viewModel.scanState.value.stagedPages[1].file.name
                compose.onNodeWithContentDescription(SECOND_OF_THREE_33_IN_SEQUENCE)
                    .performCustomAccessibilityActionWithLabel(CHANGE_THE_NUMBER)
                compose.onNodeWithText(DONE).performClick()
                compose.waitForIdle()
                fileNameAfter = run.staging.pages(DOCUMENT_ID)[1].file.name
            }

            @Test
            fun `should keep it following on`() {
                compose.onNodeWithContentDescription(SECOND_OF_THREE_33_IN_SEQUENCE).assertIsDisplayed()
            }

            @Test
            fun `should keep its file as it was`() {
                assertEquals(fileName, fileNameAfter)
            }

            companion object {
                private const val SECOND_OF_THREE_33_IN_SEQUENCE = "Page 2 of 3, number 33, in sequence"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheScreenResumesFromASourceThatReturnedNothing {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private var closingCount by Delegates.notNull<Int>()

            @Before
            fun resumeFromTheSource() = runTest {
                val review = showTheReview(compose, stagePages(folder, pageCount = 1))
                openASourceAfterRemovingTheOnlyPage(compose, review)
                review.run.viewModel.onPagesScanned(emptyList())
                compose.waitForIdle()
                resumeTheScreen(compose, review)
                closingCount = review.closingCount
            }

            @Test
            fun `should close, as the source is over and nothing is left`() {
                assertEquals(1, closingCount)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenScannedPagesArriveBeforeTheScreenResumes {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private var closingCount by Delegates.notNull<Int>()

            @Before
            fun resumeWhileTheyAreCopied() = runTest {
                val copyGate = CompletableDeferred<Unit>()
                val run = stagePages(folder, pageCount = 1, addScannedPages = { _, _ -> copyGate.await() })
                val review = showTheReview(compose, run)
                openASourceAfterRemovingTheOnlyPage(compose, review)
                run.viewModel.onPagesScanned(listOf(Uri.parse(SCANNED_PAGE)))
                run.viewModel.onSourceClosed()
                run.viewModel.scanState.first { it.preparing }
                compose.waitForIdle()
                resumeTheScreen(compose, review)
                closingCount = review.closingCount
                copyGate.complete(Unit)
            }

            @Test
            fun `should stay open while they are copied`() {
                assertEquals(0, closingCount)
            }

            companion object {
                private const val SCANNED_PAGE = "file:///scanner/page-1.jpg"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenASourceIsAskedForWhileTheScreenIsOnlyStarted {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private var cameraOpeningCount by Delegates.notNull<Int>()

            @Before
            fun askForASource() = runTest {
                val review = showTheReview(compose, stageThreePages(folder), switchToSource = ScanSource.CAMERA)
                cameraOpeningCount = review.cameraOpeningCount
            }

            @Test
            fun `should not open it yet, since the screen's resume would end it`() {
                assertEquals(0, cameraOpeningCount)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenASourceIsAskedForAndTheScreenResumes {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            @get:Rule
            val folder = TemporaryFolder()

            @get:Rule
            val compose = createComposeRule()

            private var cameraOpeningCount by Delegates.notNull<Int>()
            private var isSourceOpen by Delegates.notNull<Boolean>()

            @Before
            fun resume() = runTest {
                val review = showTheReview(compose, stageThreePages(folder), switchToSource = ScanSource.CAMERA)
                resumeTheScreen(compose, review)
                cameraOpeningCount = review.cameraOpeningCount
                isSourceOpen = review.run.viewModel.scanState.value.isSourceOpen
            }

            @Test
            fun `should open it once`() {
                assertEquals(1, cameraOpeningCount)
            }

            @Test
            fun `should keep it open, so that the review stays for what it returns`() {
                assertTrue(isSourceOpen)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheBuildPageImageRequestFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenANumberedPageIsRenamed {
            private lateinit var request: ImageRequest

            @Before
            fun buildItsRequest() {
                request = buildPageImageRequest(RuntimeEnvironment.getApplication(), RENAMED_FILE, SHOWN_IMAGE_KEY)
            }

            @Test
            fun `should show the image of its old name until the new file is read, so that the tile never blinks`() {
                assertEquals(SHOWN_IMAGE_KEY, request.placeholderMemoryCacheKey)
            }

            companion object {
                private val RENAMED_FILE = File("page_h33c.jpg")
                private val SHOWN_IMAGE_KEY = MemoryCache.Key("page.jpg")
            }
        }
    }
}

private const val FOUR_PAGES_TO_SEND = "4 pages to send"
private const val SEND_FOUR_PAGES = "Send 4 pages"
private const val FIRST_PAGE_AUTO = "Page 1 of 4, number auto"
private const val SECOND_PAGE_AUTO = "Page 2 of 4, number auto"
private const val FIRST_PAGE_32 = "Page 1 of 4, number 32"
private const val SECOND_PAGE_33_IN_SEQUENCE = "Page 2 of 4, number 33, in sequence"
private const val CHANGE_THE_NUMBER = "Change the number"
private const val NUMBER_OF_PAGE_2 = "Number of page 2"
private const val DONE = "Done"
private const val FIRST_PAGE_NUMBER = 32
private const val ENLARGE = "Enlarge"
private const val REMOVE = "Remove"
private const val CANCEL = "Cancel"
private const val OK = "OK"
private const val TWO_SKIPPED = "2 photos"
private const val DELETE_THESE_PAGES = "Delete these pages"
private const val DELETE_KEY = "delete"
private const val SCAN = "Scan"
private const val IMPORT = "Import"
private const val SCAN_WITH = "Scan with…"
private const val SECOND_OF_THREE_AUTO = "Page 2 of 3, number auto"
private const val THIRD_PAGE_AUTO = "Page 3 of 4, number auto"
private const val PAGE_2_OF_4 = "Page 2 of 4"
private const val PAGE_3_OF_4 = "Page 3 of 4"
private const val PAGE_2_OF_3 = "Page 2 of 3"
private const val ZOOM_IN = "Zoom in"
private const val BACK = "Back"
private const val UNDO = "Undo"
private const val EARLIER_MESSAGE = "Settings not saved"
private const val UNDO_STILL_OFFERED_MILLISECONDS = 9_500L
private const val UNDO_OFFERED_MILLISECONDS = 10_000L
private const val SNACKBAR_ANIMATION_MILLISECONDS = 500L

// The message's two animations, then the undo's.
private const val MESSAGE_SHOWN_THEN_REPLACED_BY_UNDO_MILLISECONDS = 3 * SNACKBAR_ANIMATION_MILLISECONDS

private val THEMES = listOf(arrayOf<Any>("light", false), arrayOf<Any>("dark", true))

private val PAPER = Color(0xFFF3EEDF)
private const val PAGE_WIDTH_PIXELS = 210f
private const val PAGE_HEIGHT_PIXELS = 297f

private val FOUR_PAGES = ScanUiState(
    defaultCamera = ScanSource.GOOGLE_SCANNER,
    loaded = true,
    isRunRead = true,
    stagedPages = (1..4).map { position ->
        StagedPage(
            File("/staging/run/$position.jpg"),
            seq = position,
            capturedAt = Instant.parse("2026-10-12T08:00:00Z").plusSeconds(position.toLong()),
        )
    },
)

private val NUMBERED_PAGES = FOUR_PAGES.copy(
    stagedPages = FOUR_PAGES.stagedPages.zip(
        listOf(
            PageNumbering.Given(FIRST_PAGE_NUMBER, nextPagesFollowOn = true),
            PageNumbering.NotGiven,
            PageNumbering.Cleared,
            PageNumbering.NotGiven,
        ),
    ) { page, numbering -> page.copy(numbering = numbering) },
)

private val IMPORTING_FOUR_PHOTOS = FOUR_PAGES.copy(
    stagedPages = emptyList(),
    preparation = Preparation(done = 2, total = 4, imagesToAdd = 4, isCancellable = true),
)

private val SECOND_PAGE_REMOVED = FOUR_PAGES.copy(
    stagedPages = FOUR_PAGES.stagedPages - FOUR_PAGES.stagedPages[1],
    removedPage = FOUR_PAGES.stagedPages[1],
)

private val PHOTOS_SKIPPED =
    FOUR_PAGES.copy(outcome = PreparationOutcome.PhotosSkipped(unsupported = 2, tooLarge = 0, unreadable = 0))

private fun hasRemoveAction(): SemanticsMatcher = hasCustomAction(REMOVE)

private fun hasCustomAction(label: String): SemanticsMatcher = SemanticsMatcher("has the action $label") { node ->
    node.config.getOrNull(SemanticsActions.CustomActions).orEmpty().any { it.label == label }
}

private fun enlargeTheSecondPage(screen: SemanticsNodeInteractionsProvider) {
    screen.onNodeWithContentDescription(SECOND_PAGE_AUTO).performClick()
}

private fun swipeToTheNextPage(screen: SemanticsNodeInteractionsProvider) {
    screen.onRoot().performTouchInput { swipeLeft() }
}

/** A blank page in portrait, of the size of a page image, drawn without a bitmap, which needs native graphics. */
private class BlankPage : Painter() {
    override val intrinsicSize = Size(PAGE_WIDTH_PIXELS, PAGE_HEIGHT_PIXELS)

    override fun DrawScope.onDraw() {
        drawRect(PAPER)
    }
}

private fun readClickLabel(screen: SemanticsNodeInteractionsProvider, description: String): String? =
    screen.onNodeWithContentDescription(description).fetchSemanticsNode().config
        .getOrNull(SemanticsActions.OnClick)?.label

private fun countColumnsOfTheFirstTwoPages(screen: SemanticsNodeInteractionsProvider): Int =
    countColumns(screen, FIRST_PAGE_AUTO, SECOND_PAGE_AUTO)

private fun countColumns(screen: SemanticsNodeInteractionsProvider, vararg pages: String): Int = pages.map { page ->
    screen.onNodeWithContentDescription(page).fetchSemanticsNode().positionInRoot.x.roundToInt()
}.toSet().size

/** A tap on the chip, at the start of the strip under the image: inside the tile's one node, a pointer target only. */
private fun tapTheNumberChip(screen: SemanticsNodeInteractionsProvider, page: String) {
    screen.onNodeWithContentDescription(page).performTouchInput {
        val chipCenterInset = STRIP_HEIGHT.toPx() / 2
        click(Offset(chipCenterInset, height - chipCenterInset))
    }
}

/** What the review asked to number. */
private data class NumberedPage(val page: StagedPage, val number: Int?, val nextPagesFollowOn: Boolean)

private val STRIP_HEIGHT = 48.dp

private fun isShownWhole(screen: SemanticsNodeInteractionsProvider, text: String): Boolean {
    val root = screen.onRoot().fetchSemanticsNode().boundsInRoot
    val bounds = screen.onNodeWithText(text).fetchSemanticsNode().boundsInRoot
    return bounds.height > 0 && root.contains(bounds.topLeft) && bounds.bottom <= root.bottom &&
        bounds.right <= root.right
}

private fun tapDeleteTheseFourPages(screen: SemanticsNodeInteractionsProvider) {
    screen.onNode(hasScrollToKeyAction()).performScrollToKey(DELETE_KEY)
    screen.onNodeWithText(DELETE_THESE_PAGES).performClick()
}

/** The lifecycle of the review's entry, which a test moves by hand. */
private class ScreenLifecycle(state: Lifecycle.State) : LifecycleOwner {
    private val registry = LifecycleRegistry.createUnsafe(this).apply { currentState = state }

    override val lifecycle: Lifecycle get() = registry

    fun moveTo(state: Lifecycle.State) {
        registry.currentState = state
    }
}

/** The review of [run], drawn while its entry is only started, as under a source in front of it. */
private class ReviewOnScreen(val run: RunUnderReview, val lifecycle: ScreenLifecycle) {
    var closingCount = 0
    var cameraOpeningCount = 0
}

private fun showTheReview(
    compose: ComposeContentTestRule,
    run: RunUnderReview,
    switchToSource: ScanSource? = null,
): ReviewOnScreen {
    val review = ReviewOnScreen(run, ScreenLifecycle(Lifecycle.State.STARTED))
    var sourceToSwitchTo by mutableStateOf(switchToSource)
    compose.setContent {
        CompositionLocalProvider(LocalLifecycleOwner provides review.lifecycle) {
            ScanMyLibTheme {
                ReviewScreen(
                    onClose = { review.closingCount++ },
                    onOpenCamera = { review.cameraOpeningCount++ },
                    switchToSource = sourceToSwitchTo,
                    onSwitchHandled = { sourceToSwitchTo = null },
                    viewModel = run.viewModel,
                )
            }
        }
    }
    compose.waitForIdle()
    return review
}

/** The run's pages deleted by something else than the review, which the review sees go. */
private suspend fun emptyTheRunElsewhere(compose: ComposeContentTestRule, review: ReviewOnScreen) {
    review.run.staging.discard(DOCUMENT_ID)
    review.run.viewModel.scanState.first { it.hasNothingToReview }
    compose.waitForIdle()
}

/** The only page removed, then a source opened, which makes the removal final: the run is empty. */
private suspend fun openASourceAfterRemovingTheOnlyPage(compose: ComposeContentTestRule, review: ReviewOnScreen) {
    val viewModel = review.run.viewModel
    viewModel.removePage(review.run.stagedPages.single())
    viewModel.scanState.first { it.removedPage != null }
    viewModel.onAddingPages()
    viewModel.scanState.first { it.stagedPages.isEmpty() && it.removedPage == null && it.isSourceOpen }
    compose.waitForIdle()
}

@Composable
private fun rememberTheRunOnceRead(run: ScanUiState): ScanUiState {
    var scan by remember { mutableStateOf(ScanUiState()) }
    LaunchedEffect(Unit) { scan = run }
    return scan
}

private fun pressBack(dialog: Dialog) {
    dialog.dispatchKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_BACK))
    dialog.dispatchKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_BACK))
}

private fun resumeTheScreen(compose: ComposeContentTestRule, review: ReviewOnScreen) {
    compose.runOnIdle { review.lifecycle.moveTo(Lifecycle.State.RESUMED) }
    compose.waitForIdle()
}

@Composable
private fun ReviewContentOf(
    scan: ScanUiState,
    onSend: () -> Unit = {},
    onDelete: () -> Unit = {},
    onRemovePage: (StagedPage) -> Unit = {},
    onRestorePage: (StagedPage) -> Unit = {},
    onDeleteRemovedPage: (StagedPage) -> Unit = {},
    onDismissOutcome: () -> Unit = {},
    onNumberPage: (StagedPage, Int?, Boolean) -> Unit = { _, _, _ -> },
    snackbarHostState: SnackbarHostState = remember { SnackbarHostState() },
) {
    ReviewContent(
        scan = scan,
        snackbarHostState = snackbarHostState,
        onClose = {},
        onNumberPage = onNumberPage,
        onCancelPreparation = {},
        onDismissOutcome = onDismissOutcome,
        onDismissAddingInterrupted = {},
        onRemovePage = onRemovePage,
        onRestorePage = onRestorePage,
        onDeleteRemovedPage = onDeleteRemovedPage,
        onScan = {},
        onImport = {},
        onChooseCamera = {},
        onSend = onSend,
        onDelete = onDelete,
        pageImage = { _, modifier -> Box(modifier.background(PAPER)) },
        pagePainter = { _, _, _ -> remember { BlankPage() } },
    )
}
