package fr.scanmylib.ui.share

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.ui.theme.ScanMyLibTheme
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class ShareScreenTest {
    @RunWith(Enclosed::class)
    class TheShareContentFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenADocumentsTitleAndAuthorHoldCharactersAReaderCannotSee {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheChoice() {
                compose.setContent {
                    ScanMyLibTheme {
                        ShareContent(
                            documents = listOf(GARBLED_DOCUMENT),
                            photoCount = PHOTOS_SHARED_SO_THAT_DOCUMENTS_ARE_LISTED,
                            onChoose = {},
                            onNewDocument = {},
                            onClose = {},
                        )
                    }
                }
            }

            @Test
            fun `should show the title without them`() {
                compose.onNodeWithText(TITLE).assertIsDisplayed()
            }

            @Test
            fun `should show the author without them`() {
                compose.onNodeWithText(AUTHOR).assertIsDisplayed()
            }

            companion object {
                private const val PHOTOS_SHARED_SO_THAT_DOCUMENTS_ARE_LISTED = 2
                private const val TITLE = "Example Book"
                private const val AUTHOR = "Jane Doe"
                private val GARBLED_DOCUMENT = DocumentEntity(
                    id = "book",
                    title = makeCharacter(0x202E) + TITLE + makeCharacter(0x0A),
                    author = makeCharacter(0x200B) + AUTHOR,
                    kind = DocumentKind.BOOK,
                    unwarp = true,
                    updatedAt = 0,
                    needsUpload = false,
                    uploadError = null,
                    confirmedAt = 0,
                    server = null,
                )
            }
        }
    }
}

private fun makeCharacter(codePoint: Int): String = String(Character.toChars(codePoint))
