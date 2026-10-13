package fr.scanmylib.library

import fr.scanmylib.api.QueueCounts
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.db.UploadState
import kotlin.time.Duration
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.withTimeoutOrNull

// The library and document screens refresh themselves from the PC while work is in progress:
// pages being uploaded from the phone, then processed by the PC.

/** How often a visible screen refreshes while work is in progress (see [autoRefresh]). */
val AUTO_REFRESH_INTERVAL: Duration = 5.seconds

/** The longest wait between automatic refreshes that fail (PC switched off, other network...). */
private val MAX_AUTO_REFRESH_DELAY: Duration = 1.minutes

/** Doublings of the wait after failed refreshes, beyond which it is at its longest anyway. */
private const val MAX_DOUBLINGS = 10

/**
 * The work in progress that makes what a screen shows of the PC out of date.
 *
 * @property uploaded pages uploaded from this phone that the PC may not have listed to the screen.
 * @property uploading whether pages are waiting on the phone for upload, or being uploaded.
 * @property processing whether the PC was still processing pages (OCR queued or under way) when
 *   the screen last asked.
 */
data class PendingWork(
    val uploaded: Set<String> = emptySet(),
    val uploading: Boolean = false,
    val processing: Boolean = false,
)

/**
 * The work followed by the screen of [document]: its pages uploaded but not listed by the PC yet
 * (see [DocumentPages.merge]), those still to upload, and the processing of the document.
 */
fun documentWork(document: DocumentEntity?, pages: DocumentPages): PendingWork = PendingWork(
    uploaded = pages.local.filter { it.state == UploadState.UPLOADED }.mapTo(HashSet()) { it.id },
    uploading = pages.local.any { it.state == UploadState.QUEUED || it.state == UploadState.UPLOADING },
    processing = document?.server?.isProcessing == true,
)

/**
 * The work followed by the library screen: the pages uploaded but not listed by the PC yet
 * ([unlistedUploads]), those still to upload, and the processing of the documents and of the
 * PC's whole OCR queue ([queue], null if unknown).
 */
fun libraryWork(documents: List<LibraryRow>, unlistedUploads: Collection<String>, queue: QueueCounts?): PendingWork =
    PendingWork(
        uploaded = unlistedUploads.toSet(),
        uploading = documents.any { it.pagesToUpload > 0 },
        processing = (queue != null && queue.queued + queue.processing > 0) ||
            documents.any { it.document.server?.isProcessing == true },
    )

private val ServerDocumentState.isProcessing: Boolean get() = queued + processing > 0

/**
 * Refreshes a screen with [refresh] while [work] shows work in progress, until canceled: to run
 * while the screen is visible.
 * - Pages uploaded: refreshed as soon as the phone has no more to upload, and every [interval]
 *   until then, so that a long upload shows its progress without a request per page.
 * - Pages processed by the PC: refreshed every [interval] until it is done.
 *
 * Refreshes never overlap. [refresh] returns whether it succeeded: after a failure, the wait
 * before the next one doubles, up to a minute.
 */
suspend fun autoRefresh(work: Flow<PendingWork>, interval: Duration, refresh: suspend () -> Boolean) {
    coroutineScope {
        val latest = work.stateIn(this)
        // The uploaded pages known when the last successful refresh started: the PC listed them,
        // unless they were deleted on the PC (a page whose local copy is kept then stays on the
        // phone as uploaded: it must not be refreshed again and again).
        var refreshedUploads = emptySet<String>()
        var failures = 0
        fun hasNewUploads(work: PendingWork) = !refreshedUploads.containsAll(work.uploaded)
        fun isPending(work: PendingWork) = hasNewUploads(work) || work.processing
        fun uploadsDone(work: PendingWork) = hasNewUploads(work) && !work.uploading && failures == 0
        while (true) {
            // Nothing pending after failures: another refresh succeeded meanwhile (the user's...).
            if (!isPending(latest.value)) failures = 0
            val pending = latest.first { isPending(it) }
            if (!uploadsDone(pending)) {
                // Nothing pending any more also ends the wait: what the last refresh brought (the
                // PC done) often shows only after it returned, or the user refreshed meanwhile.
                val changed = withTimeoutOrNull(autoRefreshDelay(interval, failures)) {
                    latest.first { uploadsDone(it) || !isPending(it) }
                }
                if (changed != null && !isPending(changed)) continue
            }
            val uploaded = latest.value.uploaded
            if (refresh()) {
                refreshedUploads = uploaded
                failures = 0
            } else {
                failures++
            }
        }
    }
}

/** The wait before the next automatic refresh, after [failures] failed ones in a row. */
internal fun autoRefreshDelay(interval: Duration, failures: Int): Duration =
    minOf(interval * (1 shl failures.coerceIn(0, MAX_DOUBLINGS)), maxOf(interval, MAX_AUTO_REFRESH_DELAY))
