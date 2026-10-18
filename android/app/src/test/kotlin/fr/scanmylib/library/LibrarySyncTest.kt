package fr.scanmylib.library

import fr.scanmylib.api.ApiFixtures
import fr.scanmylib.api.ApiJson
import fr.scanmylib.api.Document
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.Page
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.model.DocumentKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LibrarySyncTest {

    @Test
    fun `formats page ranges like the server`() {
        assertEquals("13–44", formatPageRanges(listOf(listOf(13, 44))))
        assertEquals("2, 5–9", formatPageRanges(listOf(listOf(2, 2), listOf(5, 9))))
        assertEquals("", formatPageRanges(emptyList()))
        assertEquals("7", formatPageRanges(listOf(listOf(1, 2, 3), listOf(7, 7))))
    }

    @Test
    fun `parses server times with an offset`() {
        assertEquals(1_791_828_000_000, parseServerTime("2026-10-12T20:00:00+02:00"))
        assertEquals(1_791_828_000_123, parseServerTime("2026-10-12T18:00:00.123456+00:00"))
        assertNull(parseServerTime("yesterday"))
        assertNull(parseServerTime("2026-10-12T20:00:00"))
    }

    @Test
    fun `caches a server document`() {
        val document = ApiJson.decodeFromString(Document.serializer(), ApiFixtures.DOCUMENT)
        val entity = document.toEntity(confirmedAt = NOW)
        assertEquals("Example Book", entity.title)
        assertEquals(DocumentKind.BOOK, entity.kind)
        assertEquals(1_791_828_000_000, entity.updatedAt)
        assertFalse(entity.needsUpload)
        assertEquals(NOW, entity.confirmedAt)
        val server = checkNotNull(entity.server)
        assertEquals(42, server.pages)
        assertEquals(40, server.done)
        assertEquals("1–12, 45–60", server.coverage)
        assertEquals("13–44", server.missing)
        assertEquals(3, server.unnumbered)
        assertEquals("/api/pages/${ApiFixtures.PAGE_ID}/thumb", server.coverThumbUrl)
    }

    @Test
    fun `caches a server page at its rank`() {
        val page = ApiJson.decodeFromString(Page.serializer(), ApiFixtures.PAGE).toEntity(position = 4)
        assertEquals(4, page.position)
        assertEquals(PageStatus.DONE, page.status)
        assertEquals("42", page.pageLabel)
        assertEquals(NumberSource.DETECTED, page.numberSource)
        assertFalse(page.duplicate)
    }

    @Test
    fun `decides what to do with documents the server does not list`() {
        val listedAt = NOW - 1_000
        assertEquals(
            MissingDocumentAction.KEEP,
            actionForMissing(
                local("new", needsUpload = true),
                hasPagesToUpload = false,
                hasStagedPages = false,
                listedAt,
            ),
        )
        assertEquals(
            MissingDocumentAction.KEEP,
            actionForMissing(local("just-created", confirmedAt = NOW), false, hasStagedPages = false, listedAt),
        )
        assertEquals(
            MissingDocumentAction.RECREATE,
            actionForMissing(local("deleted-with-scans"), hasPagesToUpload = true, hasStagedPages = false, listedAt),
        )
        assertEquals(
            MissingDocumentAction.DELETE,
            actionForMissing(local("deleted"), hasPagesToUpload = false, hasStagedPages = false, listedAt),
        )
    }

    @Test
    fun `pages waiting for confirmation keep a document deleted on the PC`() {
        val listedAt = NOW - 1_000
        // Forgetting the document would delete them; sending them creates it again.
        assertEquals(
            MissingDocumentAction.KEEP,
            actionForMissing(local("deleted-with-run"), hasPagesToUpload = false, hasStagedPages = true, listedAt),
        )
        // Pages already queued still bring it back right away.
        assertEquals(
            MissingDocumentAction.RECREATE,
            actionForMissing(local("deleted-with-both"), hasPagesToUpload = true, hasStagedPages = true, listedAt),
        )
        val update = reconcileLibrary(
            local = listOf(local("deleted-with-run"), local("deleted")),
            withPagesToUpload = emptySet(),
            withStagedPages = setOf("deleted-with-run"),
            remote = emptyList(),
            listedAt = listedAt,
            now = NOW,
        )
        assertEquals(emptyList<DocumentEntity>(), update.upserts)
        assertEquals(listOf("deleted"), update.deletions)
    }

    @Test
    fun `forgets uploaded pages that the server no longer lists`() {
        val listed = listOf(Page(id = "a", documentId = "doc"), Page(id = "x", documentId = "doc"))
        // "b" was uploaded before the request but deleted on the PC: it must not stay shown as uploaded.
        assertEquals(listOf("b"), uploadedPagesGone(uploadedBeforeRequest = listOf("a", "b"), listed = listed))
        assertEquals(emptyList<String>(), uploadedPagesGone(uploadedBeforeRequest = emptyList(), listed = listed))
        assertEquals(listOf("a"), uploadedPagesGone(uploadedBeforeRequest = listOf("a"), listed = emptyList()))
    }

    @Test
    fun `merges the server listing into the cache`() {
        val remote = ApiJson.decodeFromString(Document.serializer(), ApiFixtures.DOCUMENT)
        val update = reconcileLibrary(
            local = listOf(
                local(remote.id, title = "Old title", needsUpload = true),
                local("offline", needsUpload = true),
                local("deleted-with-scans"),
                local("deleted"),
            ),
            withPagesToUpload = setOf("deleted-with-scans"),
            withStagedPages = emptySet(),
            remote = listOf(remote),
            listedAt = NOW - 1_000,
            now = NOW,
        )

        val upserts = update.upserts.associateBy { it.id }
        assertEquals(setOf(remote.id, "deleted-with-scans"), upserts.keys)
        val listed = checkNotNull(upserts[remote.id])
        assertEquals("the server state wins", "Example Book", listed.title)
        assertFalse(listed.needsUpload)
        val recreated = checkNotNull(upserts["deleted-with-scans"])
        assertTrue(recreated.needsUpload)
        assertNull(recreated.server)
        assertEquals(listOf("deleted"), update.deletions)
    }

    private fun local(
        id: String,
        title: String = "Document $id",
        needsUpload: Boolean = false,
        confirmedAt: Long = NOW - 60_000,
    ) = DocumentEntity(
        id = id,
        title = title,
        author = "",
        kind = DocumentKind.DOCUMENT,
        unwarp = false,
        updatedAt = NOW - 60_000,
        needsUpload = needsUpload,
        uploadError = null,
        confirmedAt = if (needsUpload) 0 else confirmedAt,
        server = if (needsUpload) null else SERVER_STATE,
    )

    private companion object {
        const val NOW = 1_791_830_000_000
        val SERVER_STATE = ServerDocumentState(
            pages = 1, done = 1, queued = 0, processing = 0, errors = 0, excluded = 0, duplicates = 0,
            coverage = "1", missing = "", unnumbered = 0, coverThumbUrl = null, folder = "",
        )
    }
}
