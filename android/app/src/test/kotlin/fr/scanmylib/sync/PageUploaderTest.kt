package fr.scanmylib.sync

import fr.scanmylib.api.PageUpload
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.UploadState
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class PageUploaderTest {
    @RunWith(Enclosed::class)
    class TheToUploadFunction {
        class WhenThePageHasANumber {
            private lateinit var upload: PageUpload

            @Before
            fun prepareTheUpload() {
                upload = queuedPage(pageNumberHint = PAGE_NUMBER).toUpload()
            }

            @Test
            fun `should send the page with its number, its document, its session and its place`() {
                assertEquals(
                    PageUpload(
                        documentId = DOCUMENT,
                        pageId = PAGE,
                        sessionId = SESSION,
                        seq = POSITION,
                        capturedAt = CAPTURED_AT,
                        pageNumberHint = PAGE_NUMBER,
                    ),
                    upload,
                )
            }
        }

        class WhenThePageHasNoNumber {
            private lateinit var upload: PageUpload

            @Before
            fun prepareTheUpload() {
                upload = queuedPage(pageNumberHint = null).toUpload()
            }

            @Test
            fun `should send it without a number, for the PC to read the printed one`() {
                assertEquals(
                    PageUpload(
                        documentId = DOCUMENT,
                        pageId = PAGE,
                        sessionId = SESSION,
                        seq = POSITION,
                        capturedAt = CAPTURED_AT,
                        pageNumberHint = null,
                    ),
                    upload,
                )
            }
        }
    }
}

private const val DOCUMENT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
private const val PAGE = "1b2c3d4e-5f60-4a7b-8c9d-0e1f2a3b4c5d"
private const val SESSION = "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f"
private const val CAPTURED_AT = "2026-10-12T20:15:30+02:00"
private const val PAGE_NUMBER = 33
private const val POSITION = 2

private fun queuedPage(pageNumberHint: Int?) = PendingPageEntity(
    id = PAGE,
    documentId = DOCUMENT,
    sessionId = SESSION,
    seq = POSITION,
    capturedAt = CAPTURED_AT,
    pageNumberHint = pageNumberHint,
    fileName = "$PAGE.jpg",
    state = UploadState.QUEUED,
    failure = null,
    lastError = null,
    attempts = 0,
    queuedAt = 0,
)
