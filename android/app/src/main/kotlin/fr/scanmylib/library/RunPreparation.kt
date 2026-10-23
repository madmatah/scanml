package fr.scanmylib.library

import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch

/**
 * [imagesToAdd] counts the images of the copies not ended yet, running or waiting, since a copy adds
 * its images to the run only when it ends; [done] and [total] count every copy until none is left.
 */
data class Preparation(val done: Int, val total: Int, val imagesToAdd: Int, val isCancellable: Boolean)

sealed interface PreparationOutcome {
    data class PhotosSkipped(val unsupported: Int, val tooLarge: Int, val unreadable: Int) : PreparationOutcome

    data object ImportFailed : PreparationOutcome

    data object StorageFull : PreparationOutcome
}

data class PreparationState(val preparation: Preparation? = null, val outcome: PreparationOutcome? = null)

/** Where the images of a copy come from, which decides what the copy waits for. */
enum class CopySource {
    /** Google's scanner's pages: they exist nowhere else until they join the run. */
    SCANNED_PAGES,

    /** Photos that stay in the gallery: their copy can wait, and be canceled. */
    GALLERY_PHOTOS,
}

/**
 * Copies images into the runs of the documents in [scope], the application's: no screen's end
 * cancels a copy, since Google's scanner's pages exist nowhere else.
 */
class RunPreparation(private val scope: CoroutineScope) {

    private val lock = Any()

    /** The copies of each document since it last had none, the finished ones included. */
    private val copies = mutableMapOf<String, List<Copy>>()
    private val states = MutableStateFlow<Map<String, PreparationState>>(emptyMap())

    private inner class Copy(
        documentId: String,
        val source: CopySource,
        val total: Int,
        awaited: List<Job>,
        addPages: suspend (onProgress: (Int) -> Unit) -> PreparationOutcome?,
    ) {
        var done = 0
        var isFinished = false

        // Lazy, so that the copy is registered before it can run, and before a later one waits for it.
        val job: Job = scope.launch(start = CoroutineStart.LAZY) {
            awaited.joinAll()
            copyPages(documentId, this@Copy, addPages)
        }
    }

    fun observe(documentId: String): Flow<PreparationState> =
        states.map { it[documentId] ?: PreparationState() }.distinctUntilChanged()

    fun start(
        documentId: String,
        source: CopySource,
        total: Int,
        addPages: suspend (onProgress: (Int) -> Unit) -> PreparationOutcome?,
    ) {
        val copy = synchronized(lock) {
            val earlier = copies[documentId].orEmpty().filterNot { it.isFinished }
            val awaited = when (source) {
                CopySource.SCANNED_PAGES -> earlier.filter { it.source == CopySource.SCANNED_PAGES }
                CopySource.GALLERY_PHOTOS -> earlier
            }
            val copy = Copy(documentId, source, total, awaited.map { it.job }, addPages)
            copies[documentId] = copies[documentId].orEmpty() + copy
            publishLocked(documentId)
            copy
        }
        copy.job.invokeOnCompletion {
            synchronized(lock) {
                copy.isFinished = true
                publishLocked(documentId)
            }
        }
        copy.job.start()
    }

    private suspend fun copyPages(
        documentId: String,
        copy: Copy,
        addPages: suspend (onProgress: (Int) -> Unit) -> PreparationOutcome?,
    ) {
        val outcome = try {
            addPages { done ->
                synchronized(lock) {
                    copy.done = done
                    publishLocked(documentId)
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // Whatever the images' provider throws: IOException, SecurityException, but also the
            // runtime exceptions a content provider passes across the binder. Thrown in the
            // application's scope, it would end the app.
            Log.e(TAG, "could not copy the pages of the run", e)
            if (e.isStorageFull()) PreparationOutcome.StorageFull else PreparationOutcome.ImportFailed
        }
        if (outcome != null) record(documentId, outcome)
    }

    fun cancel(documentId: String) {
        val canceled = synchronized(lock) {
            val (canceled, kept) = copies[documentId].orEmpty().partition {
                it.source == CopySource.GALLERY_PHOTOS && !it.isFinished
            }
            copies[documentId] = kept
            publishLocked(documentId)
            canceled
        }
        // A read in progress (a cloud photo...) may take a while to give up: no need to wait.
        canceled.forEach { it.job.cancel() }
    }

    fun dismissOutcome(documentId: String) {
        synchronized(lock) { putStateLocked(documentId, stateLocked(documentId).copy(outcome = null)) }
    }

    private fun record(documentId: String, outcome: PreparationOutcome) {
        synchronized(lock) {
            val state = stateLocked(documentId)
            putStateLocked(documentId, state.copy(outcome = state.outcome.combinedWith(outcome)))
        }
    }

    private fun stateLocked(documentId: String): PreparationState = states.value[documentId] ?: PreparationState()

    /** A document with no copy and no outcome leaves the map, which would otherwise keep every document opened. */
    private fun putStateLocked(documentId: String, state: PreparationState) {
        states.value = if (state == PreparationState()) {
            states.value - documentId
        } else {
            states.value + (documentId to state)
        }
    }

    private fun publishLocked(documentId: String) {
        val documentCopies = copies[documentId].orEmpty()
        val waiting = documentCopies.filterNot { it.isFinished }
        val preparation = if (waiting.isEmpty()) {
            copies.remove(documentId)
            null
        } else {
            Preparation(
                done = documentCopies.sumOf { it.done },
                total = documentCopies.sumOf { it.total },
                imagesToAdd = waiting.sumOf { it.total },
                isCancellable = waiting.any { it.source == CopySource.GALLERY_PHOTOS },
            )
        }
        putStateLocked(documentId, stateLocked(documentId).copy(preparation = preparation))
    }

    private companion object {
        const val TAG = "RunPreparation"
    }
}

private fun PreparationOutcome?.combinedWith(next: PreparationOutcome): PreparationOutcome = when {
    this is PreparationOutcome.PhotosSkipped && next is PreparationOutcome.PhotosSkipped ->
        PreparationOutcome.PhotosSkipped(
            unsupported = unsupported + next.unsupported,
            tooLarge = tooLarge + next.tooLarge,
            unreadable = unreadable + next.unreadable,
        )

    this == null || next.severity >= severity -> next

    else -> this
}

private val PreparationOutcome.severity: Int get() = when (this) {
    is PreparationOutcome.PhotosSkipped -> 0
    PreparationOutcome.ImportFailed -> 1
    PreparationOutcome.StorageFull -> 2
}
