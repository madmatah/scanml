package fr.scanmylib.ui.library

import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.hasAnyDescendant
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.dp
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureRoboImage
import fr.scanmylib.api.OcrStatus
import fr.scanmylib.api.QueueCounts
import fr.scanmylib.api.ServerStatus
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.ui.components.MAX_TEXT_FROM_PC_GRAPHEMES
import fr.scanmylib.ui.isPoliteLiveRegion
import fr.scanmylib.ui.readHeadingsFromTheTop
import fr.scanmylib.ui.theme.Contrast
import fr.scanmylib.ui.theme.ScanMyLibTheme
import fr.scanmylib.update.UpdateState
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
class LibraryScreenTest {
    @RunWith(Enclosed::class)
    class TheLibraryContentFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcIsReading(private val theme: String, private val dark: Boolean, private val contrast: Contrast) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                compose.setContent { ScanMyLibTheme(dark = dark, contrast = contrast) { LibraryContentOf(LIBRARY) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/library-reading-$theme.png")
            }

            @Test
            fun `should show each document by its title`() {
                compose.onNodeWithText(BOOK_TITLE).assertIsDisplayed()
                compose.onNodeWithText(PAMPHLET_TITLE).assertIsDisplayed()
            }

            @Test
            fun `should mark its title as a heading`() {
                assertEquals(listOf(APP_NAME), readHeadingsFromTheTop(compose))
            }

            @Test
            fun `should offer no retry while all goes well`() {
                compose.onAllNodesWithText(RETRY).assertCountEquals(0)
            }

            @Test
            fun `should keep a region with a size for the PC's problems, so that one is read out when it appears`() {
                compose.onNode(isPoliteLiveRegion())
                    .assertWidthIsAtLeast(1.dp)
                    .assertHeightIsAtLeast(1.dp)
            }

            @Test
            fun `should never read out the normal card, so that each count of pages being read stays quiet`() {
                compose.onAllNodes(isPoliteLiveRegion() and hasAnyDescendant(hasText(PC_CONNECTED, substring = true)))
                    .assertCountEquals(0)
            }

            companion object {
                private const val APP_NAME = "ScanMyLib"
                private const val PC_CONNECTED = "PC connected"

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES_AND_CONTRASTS
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone, fontScale = 2f)
        class WhenThePcIsReadingAndTheTextIsTwiceItsSize(
            private val theme: String,
            private val dark: Boolean,
            private val contrast: Contrast,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                compose.setContent { ScanMyLibTheme(dark = dark, contrast = contrast) { LibraryContentOf(LIBRARY) } }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/library-reading-large-text-$theme.png")
            }

            @Test
            fun `should show what each document waits for`() {
                compose.onNodeWithContentDescription(BOOK_PAGES_ON_THEIR_WAY).assertIsDisplayed()
                compose.onNodeWithContentDescription(PAMPHLET_PAGE_REJECTED).assertIsDisplayed()
            }

            companion object {
                private const val BOOK_PAGES_ON_THEIR_WAY = "3 on their way to the PC"
                private const val PAMPHLET_PAGE_REJECTED = "1 rejected"

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES_AND_CONTRASTS
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcIsUnreachable(
            private val theme: String,
            private val dark: Boolean,
            private val contrast: Contrast,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                compose.setContent {
                    ScanMyLibTheme(dark = dark, contrast = contrast) {
                        LibraryContentOf(LIBRARY.copy(pc = PcState.Unreachable))
                    }
                }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/library-unreachable-$theme.png")
            }

            @Test
            fun `should offer to try again`() {
                compose.onNodeWithText(RETRY).assertIsDisplayed()
            }

            @Test
            fun `should announce the problem from a region that stays, so that its appearance is read out`() {
                compose.onNode(isPoliteLiveRegion() and hasAnyDescendant(hasText(UNREACHABLE, substring = true)))
                    .assertExists()
            }

            companion object {
                private const val UNREACHABLE = "PC unreachable"

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES_AND_CONTRASTS
            }
        }

        @RunWith(ParameterizedRobolectricTestRunner::class)
        @GraphicsMode(GraphicsMode.Mode.NATIVE)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcNoLongerRecognizesThePhone(
            private val theme: String,
            private val dark: Boolean,
            private val contrast: Contrast,
        ) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                compose.setContent {
                    ScanMyLibTheme(dark = dark, contrast = contrast) {
                        LibraryContentOf(LIBRARY.copy(pc = PcState.TokenRefused))
                    }
                }
                compose.onRoot().captureRoboImage("build/outputs/roborazzi/library-token-refused-$theme.png")
            }

            @Test
            fun `should lead to the settings, where the phone is paired again`() {
                compose.onNodeWithText(SETTINGS).assertIsDisplayed()
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES_AND_CONTRASTS
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcBecomesUnreachableWhileItReads {
            @get:Rule
            val compose = createComposeRule()

            private var regionIdBefore by Delegates.notNull<Int>()
            private var regionIdAfter by Delegates.notNull<Int>()

            @Before
            fun loseThePc() {
                val pc = mutableStateOf(LIBRARY.pc)
                compose.setContent { ScanMyLibTheme { LibraryContentOf(LIBRARY.copy(pc = pc.value)) } }
                regionIdBefore = compose.onNode(isPoliteLiveRegion()).fetchSemanticsNode().id
                pc.value = PcState.Unreachable
                compose.waitForIdle()
                regionIdAfter = compose
                    .onNode(isPoliteLiveRegion() and hasAnyDescendant(hasText(UNREACHABLE, substring = true)))
                    .fetchSemanticsNode()
                    .id
            }

            @Test
            fun `should show the problem in the region that was already there, so that it is read out`() {
                assertEquals(regionIdBefore, regionIdAfter)
            }

            companion object {
                private const val UNREACHABLE = "PC unreachable"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcIsUnreachableAndRetryIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var refreshes: MutableList<Unit>

            @Before
            fun tapRetry() {
                refreshes = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        LibraryContentOf(LIBRARY.copy(pc = PcState.Unreachable), onRefresh = { refreshes += Unit })
                    }
                }
                compose.onNodeWithText(RETRY).performClick()
            }

            @Test
            fun `should ask the PC again`() {
                assertEquals(1, refreshes.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcCannotReadAndRetryIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var refreshes: MutableList<Unit>

            @Before
            fun tapRetry() {
                refreshes = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        LibraryContentOf(LIBRARY.copy(pc = PC_THAT_CANNOT_READ), onRefresh = { refreshes += Unit })
                    }
                }
                compose.onNodeWithText(RETRY).performClick()
            }

            @Test
            fun `should ask the PC again`() {
                assertEquals(1, refreshes.size)
            }

            companion object {
                private val PC_THAT_CANNOT_READ = PcState.Online(ServerStatus(ocr = OcrStatus(state = "unreachable")))
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcAnswersWithAnErrorAndRetryIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var refreshes: MutableList<Unit>

            @Before
            fun tapRetry() {
                refreshes = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        LibraryContentOf(
                            LIBRARY.copy(pc = PcState.Error(SERVER_ERROR)),
                            onRefresh = { refreshes += Unit },
                        )
                    }
                }
                compose.onNodeWithText(RETRY).performClick()
            }

            @Test
            fun `should ask the PC again`() {
                assertEquals(1, refreshes.size)
            }

            companion object {
                private const val SERVER_ERROR = "HTTP 500"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcNoLongerRecognizesThePhoneAndSettingsIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var openings: MutableList<Unit>

            @Before
            fun tapSettings() {
                openings = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        LibraryContentOf(LIBRARY.copy(pc = PcState.TokenRefused), onOpenSettings = { openings += Unit })
                    }
                }
                compose.onNodeWithText(SETTINGS).performClick()
            }

            @Test
            fun `should open the settings`() {
                assertEquals(1, openings.size)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenThePcAnswersWithAGarbledError {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                compose.setContent {
                    ScanMyLibTheme { LibraryContentOf(LIBRARY.copy(pc = PcState.Error(GARBLED_ERROR))) }
                }
            }

            @Test
            fun `should show it on one line, without the characters a reader cannot see, and cut`() {
                compose.onNodeWithText(SHOWN_ERROR).assertIsDisplayed()
            }

            companion object {
                private val LONG_DETAIL = "x".repeat(MAX_TEXT_FROM_PC_GRAPHEMES)
                private val GARBLED_ERROR =
                    "HTTP 500:" + makeCharacter(0x0A) + makeCharacter(0x202E) + "engine " + LONG_DETAIL
                private val SHOWN_ERROR =
                    "PC error: " + "HTTP 500: engine $LONG_DETAIL".take(MAX_TEXT_FROM_PC_GRAPHEMES - 1) + "…"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenATitleAndAnAuthorHoldBidirectionalControls {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                val document = BOOK.document.copy(
                    title = makeCharacter(0x202E) + BOOK_TITLE,
                    author = makeCharacter(0x2066) + AUTHOR + makeCharacter(0x2069),
                )
                val book = BOOK.copy(document = document)
                compose.setContent { ScanMyLibTheme { LibraryContentOf(LIBRARY.copy(documents = listOf(book))) } }
            }

            @Test
            fun `should show the title without them, so that it reads in the order it was written`() {
                compose.onNodeWithText(BOOK_TITLE).assertIsDisplayed()
            }

            @Test
            fun `should show the author without them`() {
                compose.onNodeWithText(AUTHOR).assertIsDisplayed()
            }

            @Test
            fun `should name the scan button after the title without them`() {
                compose.onNodeWithContentDescription(SCAN_THE_BOOK).assertExists()
            }

            companion object {
                private const val AUTHOR = "Jane Doe"
                private const val SCAN_THE_BOOK = "Scan pages into $BOOK_TITLE"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenACoverageHoldsOnlyCharactersAReaderCannotSee {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                val server = BOOK.document.server?.copy(coverage = makeCharacter(0x200B).repeat(3))
                val book = BOOK.copy(document = BOOK.document.copy(server = server))
                compose.setContent { ScanMyLibTheme { LibraryContentOf(LIBRARY.copy(documents = listOf(book))) } }
            }

            @Test
            fun `should count the pages without an empty range`() {
                compose.onNodeWithText(PAGES_WITHOUT_RANGE).assertIsDisplayed()
            }

            companion object {
                private const val PAGES_WITHOUT_RANGE = "25 pages"
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheEngineFailsWithAnErrorOfCharactersAReaderCannotSee {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheLibrary() {
                val status = ServerStatus(ocr = OcrStatus(state = "error", lastError = makeCharacter(0x200B).repeat(3)))
                compose.setContent { ScanMyLibTheme { LibraryContentOf(LIBRARY.copy(pc = PcState.Online(status))) } }
            }

            @Test
            fun `should show the generic message, never an empty error`() {
                compose.onNodeWithText(READING_UNAVAILABLE).assertIsDisplayed()
            }

            companion object {
                private const val READING_UNAVAILABLE =
                    "PC connected, but text recognition isn’t available: the pages wait on the PC."
            }
        }
    }
}

private const val BOOK_TITLE = "Example Book"
private const val PAMPHLET_TITLE = "Example Pamphlet"
private const val RETRY = "Retry"
private const val SETTINGS = "Settings"

private val THEMES_AND_CONTRASTS = listOf(
    arrayOf<Any>("light", false, Contrast.STANDARD),
    arrayOf<Any>("dark", true, Contrast.STANDARD),
    arrayOf<Any>("light-high-contrast", false, Contrast.HIGH),
    arrayOf<Any>("dark-high-contrast", true, Contrast.HIGH),
)

private val BOOK = LibraryRow(
    document = DocumentEntity(
        id = "book",
        title = BOOK_TITLE,
        author = "Jane Doe",
        kind = DocumentKind.BOOK,
        unwarp = true,
        updatedAt = 0,
        needsUpload = false,
        uploadError = null,
        confirmedAt = 0,
        server = ServerDocumentState(
            pages = 25,
            done = 23,
            queued = 2,
            processing = 0,
            errors = 0,
            excluded = 0,
            duplicates = 0,
            coverage = "12–31, 88–92",
            missing = "32–87",
            unnumbered = 0,
            coverThumbUrl = null,
            folder = "Example Book",
        ),
    ),
    pagesToUpload = 3,
    failedPages = 0,
)

private val PAMPHLET = LibraryRow(
    document = DocumentEntity(
        id = "pamphlet",
        title = PAMPHLET_TITLE,
        author = "",
        kind = DocumentKind.DOCUMENT,
        unwarp = false,
        updatedAt = 0,
        needsUpload = true,
        uploadError = null,
        confirmedAt = 0,
        server = null,
    ),
    pagesToUpload = 0,
    failedPages = 1,
)

private val LIBRARY = LibraryUiState(
    documents = listOf(BOOK, PAMPHLET),
    pc = PcState.Online(
        ServerStatus(ocr = OcrStatus(state = "ready"), queue = QueueCounts(queued = 2)),
    ),
)

private fun makeCharacter(codePoint: Int): String = String(Character.toChars(codePoint))

@Composable
private fun LibraryContentOf(state: LibraryUiState, onRefresh: () -> Unit = {}, onOpenSettings: () -> Unit = {}) {
    LibraryContent(
        state = state,
        update = UpdateState.UpToDate,
        onOpenDocument = {},
        onScanDocument = {},
        onNewDocument = {},
        onOpenSettings = onOpenSettings,
        onRefresh = onRefresh,
        onInstallUpdate = {},
        onCancelUpdate = {},
    )
}
