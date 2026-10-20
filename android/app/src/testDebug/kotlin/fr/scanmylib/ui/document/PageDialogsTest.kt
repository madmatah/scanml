package fr.scanmylib.ui.document

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.ui.theme.ScanMyLibTheme
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class PageDialogsTest {
    @RunWith(Enclosed::class)
    class TheServerPageDialogFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheLabelHoldsOnlyCharactersAReaderCannotSee {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun openTheDialog() {
                compose.setContent { ScanMyLibTheme { ServerPageDialog(INVISIBLE_LABEL_PAGE, onDismiss = {}) } }
            }

            @Test
            fun `should title the page as unnumbered, never as an empty number`() {
                compose.onNodeWithText(UNNUMBERED).assertIsDisplayed()
            }

            companion object {
                private const val UNNUMBERED = "Unnumbered"
                private val INVISIBLE_LABEL_PAGE = ServerPageEntity(
                    id = "page",
                    documentId = "book",
                    position = 0,
                    status = PageStatus.DONE,
                    error = null,
                    pageLabel = String(Character.toChars(0x200B)).repeat(3),
                    numberSource = NumberSource.DETECTED,
                    excluded = false,
                    duplicate = false,
                    thumbUrl = null,
                )
            }
        }
    }
}
