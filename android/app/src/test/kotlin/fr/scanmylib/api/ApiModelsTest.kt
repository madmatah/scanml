package fr.scanmylib.api

import fr.scanmylib.model.DocumentKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class ApiModelsTest {

    @Test
    fun `decodes the health and status examples`() {
        assertEquals(Health(name = "ScanMyLib", api = 1), ApiJson.decodeFromString(Health.serializer(), ApiFixtures.HEALTH))
        val withApk = """
            {"name": "ScanMyLib", "version": "0.8.0", "api": 1, "apk": {"application_id": "fr.scanmylib",
             "version": "0.8.0", "version_code": 800, "sha256": "${"ab".repeat(32)}", "size": 1234,
             "path": "/download/scanmylib.apk"}}
        """.trimIndent()
        assertEquals(
            PublishedApk("fr.scanmylib", "0.8.0", 800, "ab".repeat(32), 1234, "/download/scanmylib.apk"),
            ApiJson.decodeFromString(Health.serializer(), withApk).apk,
        )
        assertNull(ApiJson.decodeFromString(Health.serializer(), """{"name": "ScanMyLib", "api": 1, "apk": null}""").apk)
        // A malformed description leaves the health check as it is: pairing still works.
        val malformed = ApiJson.decodeFromString(Health.serializer(), """{"name": "ScanMyLib", "api": 1, "apk": {"version": 3}}""")
        assertEquals("ScanMyLib", malformed.name)
        assertNull(malformed.apk)
        val status = ApiJson.decodeFromString(ServerStatus.serializer(), ApiFixtures.STATUS)
        assertEquals("0.1.0", status.version)
        assertEquals("idle", status.ocr.state)
        assertNull(status.ocr.lastError)
        assertEquals(QueueCounts(queued = 3, processing = 1), status.queue)
    }

    @Test
    fun `decodes the document example`() {
        val document = ApiJson.decodeFromString(Document.serializer(), ApiFixtures.DOCUMENT)
        assertEquals(ApiFixtures.DOCUMENT_ID, document.id)
        assertEquals("Example Book", document.title)
        assertEquals("Jane Doe", document.author)
        assertEquals(DocumentKind.BOOK, document.kind)
        assertFalse(document.unwarp)
        assertEquals("2026-10-12T20:00:00+02:00", document.updatedAt)
        assertEquals(DocumentStats(pages = 42, done = 40, queued = 1, processing = 1), document.stats)
        assertEquals("1–12, 45–60", document.coverage.label)
        assertEquals(listOf(listOf(13, 44)), document.coverage.gaps)
        assertEquals(3, document.coverage.unnumbered)
        assertEquals("/api/pages/${ApiFixtures.PAGE_ID}/thumb", document.coverThumbUrl)
        assertEquals("/home/user/Documents/ScanMyLib/example-book", document.folder)
    }

    @Test
    fun `decodes the page example`() {
        val page = ApiJson.decodeFromString(Page.serializer(), ApiFixtures.PAGE)
        assertEquals(ApiFixtures.PAGE_ID, page.id)
        assertEquals(ApiFixtures.DOCUMENT_ID, page.documentId)
        assertEquals(PageStatus.DONE, page.status)
        assertEquals("42", page.pageLabel)
        assertEquals(NumberSource.DETECTED, page.numberSource)
        assertFalse(page.excluded)
        assertNull(page.duplicateOf)
        assertNull(page.error)
        assertEquals("/api/pages/${ApiFixtures.PAGE_ID}/thumb", page.thumbUrl)
    }

    @Test
    fun `tolerates values and fields added by newer servers`() {
        val page = ApiJson.decodeFromString(
            Page.serializer(),
            """{"id": "p", "document_id": "d", "status": "archived", "number_source": "ai", "new_field": [1, 2]}""",
        )
        assertEquals(PageStatus.UNKNOWN, page.status)
        assertNull(page.numberSource)

        val document = ApiJson.decodeFromString(Document.serializer(), """{"id": "d", "title": "T", "kind": "magazine"}""")
        assertEquals(DocumentKind.DOCUMENT, document.kind)
        assertEquals(DocumentStats(), document.stats)
    }

    @Test
    fun `encodes the document upsert body`() {
        val json = ApiJson.encodeToString(
            DocumentUpsert.serializer(),
            DocumentUpsert(title = "Example Book", author = "Jane Doe", kind = DocumentKind.BOOK, unwarp = true),
        )
        assertEquals("""{"title":"Example Book","author":"Jane Doe","kind":"book","unwarp":true}""", json)
    }
}
