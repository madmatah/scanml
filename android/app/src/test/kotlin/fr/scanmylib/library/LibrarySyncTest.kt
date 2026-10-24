package fr.scanmylib.library

import fr.scanmylib.api.ApiFixtures
import fr.scanmylib.api.ApiJson
import fr.scanmylib.api.Document
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.Page
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.model.DocumentKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class LibrarySyncTest {
    @RunWith(Enclosed::class)
    class TheParseServerTimeFunction {
        @RunWith(Parameterized::class)
        class WhenTheTimeHasAnOffset(private val time: String, private val text: String, private val expected: Long) {
            private lateinit var serverTime: ServerTime

            @Before
            fun parseTheTime() {
                serverTime = ServerTime(parseServerTime(text))
            }

            @Test
            fun `should read it in milliseconds since the epoch`() {
                assertEquals(time, expected, serverTime.epochMilliseconds)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun times(): List<Array<Any>> = listOf(
                    arrayOf("a time with an offset", "2026-10-12T20:00:00+02:00", 1_791_828_000_000L),
                    arrayOf(
                        "a time with microseconds, read to the millisecond",
                        "2026-10-12T18:00:00.123456+00:00",
                        1_791_828_000_123L,
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheTimeCannotBeRead(private val time: String, private val text: String) {
            private lateinit var serverTime: ServerTime

            @Before
            fun parseTheTime() {
                serverTime = ServerTime(parseServerTime(text))
            }

            @Test
            fun `should give no time`() {
                assertNull(time, serverTime.epochMilliseconds)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun times(): List<Array<Any>> = listOf(
                    arrayOf("a word", "yesterday"),
                    arrayOf("a time without an offset", "2026-10-12T20:00:00"),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDocumentToEntityFunction {
        class WhenTheServerListsADocument {
            private lateinit var entity: DocumentEntity

            @Before
            fun cacheTheDocument() {
                entity = REMOTE_DOCUMENT.toEntity(confirmedAt = NOW_EPOCH_MILLISECONDS)
            }

            @Test
            fun `should take the title and the kind the server gives`() {
                assertEquals("Example Book", entity.title)
                assertEquals(DocumentKind.BOOK, entity.kind)
            }

            @Test
            fun `should date it at its last change on the server`() {
                assertEquals(1_791_828_000_000, entity.updatedAt)
            }

            @Test
            fun `should mark it as on the server, with nothing to upload`() {
                assertFalse(entity.needsUpload)
            }

            @Test
            fun `should confirm it at the time of the listing`() {
                assertEquals(NOW_EPOCH_MILLISECONDS, entity.confirmedAt)
            }

            @Test
            fun `should count its pages and those done`() {
                assertEquals(42, entity.server?.pages)
                assertEquals(40, entity.server?.done)
            }

            @Test
            fun `should show its coverage as the server labels it`() {
                assertEquals("1–12, 45–60", entity.server?.coverage)
            }

            @Test
            fun `should show its missing pages from the gaps the server reports`() {
                assertEquals("13–44", entity.server?.missing)
            }

            @Test
            fun `should count its unnumbered pages`() {
                assertEquals(3, entity.server?.unnumbered)
            }

            @Test
            fun `should show the cover the server gives`() {
                assertEquals("/api/pages/${ApiFixtures.PAGE_ID}/thumb", entity.server?.coverThumbUrl)
            }
        }
    }

    @RunWith(Enclosed::class)
    class ThePageToEntityFunction {
        class WhenTheServerListsAPage {
            private lateinit var page: ServerPageEntity

            @Before
            fun cacheThePage() {
                page = ApiJson.decodeFromString(Page.serializer(), ApiFixtures.PAGE).toEntity(position = 4)
            }

            @Test
            fun `should keep it at its rank in the document`() {
                assertEquals(4, page.position)
            }

            @Test
            fun `should keep its status`() {
                assertEquals(PageStatus.DONE, page.status)
            }

            @Test
            fun `should keep its label and how its number was found`() {
                assertEquals("42", page.pageLabel)
                assertEquals(NumberSource.DETECTED, page.numberSource)
            }

            @Test
            fun `should not mark it as a duplicate when it duplicates no page`() {
                assertFalse(page.duplicate)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheActionForMissingFunction {
        @RunWith(Parameterized::class)
        class WhenNoScanWaitsForUploadAndTheListingCannotShowItYetOrPagesWaitForConfirmation(
            private val document: String,
            private val cachedDocument: DocumentEntity,
            private val hasStagedPages: Boolean,
        ) {
            private lateinit var action: MissingDocumentAction

            @Before
            fun decideWhatToDo() {
                action = actionForMissing(
                    cachedDocument,
                    hasPagesToUpload = false,
                    hasStagedPages = hasStagedPages,
                    listedAt = LISTED_AT_EPOCH_MILLISECONDS,
                )
            }

            @Test
            fun `should keep it`() {
                assertEquals(document, MissingDocumentAction.KEEP, action)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun documents(): List<Array<Any>> = listOf(
                    arrayOf(
                        "a document not created on the server yet",
                        makeCachedDocument("new", needsUpload = true),
                        false,
                    ),
                    arrayOf(
                        "a document confirmed after the listing was requested",
                        makeCachedDocument("just-created", confirmedAt = NOW_EPOCH_MILLISECONDS),
                        false,
                    ),
                    arrayOf(
                        "a document deleted on the PC while pages wait for confirmation, " +
                            "since forgetting it would delete them and sending them creates it again",
                        makeCachedDocument("deleted-with-run"),
                        true,
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheDocumentWasDeletedOnThePcWithScansToUpload(
            private val document: String,
            private val cachedDocument: DocumentEntity,
            private val hasStagedPages: Boolean,
        ) {
            private lateinit var action: MissingDocumentAction

            @Before
            fun decideWhatToDo() {
                action = actionForMissing(
                    cachedDocument,
                    hasPagesToUpload = true,
                    hasStagedPages = hasStagedPages,
                    listedAt = LISTED_AT_EPOCH_MILLISECONDS,
                )
            }

            @Test
            fun `should create it again, to deliver them`() {
                assertEquals(document, MissingDocumentAction.RECREATE, action)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun documents(): List<Array<Any>> = listOf(
                    arrayOf("with no page waiting for confirmation", makeCachedDocument("deleted-with-scans"), false),
                    arrayOf(
                        "at once, even while pages wait for confirmation",
                        makeCachedDocument("deleted-with-both"),
                        true,
                    ),
                )
            }
        }

        class WhenTheDocumentWasDeletedOnThePcAndNothingWaitsForIt {
            private lateinit var action: MissingDocumentAction

            @Before
            fun decideWhatToDo() {
                action = actionForMissing(
                    makeCachedDocument("deleted"),
                    hasPagesToUpload = false,
                    hasStagedPages = false,
                    listedAt = LISTED_AT_EPOCH_MILLISECONDS,
                )
            }

            @Test
            fun `should forget it`() {
                assertEquals(MissingDocumentAction.DELETE, action)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheReconcileLibraryFunction {
        class WhenTheServerListsSomeOfTheCachedDocuments {
            private lateinit var upserts: Map<String, DocumentEntity>
            private lateinit var deletions: List<String>

            @Before
            fun mergeTheListing() {
                val update = reconcileLibrary(
                    local = listOf(
                        makeCachedDocument(REMOTE_DOCUMENT.id, title = "Old title", needsUpload = true),
                        makeCachedDocument("offline", needsUpload = true),
                        makeCachedDocument("deleted-with-scans"),
                        makeCachedDocument("deleted"),
                    ),
                    withPagesToUpload = setOf("deleted-with-scans"),
                    withStagedPages = emptySet(),
                    remote = listOf(REMOTE_DOCUMENT),
                    listedAt = LISTED_AT_EPOCH_MILLISECONDS,
                    now = NOW_EPOCH_MILLISECONDS,
                )
                upserts = update.upserts.associateBy { it.id }
                deletions = update.deletions
            }

            @Test
            fun `should update the listed document, and create again the one with scans to upload`() {
                assertEquals(setOf(REMOTE_DOCUMENT.id, "deleted-with-scans"), upserts.keys)
            }

            @Test
            fun `should give the listed document the server's state, which wins over the cache`() {
                assertEquals("Example Book", upserts[REMOTE_DOCUMENT.id]?.title)
            }

            @Test
            fun `should mark the listed document as on the server`() {
                assertEquals(false, upserts[REMOTE_DOCUMENT.id]?.needsUpload)
            }

            @Test
            fun `should mark the document to create again as not on the server`() {
                assertEquals(true, upserts["deleted-with-scans"]?.needsUpload)
                assertNull(upserts["deleted-with-scans"]?.server)
            }

            @Test
            fun `should forget the document deleted on the PC`() {
                assertEquals(listOf("deleted"), deletions)
            }
        }

        class WhenADocumentDeletedOnThePcHasPagesWaitingForConfirmation {
            private lateinit var upserts: List<DocumentEntity>
            private lateinit var deletions: List<String>

            @Before
            fun mergeTheListing() {
                val update = reconcileLibrary(
                    local = listOf(makeCachedDocument("deleted-with-run"), makeCachedDocument("deleted")),
                    withPagesToUpload = emptySet(),
                    withStagedPages = setOf("deleted-with-run"),
                    remote = emptyList(),
                    listedAt = LISTED_AT_EPOCH_MILLISECONDS,
                    now = NOW_EPOCH_MILLISECONDS,
                )
                upserts = update.upserts
                deletions = update.deletions
            }

            @Test
            fun `should neither update it nor create it again`() {
                assertEquals(emptyList<DocumentEntity>(), upserts)
            }

            @Test
            fun `should forget only the document without pages`() {
                assertEquals(listOf("deleted"), deletions)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheUploadedPagesGoneFunction {
        @RunWith(Parameterized::class)
        class WhenTheServerListsTheDocumentsPages(
            private val pages: String,
            private val uploadedBeforeRequest: List<String>,
            private val listed: List<Page>,
            private val expected: List<String>,
        ) {
            private lateinit var gonePageIds: List<String>

            @Before
            fun comparePages() {
                gonePageIds = uploadedPagesGone(uploadedBeforeRequest, listed)
            }

            @Test
            fun `should give the uploaded pages the server no longer lists, so that none stays shown as uploaded`() {
                assertEquals(pages, expected, gonePageIds)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun pages(): List<Array<Any>> = listOf(
                    arrayOf(
                        "a page uploaded before the request, then deleted on the PC, is gone",
                        listOf("a", "b"),
                        listOf(Page(id = "a", documentId = "doc"), Page(id = "x", documentId = "doc")),
                        listOf("b"),
                    ),
                    arrayOf(
                        "no page uploaded, none gone",
                        emptyList<String>(),
                        listOf(Page(id = "a", documentId = "doc"), Page(id = "x", documentId = "doc")),
                        emptyList<String>(),
                    ),
                    arrayOf(
                        "an uploaded page is gone when the server lists none",
                        listOf("a"),
                        emptyList<Page>(),
                        listOf("a"),
                    ),
                )
            }
        }
    }
}

private const val NOW_EPOCH_MILLISECONDS = 1_791_830_000_000
private const val LISTED_AT_EPOCH_MILLISECONDS = NOW_EPOCH_MILLISECONDS - 1_000

private val REMOTE_DOCUMENT: Document = ApiJson.decodeFromString(Document.serializer(), ApiFixtures.DOCUMENT)

private val SERVER_STATE = ServerDocumentState(
    pages = 1, done = 1, queued = 0, processing = 0, errors = 0, excluded = 0, duplicates = 0,
    coverage = "1", missing = "", unnumbered = 0, coverThumbUrl = null, folder = "",
)

/** A time that may be unreadable, held in a non-null value so that a test fails when no hook ran. */
private data class ServerTime(val epochMilliseconds: Long?)

private fun makeCachedDocument(
    id: String,
    title: String = "Document $id",
    needsUpload: Boolean = false,
    confirmedAt: Long = NOW_EPOCH_MILLISECONDS - 60_000,
) = DocumentEntity(
    id = id,
    title = title,
    author = "",
    kind = DocumentKind.DOCUMENT,
    unwarp = false,
    updatedAt = NOW_EPOCH_MILLISECONDS - 60_000,
    needsUpload = needsUpload,
    uploadError = null,
    confirmedAt = if (needsUpload) 0 else confirmedAt,
    server = if (needsUpload) null else SERVER_STATE,
)
