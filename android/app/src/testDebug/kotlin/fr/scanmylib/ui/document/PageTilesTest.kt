package fr.scanmylib.ui.document

import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.ui.theme.ScanMyLibTheme
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class PageTilesTest {
    @RunWith(Enclosed::class)
    class TheServerPageTileFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenDrawn(private val name: String, private val page: ServerPageEntity, private val description: String) {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawThePage() {
                compose.setContent { ScanMyLibTheme { ServerPageTile(page, server = null, onClick = {}) } }
            }

            @Test
            fun `should read its pages in words, with what the page's state means in full`() {
                assertEquals(name, 1, compose.onAllNodesWithContentDescription(description).fetchSemanticsNodes().size)
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
                fun pages(): List<Array<Any>> = listOf(
                    arrayOf("a page whose text is ready", makePageOnThePc("12"), "Page 12, Text ready"),
                    arrayOf("a spread", makePageOnThePc("16–17"), "Pages 16 and 17, Text ready"),
                    arrayOf(
                        "a page whose text could not be read",
                        makePageOnThePc("15", PageStatus.ERROR),
                        "Page 15, Couldn’t read the text",
                    ),
                    arrayOf(
                        "a duplicate",
                        makePageOnThePc("14", isDuplicate = true),
                        "Page 14, Duplicate: a page scanned later has the same number.",
                    ),
                    arrayOf(
                        "an excluded page",
                        makePageOnThePc("18", isExcluded = true),
                        "Page 18, Excluded from the document.",
                    ),
                    arrayOf(
                        "a page whose label is longer than a label can be",
                        makePageOnThePc("1234567890123456789"),
                        "Page 123456789012345…, Text ready",
                    ),
                    arrayOf(
                        "a page whose label holds only characters a reader cannot see",
                        makePageOnThePc(String(Character.toChars(0x200B)).repeat(3)),
                        "Unnumbered page, Text ready",
                    ),
                )
            }
        }
    }
}

private fun makePageOnThePc(
    label: String,
    status: PageStatus = PageStatus.DONE,
    isDuplicate: Boolean = false,
    isExcluded: Boolean = false,
) = ServerPageEntity(
    id = "page",
    documentId = "book",
    position = 0,
    status = status,
    error = null,
    pageLabel = label,
    numberSource = NumberSource.DETECTED,
    excluded = isExcluded,
    duplicate = isDuplicate,
    thumbUrl = null,
)
