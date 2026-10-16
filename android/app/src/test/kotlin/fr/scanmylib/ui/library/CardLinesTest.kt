package fr.scanmylib.ui.library

import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.model.DocumentKind
import org.junit.Assert.assertEquals
import org.junit.Test

class CardLinesTest {

    private fun server(pages: Int = 25, queued: Int = 0, processing: Int = 0, errors: Int = 0) = ServerDocumentState(
        pages = pages,
        done = pages - queued - processing - errors,
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

    private fun row(
        server: ServerDocumentState? = server(),
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

    @Test
    fun `a document whose pages are all read shows no line`() {
        assertEquals(emptyList<CardLine>(), cardLines(row(), stagedPages = 0))
    }

    @Test
    fun `each state has its own line`() {
        assertEquals(listOf(CardLine.ToSend(4)), cardLines(row(), stagedPages = 4))
        assertEquals(listOf(CardLine.InTransit(2)), cardLines(row(pagesToUpload = 2), stagedPages = 0))
        assertEquals(listOf(CardLine.Refused(1)), cardLines(row(failedPages = 1), stagedPages = 0))
        assertEquals(listOf(CardLine.ReadFailed(2)), cardLines(row(server(errors = 2)), stagedPages = 0))
        assertEquals(listOf(CardLine.BeingRead(3)), cardLines(row(server(queued = 2, processing = 1)), stagedPages = 0))
        assertEquals(listOf(CardLine.NotOnPcYet), cardLines(row(server = null), stagedPages = 0))
        assertEquals(
            listOf(CardLine.DocumentRefused),
            cardLines(row(server = null, uploadError = "title too long"), stagedPages = 0),
        )
    }

    @Test
    fun `states are never merged, and what needs the user comes first`() {
        val lines = cardLines(
            row(server(queued = 1, processing = 1, errors = 2), pagesToUpload = 4, failedPages = 1),
            stagedPages = 3,
        )
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
