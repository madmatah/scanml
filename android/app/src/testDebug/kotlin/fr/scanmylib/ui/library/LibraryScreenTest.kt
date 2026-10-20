package fr.scanmylib.ui.library

import androidx.compose.runtime.Composable
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import com.github.takahirom.roborazzi.captureRoboImage
import fr.scanmylib.api.OcrStatus
import fr.scanmylib.api.QueueCounts
import fr.scanmylib.api.ServerStatus
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.ui.readHeadingsFromTheTop
import fr.scanmylib.ui.theme.Contrast
import fr.scanmylib.ui.theme.ScanMyLibTheme
import fr.scanmylib.update.UpdateState
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

            companion object {
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

private const val APP_NAME = "ScanMyLib"
private const val BOOK_TITLE = "Example Book"
private const val PAMPHLET_TITLE = "Example Pamphlet"

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
private fun LibraryContentOf(state: LibraryUiState) {
    LibraryContent(
        state = state,
        update = UpdateState.UpToDate,
        onOpenDocument = {},
        onScanDocument = {},
        onNewDocument = {},
        onOpenSettings = {},
        onRefresh = {},
        onInstallUpdate = {},
        onCancelUpdate = {},
    )
}
