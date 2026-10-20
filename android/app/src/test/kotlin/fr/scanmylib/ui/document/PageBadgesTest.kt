package fr.scanmylib.ui.document

import fr.scanmylib.R
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadState
import fr.scanmylib.ui.components.PageBadge
import fr.scanmylib.ui.components.StatusTone
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class PageBadgesTest {
    @RunWith(Enclosed::class)
    class ThePickBadgeFunctionOfAPageOnThePc {
        @RunWith(Parameterized::class)
        class WhenThePageIsInAState(
            private val name: String,
            private val page: ServerPageEntity,
            private val expectedBadges: List<PageBadge?>,
        ) {
            private lateinit var badges: List<PageBadge?>

            @Before
            fun pickTheBadge() {
                badges = listOf(page.pickBadge())
            }

            @Test
            fun `should show the badge of its state`() {
                assertEquals(name, expectedBadges, badges)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun rows(): List<Array<Any>> = PAGE_ON_THE_PC_ROWS.map { arrayOf(it.name, it.page, listOf(it.badge)) }
            }
        }

        class WhenItsRowsAreCounted {
            @Test
            fun `should have a row for each status of a page on the PC`() {
                assertEquals(PageStatus.entries.toSet(), PAGE_ON_THE_PC_ROWS.map { it.page.status }.toSet())
            }
        }
    }

    @RunWith(Enclosed::class)
    class ThePickBadgeFunctionOfAPageOnThePhone {
        @RunWith(Parameterized::class)
        class WhenThePageIsInAState(
            private val name: String,
            private val page: PendingPageEntity,
            private val expectedBadge: PageBadge,
        ) {
            private lateinit var badge: PageBadge

            @Before
            fun pickTheBadge() {
                badge = page.pickBadge()
            }

            @Test
            fun `should show the badge of its state`() {
                assertEquals(name, expectedBadge, badge)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun rows(): List<Array<Any>> = PAGE_ON_THE_PHONE_ROWS.map { arrayOf(it.name, it.page, it.badge) }
            }
        }

        class WhenItsRowsAreCounted {
            @Test
            fun `should have a row for each state of an upload`() {
                assertEquals(UploadState.entries.toSet(), PAGE_ON_THE_PHONE_ROWS.map { it.page.state }.toSet())
            }
        }
    }
}

private class PageOnThePcRow(val name: String, val page: ServerPageEntity, val badge: PageBadge?)

private class PageOnThePhoneRow(val name: String, val page: PendingPageEntity, val badge: PageBadge)

private val PAGE_ON_THE_PC_ROWS = listOf(
    PageOnThePcRow(
        "a page whose text is ready shows none, so that the normal state stays quiet",
        makePageOnThePc(PageStatus.DONE),
        null,
    ),
    PageOnThePcRow(
        "a page queued on the PC says so, in a neutral tone",
        makePageOnThePc(PageStatus.QUEUED),
        PageBadge(R.string.page_badge_queued, R.drawable.ic_schedule, StatusTone.NEUTRAL),
    ),
    PageOnThePcRow(
        "a page being read says so, in the tone of work in progress",
        makePageOnThePc(PageStatus.PROCESSING),
        PageBadge(R.string.page_status_processing, R.drawable.ic_autorenew, StatusTone.IN_PROGRESS),
    ),
    PageOnThePcRow(
        "a page whose text could not be read says it failed, in the tone of a failure",
        makePageOnThePc(PageStatus.ERROR),
        PageBadge(R.string.page_badge_failed, R.drawable.ic_error, StatusTone.FAILURE),
    ),
    PageOnThePcRow(
        "a page whose status the app does not know says so, in a neutral tone",
        makePageOnThePc(PageStatus.UNKNOWN),
        PageBadge(R.string.page_status_unknown, R.drawable.ic_schedule, StatusTone.NEUTRAL),
    ),
    PageOnThePcRow(
        "a duplicate says so, since it is set aside",
        makePageOnThePc(PageStatus.DONE, isDuplicate = true),
        PageBadge(R.string.page_duplicate, R.drawable.ic_content_copy, StatusTone.NEUTRAL),
    ),
    PageOnThePcRow(
        "an excluded page says so, since it is set aside",
        makePageOnThePc(PageStatus.DONE, isExcluded = true),
        PageBadge(R.string.page_excluded, R.drawable.ic_block, StatusTone.NEUTRAL),
    ),
)

private val PAGE_ON_THE_PHONE_ROWS = listOf(
    PageOnThePhoneRow(
        "a page waiting to upload says so, in a neutral tone",
        makePageOnThePhone(UploadState.QUEUED),
        PageBadge(R.string.upload_badge_queued, R.drawable.ic_schedule, StatusTone.NEUTRAL),
    ),
    PageOnThePhoneRow(
        "a page uploading says so, in a neutral tone",
        makePageOnThePhone(UploadState.UPLOADING),
        PageBadge(R.string.upload_badge_uploading, R.drawable.ic_cloud_upload, StatusTone.NEUTRAL),
    ),
    PageOnThePhoneRow(
        "a page the PC rejected says so, in the tone of a failure",
        makePageOnThePhone(UploadState.FAILED),
        PageBadge(R.string.upload_badge_failed, R.drawable.ic_error, StatusTone.FAILURE),
    ),
    PageOnThePhoneRow(
        "an uploaded page still shows one, since its text is not ready yet",
        makePageOnThePhone(UploadState.UPLOADED),
        PageBadge(R.string.upload_badge_uploaded, R.drawable.ic_cloud_done, StatusTone.NEUTRAL),
    ),
)

private fun makePageOnThePc(status: PageStatus, isDuplicate: Boolean = false, isExcluded: Boolean = false) =
    ServerPageEntity(
        id = "page",
        documentId = "book",
        position = 0,
        status = status,
        error = null,
        pageLabel = "12",
        numberSource = NumberSource.DETECTED,
        excluded = isExcluded,
        duplicate = isDuplicate,
        thumbUrl = null,
    )

private fun makePageOnThePhone(state: UploadState) = PendingPageEntity(
    id = "page",
    documentId = "book",
    sessionId = "session",
    seq = 1,
    capturedAt = "2026-10-12T10:00:00+02:00",
    pageNumberHint = 12,
    fileName = null,
    state = state,
    failure = null,
    lastError = null,
    attempts = 0,
    queuedAt = 0,
)
