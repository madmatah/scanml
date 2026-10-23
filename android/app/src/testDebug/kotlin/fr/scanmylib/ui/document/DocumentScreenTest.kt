package fr.scanmylib.ui.document

import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.hasAnyDescendant
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasScrollToKeyAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToKey
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureRoboImage
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadFailure
import fr.scanmylib.db.UploadState
import fr.scanmylib.library.DocumentPages
import fr.scanmylib.library.Preparation
import fr.scanmylib.library.PreparationOutcome
import fr.scanmylib.library.StagedPage
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.MAX_TEXT_FROM_PC_GRAPHEMES
import fr.scanmylib.ui.isPoliteLiveRegion
import fr.scanmylib.ui.readHeadingsFromTheTop
import fr.scanmylib.ui.theme.ScanMyLibTheme
import java.io.File
import java.time.Instant
import kotlin.math.roundToInt
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
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
class DocumentScreenTest {
    @RunWith(Enclosed::class)
    class TheDocumentContentFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItsPagesAreBeingRead(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent { ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/document-reading-$theme.png")
            }

            @Test
            fun `should show the pages on the PC by their numbers`() {
                compose.onNodeWithContentDescription(FIRST_READ_PAGE).assertIsDisplayed()
            }

            @Test
            fun `should show the pages that wait on the phone`() {
                compose.onNodeWithContentDescription(FIRST_PAGE_ON_THE_PHONE).assertIsDisplayed()
            }

            @Test
            fun `should keep a region with a size for a refusal, so that one is read out when it appears`() {
                compose.onNode(isPoliteLiveRegion())
                    .assertWidthIsAtLeast(1.dp)
                    .assertHeightIsAtLeast(1.dp)
            }

            @Test
            fun `should mark its title and the titles of its sections as headings, in reading order`() {
                assertEquals(HEADINGS, readHeadingsFromTheTop(compose))
            }

            companion object {
                private val HEADINGS = listOf("Example Book", "On the phone (4)", "On the PC (8)")

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItsPagesAreBeingReadAndScrolledToThePc(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePagesOnThePc() {
                compose.setContent { ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ) } }
                compose.onNode(hasScrollToKeyAction()).performScrollToKey(PAGES_ON_THE_PC_KEY)
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/document-reading-pc-$theme.png")
            }

            @Test
            fun `should show the pages on the PC by their numbers`() {
                compose.onNodeWithContentDescription(FIRST_READ_PAGE).assertIsDisplayed()
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
        class WhenItsPagesAreBeingReadAndTheTextIsTwiceItsSize(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent { ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/document-reading-large-text-$theme.png")
            }

            @Test
            fun `should show the pages that wait on the phone`() {
                compose.onNodeWithContentDescription(FIRST_PAGE_ON_THE_PHONE).assertIsDisplayed()
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
        class WhenItsPagesAreBeingReadAndTheTextIsTwiceItsSizeAndScrolledToThePc(
            private val theme: String,
            private val dark: Boolean,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePagesOnThePc() {
                compose.setContent { ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ) } }
                compose.onNode(hasScrollToKeyAction()).performScrollToKey(PAGES_ON_THE_PC_KEY)
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/document-reading-large-text-pc-$theme.png")
            }

            @Test
            fun `should show the pages on the PC by their numbers`() {
                compose.onNodeWithContentDescription(FIRST_READ_PAGE).assertIsDisplayed()
            }

            @Test
            fun `should lay the pages out in two columns, so that no badge is cut`() {
                assertEquals(2, countColumnsOfTheFirstThreePagesOnThePc(compose))
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.SmallPhone, fontScale = 2f)
        class WhenItsPagesAreBeingReadAndTheTextIsTwiceItsSizeOnASmallPhone(
            private val theme: String,
            private val dark: Boolean,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePagesOnThePhone() {
                compose.setContent { ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ) } }
                compose.onNode(hasScrollToKeyAction()).performScrollToKey(PAGES_ON_THE_PHONE_KEY)
                compose.onRoot()
                    .captureRoboImage("build/outputs/roborazzi/document-reading-large-text-small-phone-$theme.png")
            }

            @Test
            fun `should show the pages that wait on the phone`() {
                compose.onNodeWithContentDescription(FIRST_PAGE_ON_THE_PHONE).assertIsDisplayed()
            }

            companion object {
                private const val PAGES_ON_THE_PHONE_KEY = "local"

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.SmallPhone, fontScale = 2f)
        class WhenTheTextIsTwiceItsSizeOnASmallPhoneAndScrolledToThePc(
            private val theme: String,
            private val dark: Boolean,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePagesOnThePc() {
                compose.setContent { ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ) } }
                compose.onNode(hasScrollToKeyAction()).performScrollToKey(PAGES_ON_THE_PC_KEY)
                compose.onRoot()
                    .captureRoboImage("build/outputs/roborazzi/document-reading-large-text-small-phone-pc-$theme.png")
            }

            @Test
            fun `should lay the pages out in two columns, so that no badge is cut`() {
                assertEquals(2, countColumnsOfTheFirstThreePagesOnThePc(compose))
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
        class WhenThePcRejectedIt(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent { ScanMyLibTheme(dark = dark) { DocumentContentOf(PAMPHLET_REJECTED) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/document-rejected-$theme.png")
            }

            @Test
            fun `should say why the PC rejected it`() {
                compose.onNodeWithText(REJECTION, substring = true).assertIsDisplayed()
            }

            @Test
            fun `should offer to send it again`() {
                compose.onNodeWithText(RETRY).assertIsDisplayed()
            }

            @Test
            fun `should announce the refusal from a region that stays, so that its appearance is read out`() {
                compose.onNode(isPoliteLiveRegion() and hasAnyDescendant(hasText(REJECTION, substring = true)))
                    .assertExists()
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
        class WhenPagesWaitToBeSent(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent {
                    ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ, scan = THREE_PAGES_TO_SEND) }
                }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/document-pages-to-send-$theme.png")
            }

            @Test
            fun `should say how many pages wait on the phone, not on the PC yet`() {
                compose.onNodeWithText(THREE_PAGES_TO_SEND_TEXT).assertIsDisplayed()
            }

            @Test
            fun `should offer to review them`() {
                compose.onNodeWithText(REVIEW).assertIsDisplayed()
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
        class WhenPagesWaitToBeSentAndTheTextIsTwiceItsSize(private val theme: String, private val dark: Boolean) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent {
                    ScanMyLibTheme(dark = dark) { DocumentContentOf(BOOK_BEING_READ, scan = THREE_PAGES_TO_SEND) }
                }
                compose.onRoot().captureRoboImage(
                    "build/outputs/roborazzi/document-pages-to-send-large-text-$theme.png",
                )
            }

            @Test
            fun `should offer to review them`() {
                compose.onNodeWithText(REVIEW).assertIsDisplayed()
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPagesWaitToBeSentAndReviewIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var reviews: MutableList<Unit>

            @Before
            fun tapReview() {
                reviews = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(BOOK_BEING_READ, scan = THREE_PAGES_TO_SEND, onReview = { reviews += Unit })
                    }
                }
                compose.onNodeWithText(REVIEW).performClick()
            }

            @Test
            fun `should open the review`() {
                assertEquals(1, reviews.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenPagesAreBeingPrepared {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent {
                    ScanMyLibTheme { DocumentContentOf(BOOK_BEING_READ, scan = PREPARING_FOUR_PAGES) }
                }
            }

            @Test
            fun `should say how many pages are being prepared, once per copy`() {
                compose.onNodeWithText(PREPARING_FOUR_PAGES_TEXT).assertIsDisplayed()
            }

            @Test
            fun `should offer to review them`() {
                compose.onNodeWithText(REVIEW).assertIsDisplayed()
            }

            companion object {
                private const val PREPARING_FOUR_PAGES_TEXT = "Preparing 4 pages…"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheAppWasClosedWhileAddingPagesAndNoPageIsLeft {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(BOOK_BEING_READ, scan = NOTHING_TO_SEND.copy(wasAddingInterrupted = true))
                    }
                }
            }

            @Test
            fun `should ask to add the pages again`() {
                compose.onNodeWithText(ADDING_INTERRUPTED).assertIsDisplayed()
            }

            @Test
            fun `should let the message be dismissed`() {
                compose.onNodeWithText(OK).assertIsDisplayed()
            }

            @Test
            fun `should not offer a review, since there is nothing to review`() {
                compose.onNodeWithText(REVIEW).assertDoesNotExist()
            }

            companion object {
                private const val ADDING_INTERRUPTED =
                    "The app was closed while pages were being added: add them again."
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheAppWasClosedWhileAddingPagesAndNoPageIsLeftAndOkIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var dismissals: MutableList<Unit>

            @Before
            fun tapOk() {
                dismissals = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(
                            BOOK_BEING_READ,
                            scan = NOTHING_TO_SEND.copy(wasAddingInterrupted = true),
                            onDismissAddingInterrupted = { dismissals += Unit },
                        )
                    }
                }
                compose.onNodeWithText(OK).performClick()
            }

            @Test
            fun `should dismiss the message`() {
                assertEquals(1, dismissals.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenAnImportSkippedPhotos {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent { ScanMyLibTheme { DocumentContentOf(BOOK_BEING_READ, scan = PHOTOS_SKIPPED) } }
            }

            @Test
            fun `should say so from a region that stays, so that it is read out`() {
                compose.onNode(isPoliteLiveRegion() and hasAnyDescendant(hasText(TWO_SKIPPED, substring = true)))
                    .assertExists()
            }

            @Test
            fun `should let the banner be dismissed`() {
                compose.onNodeWithText(OK).assertIsDisplayed()
            }

            companion object {
                private const val TWO_SKIPPED = "2 photos"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenAnImportSkippedPhotosAndOkIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var dismissals: MutableList<Unit>

            @Before
            fun tapOk() {
                dismissals = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(
                            BOOK_BEING_READ,
                            scan = PHOTOS_SKIPPED,
                            onDismissOutcome = { dismissals += Unit },
                        )
                    }
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
        class WhenThePcRejectedItAndPagesWaitToBeSent {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                compose.setContent {
                    ScanMyLibTheme { DocumentContentOf(PAMPHLET_REJECTED, scan = THREE_PAGES_TO_SEND) }
                }
            }

            @Test
            fun `should show both banners in the one region that is read out`() {
                compose.onNode(
                    isPoliteLiveRegion() and
                        hasAnyDescendant(hasText(REJECTION, substring = true)) and
                        hasAnyDescendant(hasText(THREE_PAGES_TO_SEND_TEXT)),
                ).assertExists()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheReviewEndedWithThePagesKept {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var snackbarHostState: SnackbarHostState
            private lateinit var snackbarMessages: List<String>

            @Before
            fun endTheReview() {
                snackbarHostState = SnackbarHostState()
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(
                            BOOK_BEING_READ,
                            scan = THREE_PAGES_TO_SEND,
                            reviewEnd = ReviewEnd.PagesKept,
                            snackbarHostState = snackbarHostState,
                        )
                    }
                }
                compose.waitForIdle()
                snackbarMessages = listOfNotNull(snackbarHostState.currentSnackbarData?.visuals?.message)
            }

            @Test
            fun `should say that the pages are kept on the phone`() {
                assertEquals(listOf("Pages kept on the phone"), snackbarMessages)
            }

            @Test
            fun `should move the focus to the banner's review, where the user goes on`() {
                compose.onNodeWithText(REVIEW).assertIsFocused()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheReviewEndedWithThePagesSent {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var snackbarHostState: SnackbarHostState
            private lateinit var snackbarMessages: List<String>

            @Before
            fun endTheReview() {
                snackbarHostState = SnackbarHostState()
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(
                            BOOK_BEING_READ,
                            scan = THREE_PAGES_TO_SEND,
                            reviewEnd = ReviewEnd.PagesSent(PAGE_TO_SEND_COUNT),
                            snackbarHostState = snackbarHostState,
                        )
                    }
                }
                compose.waitForIdle()
                snackbarMessages = listOfNotNull(snackbarHostState.currentSnackbarData?.visuals?.message)
            }

            @Test
            fun `should say that the pages are on their way to the PC`() {
                assertEquals(listOf("Sending 3 pages to the PC"), snackbarMessages)
            }

            @Test
            fun `should move the focus to the pages on the phone, where the sent pages now are`() {
                compose.onNodeWithText(PAGES_ON_THE_PHONE).assertIsFocused()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheReviewEndedWithThePagesDeleted {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var snackbarHostState: SnackbarHostState
            private lateinit var snackbarMessages: List<String>

            @Before
            fun endTheReview() {
                snackbarHostState = SnackbarHostState()
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(
                            BOOK_BEING_READ,
                            scan = THREE_PAGES_TO_SEND,
                            reviewEnd = ReviewEnd.PagesDeleted(DELETED_PAGE_COUNT),
                            snackbarHostState = snackbarHostState,
                        )
                    }
                }
                compose.waitForIdle()
                snackbarMessages = listOfNotNull(snackbarHostState.currentSnackbarData?.visuals?.message)
            }

            @Test
            fun `should say that the pages are deleted`() {
                assertEquals(listOf("3 pages deleted from the phone"), snackbarMessages)
            }

            @Test
            fun `should move the focus to the scan button, where the user goes on`() {
                compose.onNode(hasText(SCAN) and hasClickAction()).assertIsFocused()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheReviewEndedEmpty {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var snackbarHostState: SnackbarHostState
            private lateinit var snackbarMessages: List<String>

            @Before
            fun endTheReview() {
                snackbarHostState = SnackbarHostState()
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(
                            BOOK_BEING_READ,
                            scan = THREE_PAGES_TO_SEND,
                            reviewEnd = ReviewEnd.Emptied,
                            snackbarHostState = snackbarHostState,
                        )
                    }
                }
                compose.waitForIdle()
                snackbarMessages = listOfNotNull(snackbarHostState.currentSnackbarData?.visuals?.message)
            }

            @Test
            fun `should say nothing, since nothing changed`() {
                assertEquals(emptyList<String>(), snackbarMessages)
            }

            @Test
            fun `should move the focus to the scan button, where the user goes on`() {
                compose.onNode(hasText(SCAN) and hasClickAction()).assertIsFocused()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheReviewEnded {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var endAndSnackbar: List<Any?>

            @Before
            fun tellTheEnd() {
                val snackbarHostState = SnackbarHostState()
                val reviewEnd = mutableStateOf<ReviewEnd?>(ReviewEnd.PagesKept)
                compose.setContent {
                    ScanMyLibTheme {
                        DocumentContentOf(
                            BOOK_BEING_READ,
                            scan = THREE_PAGES_TO_SEND,
                            reviewEnd = reviewEnd.value,
                            snackbarHostState = snackbarHostState,
                            onReviewEndShown = { reviewEnd.value = null },
                        )
                    }
                }
                compose.waitForIdle()
                endAndSnackbar = listOf(reviewEnd.value, snackbarHostState.currentSnackbarData?.visuals?.message)
            }

            @Test
            fun `should clear the end before the snackbar ends, so that the end is told once and the snackbar stays`() {
                assertEquals(listOf(null, "Pages kept on the phone"), endAndSnackbar)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItsTitleAndAuthorHoldCharactersAReaderCannotSee {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                val document = BOOK.copy(
                    title = makeCharacter(0x202E) + BOOK.title + makeCharacter(0x0A),
                    author = makeCharacter(0x200B) + BOOK.author,
                )
                compose.setContent { ScanMyLibTheme { DocumentContentOf(BOOK_BEING_READ.copy(document = document)) } }
            }

            @Test
            fun `should show the title without them in the top bar`() {
                assertEquals(BOOK.title, readHeadingsFromTheTop(compose).first())
            }

            @Test
            fun `should show the author without them in the summary`() {
                compose.onNodeWithText("Book · ${BOOK.author}").assertIsDisplayed()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenItsRangesAndFolderHoldOnlyCharactersAReaderCannotSee {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                val invisibleText = makeCharacter(0x200B).repeat(3)
                val server =
                    BOOK.server?.copy(coverage = invisibleText, missing = invisibleText, folder = invisibleText)
                val document = BOOK.copy(server = server)
                compose.setContent { ScanMyLibTheme { DocumentContentOf(BOOK_BEING_READ.copy(document = document)) } }
            }

            @Test
            fun `should not mention the missing pages, rather than show an empty range`() {
                compose.onAllNodesWithText(MISSING_PAGES, substring = true).assertCountEquals(0)
            }

            @Test
            fun `should not mention the folder, rather than show an empty name`() {
                compose.onAllNodesWithText(FOLDER, substring = true).assertCountEquals(0)
            }

            @Test
            fun `should say that no page is numbered, rather than show an empty range`() {
                compose.onNodeWithText(NO_NUMBERED_PAGES).assertIsDisplayed()
            }

            companion object {
                private const val MISSING_PAGES = "Not scanned yet"
                private const val FOLDER = "Folder on the PC"
                private const val NO_NUMBERED_PAGES = "Scanned pages: no numbered pages"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcRejectsItWhileItIsOpen {
            @get:Rule
            val compose = createComposeRule()

            private var regionIdBefore by Delegates.notNull<Int>()
            private var regionIdAfter by Delegates.notNull<Int>()

            @Before
            fun rejectTheDocument() {
                val state = mutableStateOf(BOOK_BEING_READ)
                compose.setContent { ScanMyLibTheme { DocumentContentOf(state.value) } }
                regionIdBefore = compose.onNode(isPoliteLiveRegion()).fetchSemanticsNode().id
                state.value = BOOK_BEING_READ.copy(document = BOOK.copy(uploadError = "HTTP 422: $REJECTION"))
                compose.waitForIdle()
                regionIdAfter = compose
                    .onNode(isPoliteLiveRegion() and hasAnyDescendant(hasText(REJECTION, substring = true)))
                    .fetchSemanticsNode()
                    .id
            }

            @Test
            fun `should show the refusal in the region that was already there, so that it is read out`() {
                assertEquals(regionIdBefore, regionIdAfter)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcRejectedItAndRetryIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var retries: MutableList<Unit>

            @Before
            fun tapRetry() {
                retries = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { DocumentContentOf(PAMPHLET_REJECTED, onRetryDocumentUpload = { retries += Unit }) }
                }
                compose.onNodeWithText(RETRY).performClick()
            }

            @Test
            fun `should send the document again`() {
                assertEquals(1, retries.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcRejectedItWithAGarbledReason {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheDocument() {
                val document = PAMPHLET_REJECTED.document?.copy(uploadError = GARBLED_REASON)
                compose.setContent { ScanMyLibTheme { DocumentContentOf(PAMPHLET_REJECTED.copy(document = document)) } }
            }

            @Test
            fun `should show the reason on one line, without the characters a reader cannot see, and cut`() {
                compose.onNodeWithText(SHOWN_REFUSAL).assertIsDisplayed()
            }

            companion object {
                private val LONG_DETAIL = "x".repeat(MAX_TEXT_FROM_PC_GRAPHEMES)
                private val GARBLED_REASON =
                    "HTTP 422:" + makeCharacter(0x0A) + makeCharacter(0x202E) + "title " + LONG_DETAIL
                private val SHOWN_REFUSAL = "The PC rejected this document: " +
                    "HTTP 422: title $LONG_DETAIL".take(MAX_TEXT_FROM_PC_GRAPHEMES - 1) + "…"
            }
        }
    }
}

private const val FIRST_READ_PAGE = "Page 12, Text ready"
private val FIRST_THREE_PAGES_ON_THE_PC = listOf(FIRST_READ_PAGE, "Page 13, Reading…", "Page 14, Waiting to be read")
private const val PAGES_ON_THE_PC_KEY = "server"
private const val FIRST_PAGE_ON_THE_PHONE = "Page 31, Uploading…"
private const val REJECTION = "invalid title"
private const val RETRY = "Retry"
private const val REVIEW = "Review"
private const val OK = "OK"
private const val SCAN = "Scan"
private const val PAGES_ON_THE_PHONE = "On the phone (4)"
private const val PAGE_TO_SEND_COUNT = 3
private const val DELETED_PAGE_COUNT = PAGE_TO_SEND_COUNT
private const val THREE_PAGES_TO_SEND_TEXT = "3 pages to send, not on the PC yet."

private val THEMES = listOf(arrayOf<Any>("light", false), arrayOf<Any>("dark", true))

private val BOOK = DocumentEntity(
    id = "book",
    title = "Example Book",
    author = "Jane Doe",
    kind = DocumentKind.BOOK,
    unwarp = true,
    updatedAt = 0,
    needsUpload = false,
    uploadError = null,
    confirmedAt = 0,
    server = ServerDocumentState(
        pages = 8,
        done = 3,
        queued = 1,
        processing = 1,
        errors = 1,
        excluded = 1,
        duplicates = 1,
        coverage = "12–17",
        missing = "",
        unnumbered = 1,
        coverThumbUrl = null,
        folder = "example-book",
    ),
)

private fun makePageOnThePhone(number: Int, state: UploadState, failure: UploadFailure? = null) = PendingPageEntity(
    id = "phone-$number",
    documentId = BOOK.id,
    sessionId = "session",
    seq = number,
    capturedAt = "2026-10-12T10:00:00+02:00",
    pageNumberHint = number,
    fileName = null,
    state = state,
    failure = failure,
    lastError = null,
    attempts = if (failure == null) 0 else 1,
    queuedAt = number.toLong(),
)

private fun makePageOnThePc(label: String?, status: PageStatus, duplicate: Boolean = false, excluded: Boolean = false) =
    ServerPageEntity(
        id = "pc-$label-$status-$duplicate-$excluded",
        documentId = BOOK.id,
        position = 0,
        status = status,
        error = if (status == PageStatus.ERROR) "unreadable image" else null,
        pageLabel = label,
        numberSource = NumberSource.DETECTED,
        excluded = excluded,
        duplicate = duplicate,
        thumbUrl = null,
    )

private val BOOK_BEING_READ = DocumentUiState(
    loading = false,
    document = BOOK,
    pages = DocumentPages(
        local = listOf(
            makePageOnThePhone(31, UploadState.UPLOADING),
            makePageOnThePhone(32, UploadState.QUEUED),
            makePageOnThePhone(33, UploadState.FAILED, UploadFailure.TOO_LARGE),
            makePageOnThePhone(34, UploadState.UPLOADED),
        ),
        server = listOf(
            makePageOnThePc("12", PageStatus.DONE),
            makePageOnThePc("13", PageStatus.PROCESSING),
            makePageOnThePc("14", PageStatus.QUEUED),
            makePageOnThePc("15", PageStatus.ERROR),
            makePageOnThePc("16–17", PageStatus.DONE),
            makePageOnThePc(null, PageStatus.DONE),
            makePageOnThePc("14", PageStatus.DONE, duplicate = true),
            makePageOnThePc("18", PageStatus.DONE, excluded = true),
        ),
    ),
)

private val PAMPHLET_REJECTED = DocumentUiState(
    loading = false,
    document = DocumentEntity(
        id = "pamphlet",
        title = "Example Pamphlet",
        author = "",
        kind = DocumentKind.DOCUMENT,
        unwarp = false,
        updatedAt = 0,
        needsUpload = true,
        uploadError = "HTTP 422: $REJECTION",
        confirmedAt = 0,
        server = null,
    ),
    pages = DocumentPages(local = listOf(makePageOnThePhone(1, UploadState.QUEUED)), server = emptyList()),
)

private val NOTHING_TO_SEND = ScanUiState(defaultCamera = ScanSource.GOOGLE_SCANNER, loaded = true, isRunRead = true)

private val THREE_PAGES_TO_SEND = NOTHING_TO_SEND.copy(
    stagedPages = (1..PAGE_TO_SEND_COUNT).map { position ->
        StagedPage(File("/staging/run/$position.jpg"), seq = position, capturedAt = Instant.EPOCH)
    },
)

private val PHOTOS_SKIPPED =
    NOTHING_TO_SEND.copy(outcome = PreparationOutcome.PhotosSkipped(unsupported = 2, tooLarge = 0, unreadable = 0))

private val PREPARING_FOUR_PAGES =
    NOTHING_TO_SEND.copy(preparation = Preparation(done = 1, total = 4, imagesToAdd = 4, isCancellable = true))

private fun makeCharacter(codePoint: Int): String = String(Character.toChars(codePoint))

private fun countColumnsOfTheFirstThreePagesOnThePc(screen: SemanticsNodeInteractionsProvider): Int =
    FIRST_THREE_PAGES_ON_THE_PC.map { page ->
        screen.onNodeWithContentDescription(page).fetchSemanticsNode().positionInRoot.x.roundToInt()
    }.toSet().size

@Composable
private fun DocumentContentOf(
    state: DocumentUiState,
    scan: ScanUiState = NOTHING_TO_SEND,
    reviewEnd: ReviewEnd? = null,
    snackbarHostState: SnackbarHostState = remember { SnackbarHostState() },
    onRetryDocumentUpload: () -> Unit = {},
    onReview: () -> Unit = {},
    onDismissOutcome: () -> Unit = {},
    onDismissAddingInterrupted: () -> Unit = {},
    onReviewEndShown: () -> Unit = {},
) {
    DocumentContent(
        state = state,
        scan = scan,
        reviewEnd = reviewEnd,
        snackbarHostState = snackbarHostState,
        localImage = { null },
        onBack = {},
        onRefresh = {},
        onRetryDocumentUpload = onRetryDocumentUpload,
        onImport = {},
        onScan = {},
        onChooseCamera = {},
        onOpenLocalPage = {},
        onOpenServerPage = {},
        onReview = onReview,
        onDismissOutcome = onDismissOutcome,
        onDismissAddingInterrupted = onDismissAddingInterrupted,
        onReviewEndShown = onReviewEndShown,
    )
}
