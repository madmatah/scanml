package fr.scanmylib.ui.library

import androidx.compose.runtime.Composable
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
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
import fr.scanmylib.ui.theme.Contrast
import fr.scanmylib.ui.theme.ScanMyLibTheme
import fr.scanmylib.update.UpdateState
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
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

            companion object {
                private const val BOOK_TITLE = "Example Book"
                private const val PAMPHLET_TITLE = "Example Pamphlet"

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

                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "in the {0} theme")
                fun themes(): List<Array<Any>> = listOf(
                    arrayOf("light", false, Contrast.STANDARD),
                    arrayOf("dark", true, Contrast.STANDARD),
                    arrayOf("light-high-contrast", false, Contrast.HIGH),
                    arrayOf("dark-high-contrast", true, Contrast.HIGH),
                )
            }
        }
    }
}

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
