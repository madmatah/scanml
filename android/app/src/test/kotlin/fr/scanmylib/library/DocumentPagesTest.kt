package fr.scanmylib.library

import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DocumentPagesTest {

    @Test
    fun `shows each page once, with the server state when the server lists it`() {
        val pages = DocumentPages.merge(
            local = listOf(
                local("a", UploadState.UPLOADED),
                local("b", UploadState.UPLOADING),
                local("c", UploadState.QUEUED),
            ),
            server = listOf(server("x"), server("a")),
        )
        assertEquals(listOf("b", "c"), pages.local.map { it.id })
        assertEquals(listOf("x", "a"), pages.server.map { it.id })
    }

    @Test
    fun `keeps uploaded pages until the server lists them`() {
        val pages = DocumentPages.merge(local = listOf(local("a", UploadState.UPLOADED)), server = emptyList())
        assertEquals(listOf("a"), pages.local.map { it.id })
    }

    @Test
    fun `knows when there is nothing to show`() {
        assertTrue(DocumentPages.merge(emptyList(), emptyList()).isEmpty)
    }

    @Test
    fun `an uploaded page whose copy is deleted shows the PC's thumbnail`() {
        // The report: once uploaded, the pages were deleted from the phone ("Keep scans on the
        // phone" is off by default) and showed as empty boxes until the PC listed them.
        assertEquals("/api/pages/a/thumb", local("a", UploadState.UPLOADED).copy(fileName = null).serverThumbUrl())
        // The phone's image while it has one.
        assertNull(local("kept", UploadState.UPLOADED).serverThumbUrl())
        assertNull(local("queued", UploadState.QUEUED).serverThumbUrl())
        assertNull(local("uploading", UploadState.UPLOADING).serverThumbUrl())
        // Never uploaded: the PC has no thumbnail.
        assertNull(local("missing", UploadState.FAILED).copy(fileName = null).serverThumbUrl())
    }

    private fun local(id: String, state: UploadState) = PendingPageEntity(
        id = id,
        documentId = "doc",
        sessionId = "session",
        seq = 1,
        capturedAt = "2026-10-12T20:15:30+02:00",
        pageNumberHint = null,
        fileName = "$id.jpg",
        state = state,
        failure = null,
        lastError = null,
        attempts = 0,
        queuedAt = 0,
    )

    private fun server(id: String) = ServerPageEntity(
        id = id,
        documentId = "doc",
        position = 0,
        status = PageStatus.QUEUED,
        error = null,
        pageLabel = null,
        numberSource = null,
        excluded = false,
        duplicate = false,
        thumbUrl = null,
    )
}
