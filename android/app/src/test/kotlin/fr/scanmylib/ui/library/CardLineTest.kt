package fr.scanmylib.ui.library

import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.model.DocumentKind
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class CardLineTest {
    @RunWith(Enclosed::class)
    class TheCardLinesFunction {
        class WhenAllPagesAreRead {
            private lateinit var lines: List<CardLine>

            @Before
            fun drawTheCard() {
                lines = cardLines(buildLibraryRow(), stagedPages = 0)
            }

            @Test
            fun `should show no line`() {
                assertEquals(emptyList<CardLine>(), lines)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheDocumentIsInOneState(
            private val case: String,
            private val row: LibraryRow,
            private val stagedPages: Int,
            private val expected: CardLine,
        ) {
            private lateinit var lines: List<CardLine>

            @Before
            fun drawTheCard() {
                lines = cardLines(row, stagedPages)
            }

            @Test
            fun `should show the state on a line of its own`() {
                assertEquals(case, listOf(expected), lines)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun states(): List<Array<Any>> = listOf(
                    arrayOf("pages to send", buildLibraryRow(), 4, CardLine.ToSend(4)),
                    arrayOf("pages in transit", buildLibraryRow(pagesToUpload = 2), 0, CardLine.InTransit(2)),
                    arrayOf("uploads refused", buildLibraryRow(failedPages = 1), 0, CardLine.Refused(1)),
                    arrayOf(
                        "pages the PC could not read",
                        buildLibraryRow(buildServerState(errors = 2)),
                        0,
                        CardLine.ReadFailed(2),
                    ),
                    arrayOf(
                        "pages being read",
                        buildLibraryRow(buildServerState(queued = 2, processing = 1)),
                        0,
                        CardLine.BeingRead(3),
                    ),
                    arrayOf("not on the PC yet", buildLibraryRow(server = null), 0, CardLine.NotOnPcYet),
                    arrayOf(
                        "the document refused by the PC",
                        buildLibraryRow(server = null, uploadError = "title too long"),
                        0,
                        CardLine.DocumentRefused,
                    ),
                )
            }
        }

        class WhenTheDocumentIsInEveryState {
            private lateinit var lines: List<CardLine>

            @Before
            fun drawTheCard() {
                val server = buildServerState(queued = 1, processing = 1, errors = 2)
                lines = cardLines(buildLibraryRow(server, pagesToUpload = 4, failedPages = 1), stagedPages = 3)
            }

            @Test
            fun `should never merge the states, and put first those that need the user`() {
                assertEquals(
                    listOf(
                        CardLine.ToSend(3),
                        CardLine.Refused(1),
                        CardLine.ReadFailed(2),
                        CardLine.InTransit(4),
                        CardLine.BeingRead(2),
                    ),
                    lines,
                )
            }
        }
    }
}

private fun buildServerState(queued: Int = 0, processing: Int = 0, errors: Int = 0) = ServerDocumentState(
    pages = SERVER_PAGE_COUNT,
    done = SERVER_PAGE_COUNT - queued - processing - errors,
    queued = queued,
    processing = processing,
    errors = errors,
    excluded = 0,
    duplicates = 0,
    coverage = "12–31, 88–90",
    missing = "32–87",
    unnumbered = 0,
    coverThumbUrl = null,
    folder = "example-book",
)

private fun buildLibraryRow(
    server: ServerDocumentState? = buildServerState(),
    uploadError: String? = null,
    pagesToUpload: Int = 0,
    failedPages: Int = 0,
) = LibraryRow(
    DocumentEntity(
        id = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b",
        title = "Example Book",
        author = "Jane Doe",
        kind = DocumentKind.BOOK,
        unwarp = true,
        updatedAt = 0,
        needsUpload = server == null,
        uploadError = uploadError,
        confirmedAt = 0,
        server = server,
    ),
    pagesToUpload = pagesToUpload,
    failedPages = failedPages,
)

private const val SERVER_PAGE_COUNT = 25
