package fr.scanmylib.library

import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadState
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class DocumentPagesTest {
    @RunWith(Enclosed::class)
    class TheMergeMethod {
        class WhenTheServerListsAPageOfThePhone {
            private lateinit var pages: DocumentPages

            @Before
            fun mergeThePages() {
                pages = DocumentPages.merge(
                    local = listOf(
                        localPage("a", UploadState.UPLOADED),
                        localPage("b", UploadState.UPLOADING),
                        localPage("c", UploadState.QUEUED),
                    ),
                    server = listOf(serverPage("x"), serverPage("a")),
                )
            }

            @Test
            fun `should show that page once, with the server's state`() {
                assertEquals(listOf("b", "c"), pages.local.map { it.id })
            }

            @Test
            fun `should show the server's pages in the server's order`() {
                assertEquals(listOf("x", "a"), pages.server.map { it.id })
            }
        }

        class WhenTheServerDoesNotListAnUploadedPageYet {
            private lateinit var pages: DocumentPages

            @Before
            fun mergeThePages() {
                pages = DocumentPages.merge(local = listOf(localPage("a", UploadState.UPLOADED)), server = emptyList())
            }

            @Test
            fun `should keep the page of the phone until the server lists it`() {
                assertEquals(listOf("a"), pages.local.map { it.id })
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheIsEmptyProperty {
        class WhenNeitherThePhoneNorTheServerHasPages {
            private var isEmpty by Delegates.notNull<Boolean>()

            @Before
            fun mergeNoPages() {
                isEmpty = DocumentPages.merge(emptyList(), emptyList()).isEmpty
            }

            @Test
            fun `should say there is nothing to show`() {
                assertTrue(isEmpty)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheServerThumbUrlFunction {
        class WhenTheCopyOfAnUploadedPageIsDeleted {
            private lateinit var thumbnail: PcThumbnail

            @Before
            fun readTheThumbnail() {
                thumbnail = PcThumbnail(localPage("a", UploadState.UPLOADED).copy(fileName = null).serverThumbUrl())
            }

            @Test
            fun `should show the PC's thumbnail, not an empty box until the PC lists the page`() {
                assertEquals("/api/pages/a/thumb", thumbnail.url)
            }
        }

        @RunWith(Parameterized::class)
        class WhenThePhoneHasTheImageOrThePageWasNeverUploaded(
            private val page: String,
            private val localPage: PendingPageEntity,
        ) {
            private lateinit var thumbnail: PcThumbnail

            @Before
            fun readTheThumbnail() {
                thumbnail = PcThumbnail(localPage.serverThumbUrl())
            }

            @Test
            fun `should show no thumbnail of the PC`() {
                assertNull(page, thumbnail.url)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun pages(): List<Array<Any>> = listOf(
                    arrayOf(
                        "an uploaded page whose copy is kept shows the phone's image",
                        localPage("kept", UploadState.UPLOADED),
                    ),
                    arrayOf("a queued page shows the phone's image", localPage("queued", UploadState.QUEUED)),
                    arrayOf(
                        "a page being uploaded shows the phone's image",
                        localPage("uploading", UploadState.UPLOADING),
                    ),
                    arrayOf(
                        "a page never uploaded has no thumbnail on the PC, even without its copy",
                        localPage("missing", UploadState.FAILED).copy(fileName = null),
                    ),
                )
            }
        }
    }
}

/** A thumbnail URL that may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class PcThumbnail(val url: String?)

private fun localPage(id: String, state: UploadState) = PendingPageEntity(
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

private fun serverPage(id: String) = ServerPageEntity(
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
