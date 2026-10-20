package fr.scanmylib.ui.document

import androidx.compose.runtime.Composable
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasScrollToKeyAction
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performScrollToKey
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
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.theme.ScanMyLibTheme
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
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
                compose.onNodeWithText(FIRST_READ_PAGE).assertIsDisplayed()
            }

            @Test
            fun `should show the pages that wait on the phone`() {
                compose.onNodeWithText(FIRST_PAGE_ON_THE_PHONE).assertIsDisplayed()
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
                compose.onNodeWithText(FIRST_READ_PAGE).assertIsDisplayed()
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
                compose.onNodeWithText(FIRST_PAGE_ON_THE_PHONE).assertIsDisplayed()
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
                compose.onNodeWithText(FIRST_READ_PAGE).assertIsDisplayed()
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

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = THEMES
            }
        }
    }
}

private const val FIRST_READ_PAGE = "p. 12"
private const val PAGES_ON_THE_PC_KEY = "server"
private const val FIRST_PAGE_ON_THE_PHONE = "p. 31"
private const val REJECTION = "invalid title"

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

private fun pageOnThePhone(number: Int, state: UploadState, failure: UploadFailure? = null) = PendingPageEntity(
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

private fun pageOnThePc(label: String?, status: PageStatus, duplicate: Boolean = false, excluded: Boolean = false) =
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
            pageOnThePhone(31, UploadState.UPLOADING),
            pageOnThePhone(32, UploadState.QUEUED),
            pageOnThePhone(33, UploadState.FAILED, UploadFailure.TOO_LARGE),
        ),
        server = listOf(
            pageOnThePc("12", PageStatus.DONE),
            pageOnThePc("13", PageStatus.PROCESSING),
            pageOnThePc("14", PageStatus.QUEUED),
            pageOnThePc("15", PageStatus.ERROR),
            pageOnThePc("16–17", PageStatus.DONE),
            pageOnThePc(null, PageStatus.DONE),
            pageOnThePc("14", PageStatus.DONE, duplicate = true),
            pageOnThePc("18", PageStatus.DONE, excluded = true),
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
    pages = DocumentPages(local = listOf(pageOnThePhone(1, UploadState.QUEUED)), server = emptyList()),
)

@Composable
private fun DocumentContentOf(state: DocumentUiState) {
    DocumentContent(
        state = state,
        camera = ScanSource.GOOGLE_SCANNER,
        canScan = true,
        localImage = { null },
        onBack = {},
        onRefresh = {},
        onRetryDocumentUpload = {},
        onImport = {},
        onScan = {},
        onChooseCamera = {},
        onOpenLocalPage = {},
        onOpenServerPage = {},
        snackbarHost = {},
    )
}
