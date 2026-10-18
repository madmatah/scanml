package fr.scanmylib.sync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import fr.scanmylib.ScanMyLibApplication

/** Runs [PageUploader] for [SyncScheduler]; WorkManager handles constraints and retries. */
class UploadWorker(context: Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {

    override suspend fun doWork(): Result {
        val uploader = (applicationContext as ScanMyLibApplication).container.uploader
        return when (uploader.uploadPending()) {
            UploadRunResult.DONE, UploadRunResult.NOT_PAIRED -> Result.success()

            UploadRunResult.RETRY_LATER -> Result.retry()

            // Retrying cannot help until the user pairs again, which restarts the uploads.
            UploadRunResult.UNAUTHORIZED -> Result.failure()
        }
    }
}
