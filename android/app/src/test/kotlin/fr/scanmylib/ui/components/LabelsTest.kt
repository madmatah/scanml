package fr.scanmylib.ui.components

import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.UploadState
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class LabelsTest {
    @RunWith(Enclosed::class)
    class TheTonePropertyOfAPageStatus {
        @RunWith(Parameterized::class)
        class WhenReadForAStatus(
            private val name: String,
            private val status: PageStatus,
            private val expectedTone: StatusTone,
        ) {
            private lateinit var tone: StatusTone

            @Before
            fun readTheTone() {
                tone = status.tone
            }

            @Test
            fun `should say what the state of the page asks of the user`() {
                assertEquals(name, expectedTone, tone)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun statuses(): List<Array<Any>> = PAGE_STATUS_TONES.map { arrayOf(it.name, it.status, it.tone) }
            }
        }

        class WhenItsRowsAreCounted {
            @Test
            fun `should have a row for each status of a page`() {
                assertEquals(PageStatus.entries.toSet(), PAGE_STATUS_TONES.map { it.status }.toSet())
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheTonePropertyOfAnUploadState {
        @RunWith(Parameterized::class)
        class WhenReadForAState(
            private val name: String,
            private val state: UploadState,
            private val expectedTone: StatusTone,
        ) {
            private lateinit var tone: StatusTone

            @Before
            fun readTheTone() {
                tone = state.tone
            }

            @Test
            fun `should say what the upload of the page asks of the user`() {
                assertEquals(name, expectedTone, tone)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun states(): List<Array<Any>> = UPLOAD_STATE_TONES.map { arrayOf(it.name, it.state, it.tone) }
            }
        }

        class WhenItsRowsAreCounted {
            @Test
            fun `should have a row for each state of an upload`() {
                assertEquals(UploadState.entries.toSet(), UPLOAD_STATE_TONES.map { it.state }.toSet())
            }
        }
    }
}

private class PageStatusTone(val name: String, val status: PageStatus, val tone: StatusTone)

private class UploadStateTone(val name: String, val state: UploadState, val tone: StatusTone)

private val PAGE_STATUS_TONES = listOf(
    PageStatusTone(
        "a page queued on the PC is neutral, since it goes on by itself",
        PageStatus.QUEUED,
        StatusTone.NEUTRAL,
    ),
    PageStatusTone(
        "a page being read is in progress, since the PC works on it",
        PageStatus.PROCESSING,
        StatusTone.IN_PROGRESS,
    ),
    PageStatusTone(
        "a page whose text is ready is neutral, since it asks nothing",
        PageStatus.DONE,
        StatusTone.NEUTRAL,
    ),
    PageStatusTone(
        "a page whose text could not be read is a failure, since the user must act",
        PageStatus.ERROR,
        StatusTone.FAILURE,
    ),
    PageStatusTone(
        "a page of an unknown status is neutral, since the app cannot tell",
        PageStatus.UNKNOWN,
        StatusTone.NEUTRAL,
    ),
)

private val UPLOAD_STATE_TONES = listOf(
    UploadStateTone(
        "a page waiting to upload is neutral, since it goes on by itself",
        UploadState.QUEUED,
        StatusTone.NEUTRAL,
    ),
    UploadStateTone(
        "a page uploading is neutral, since it goes on by itself",
        UploadState.UPLOADING,
        StatusTone.NEUTRAL,
    ),
    UploadStateTone(
        "a page the PC rejected is a failure, since the user must act",
        UploadState.FAILED,
        StatusTone.FAILURE,
    ),
    UploadStateTone(
        "an uploaded page is neutral, since the PC takes it from there",
        UploadState.UPLOADED,
        StatusTone.NEUTRAL,
    ),
)
