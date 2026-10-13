package fr.scanmylib.sync

import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequest
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.await
import fr.scanmylib.db.ScanMyLibDatabase
import fr.scanmylib.settings.SettingsRepository
import java.time.Duration
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Schedules the upload of local documents and scans as a unique WorkManager work: it runs when
 * the network allows (any network, or Wi-Fi only), survives app restarts, and retries with a
 * linear backoff while the PC is unreachable.
 */
class SyncScheduler(
    private val workManager: WorkManager,
    private val settings: SettingsRepository,
    private val database: ScanMyLibDatabase,
) {
    // Serializes the read-then-enqueue sequences of this process.
    private val mutex = Mutex()

    /** Uploads everything waiting as soon as possible. */
    suspend fun requestSync() {
        mutex.withLock {
            val states = workManager.getWorkInfosForUniqueWorkFlow(WORK_NAME).first().map { it.state }
            val policy = enqueuePolicy(states) ?: return
            workManager.enqueueUniqueWork(WORK_NAME, policy, uploadRequest()).await()
        }
    }

    /** [requestSync] if anything waits for upload; cheap enough for every return to the app. */
    suspend fun requestSyncIfPending() {
        val pending = database.documentDao().countAwaitingUpload() + database.pendingPageDao().countAwaitingUpload()
        if (pending > 0) requestSync()
    }

    /** Starts over with the current settings (network constraint, server), interrupting a running upload. */
    suspend fun restart() {
        mutex.withLock {
            workManager.enqueueUniqueWork(WORK_NAME, ExistingWorkPolicy.REPLACE, uploadRequest()).await()
        }
    }

    suspend fun cancel() {
        mutex.withLock { workManager.cancelUniqueWork(WORK_NAME).await() }
    }

    private suspend fun uploadRequest(): OneTimeWorkRequest {
        val network = if (settings.current().wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED
        return OneTimeWorkRequestBuilder<UploadWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(network).build())
            // Linear, not exponential: away from the PC the network constraint stays met, so only
            // the backoff decides when the next try comes. Doubling from 30 s reaches WorkManager's
            // 5-hour cap after 4 hours away, and scans would then wait hours once back home.
            // Linear steps of 30 s: the next try comes within ~20 min after 8 hours away.
            .setBackoffCriteria(BackoffPolicy.LINEAR, BACKOFF_STEP)
            .build()
    }

    private companion object {
        const val WORK_NAME = "upload"
        val BACKOFF_STEP: Duration = Duration.ofSeconds(30)
    }
}

/**
 * How to enqueue a new upload run, given the states of the existing unique work, or null when
 * nothing needs to be enqueued:
 * - no run in progress: replace any waiting run, which also cancels a pending backoff delay
 *   (the user is back, the PC may be on again);
 * - a run in progress: append one follow-up run, so that pages queued after the running upload
 *   looked for work are not left behind, unless a follow-up is already waiting.
 */
internal fun enqueuePolicy(states: List<WorkInfo.State>): ExistingWorkPolicy? = when {
    WorkInfo.State.RUNNING !in states -> ExistingWorkPolicy.REPLACE
    states.any { it == WorkInfo.State.ENQUEUED || it == WorkInfo.State.BLOCKED } -> null
    else -> ExistingWorkPolicy.APPEND_OR_REPLACE
}
