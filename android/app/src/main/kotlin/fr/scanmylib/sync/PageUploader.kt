package fr.scanmylib.sync

import fr.scanmylib.api.ApiException
import fr.scanmylib.api.DocumentUpsert
import fr.scanmylib.api.PageUpload
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ScanMyLibDatabase
import fr.scanmylib.db.UploadFailure
import fr.scanmylib.db.UploadState
import fr.scanmylib.library.ScanFileStore
import fr.scanmylib.library.toEntity
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import java.time.Clock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/** Outcome of an upload run. */
enum class UploadRunResult {
    /** Nothing left that can be uploaded now. */
    DONE,

    /** The server could not be reached or failed: try again later. */
    RETRY_LATER,

    /** The server refused the token: uploads wait for a new pairing. */
    UNAUTHORIZED,

    /** No server paired yet: the scans wait on the phone. */
    NOT_PAIRED,
}

/**
 * Uploads what waits on the phone: first the documents the server does not know yet (PUT,
 * idempotent), then their pages one by one, oldest first (POST, idempotent on the page id).
 * Every step is recorded in the database, so an interrupted run resumes where it stopped.
 */
class PageUploader(
    private val settings: SettingsRepository,
    private val api: (ServerConfig) -> ScanMyLibApi,
    database: ScanMyLibDatabase,
    private val scanFiles: ScanFileStore,
    private val clock: Clock,
) {
    private val documents = database.documentDao()
    private val pendingPages = database.pendingPageDao()

    // WorkManager may start a new run (REPLACE) while the canceled one is still winding down:
    // runs must not overlap, or both could work on the same page.
    private val runMutex = Mutex()

    suspend fun uploadPending(): UploadRunResult = runMutex.withLock { uploadAll() }

    private suspend fun uploadAll(): UploadRunResult {
        val current = settings.current()
        val server = current.server ?: return UploadRunResult.NOT_PAIRED
        val api = api(server)
        pendingPages.requeueInterrupted()
        // Documents created again after a 404 during this run; a second 404 fails the page.
        val recreatedDocuments = mutableSetOf<String>()
        while (true) {
            uploadDocuments(api)?.let { return it }
            val page = pendingPages.nextToUpload() ?: return UploadRunResult.DONE
            if (pendingPages.claimForUpload(page.id) == 0) continue // deleted by the user meanwhile

            val failure = uploadPage(api, page, current.keepLocalCopies) ?: continue
            when {
                failure.kind == UploadFailure.DOCUMENT_MISSING && recreatedDocuments.add(page.documentId) -> {
                    // Deleted on the server: create it again, then resend the page.
                    documents.markNeedsUpload(page.documentId)
                    pendingPages.recordFailure(page.id, UploadState.QUEUED, failure.kind, failure.detail)
                }
                failure.kind.retryable -> {
                    pendingPages.recordFailure(page.id, UploadState.QUEUED, failure.kind, failure.detail)
                    return if (failure.kind == UploadFailure.UNAUTHORIZED) {
                        UploadRunResult.UNAUTHORIZED
                    } else {
                        UploadRunResult.RETRY_LATER
                    }
                }
                else -> pendingPages.recordFailure(page.id, UploadState.FAILED, failure.kind, failure.detail)
            }
        }
    }

    /** Creates on the server the documents it does not know yet; returns a result to stop the run. */
    private suspend fun uploadDocuments(api: ScanMyLibApi): UploadRunResult? {
        for (document in documents.awaitingUpload()) {
            val body = DocumentUpsert(document.title, document.author, document.kind, document.unwarp)
            try {
                val created = api.upsertDocument(document.id, body)
                documents.upsert(listOf(created.toEntity(confirmedAt = clock.millis())))
            } catch (e: ApiException) {
                val failure = uploadFailureOf(e)
                when {
                    failure == UploadFailure.UNAUTHORIZED -> return UploadRunResult.UNAUTHORIZED
                    failure.retryable -> return UploadRunResult.RETRY_LATER
                    else -> documents.setUploadError(document.id, e.message)
                }
            }
        }
        return null
    }

    /** Uploads one claimed page; returns null on success. */
    private suspend fun uploadPage(api: ScanMyLibApi, page: PendingPageEntity, keepLocalCopy: Boolean): Failure? {
        val fileName = page.fileName
        val image = fileName?.let(scanFiles::file)
        if (image == null || !withContext(Dispatchers.IO) { image.isFile }) {
            return Failure(UploadFailure.FILE_MISSING, fileName)
        }
        val upload = PageUpload(
            documentId = page.documentId,
            pageId = page.id,
            sessionId = page.sessionId,
            seq = page.seq,
            capturedAt = page.capturedAt,
            pageNumberHint = page.pageNumberHint,
        )
        try {
            api.uploadPage(upload, image)
        } catch (e: ApiException) {
            return Failure(uploadFailureOf(e), e.message)
        }
        if (keepLocalCopy) {
            pendingPages.markUploaded(page.id, keptFileName = fileName)
        } else {
            pendingPages.markUploaded(page.id, keptFileName = null)
            withContext(Dispatchers.IO) { scanFiles.delete(fileName) }
        }
        return null
    }

    private data class Failure(val kind: UploadFailure, val detail: String?)
}

/** Classifies an API error for the upload queue: retry later, wait for the user, or give up. */
internal fun uploadFailureOf(e: ApiException): UploadFailure = when (e) {
    is ApiException.Unreachable -> UploadFailure.NETWORK
    is ApiException.InvalidResponse -> UploadFailure.SERVER_ERROR
    is ApiException.Unauthorized -> UploadFailure.UNAUTHORIZED
    is ApiException.Http -> when (e.code) {
        404 -> UploadFailure.DOCUMENT_MISSING
        408, 429 -> UploadFailure.SERVER_ERROR
        413 -> UploadFailure.TOO_LARGE
        415 -> UploadFailure.UNSUPPORTED_TYPE
        in 500..599 -> UploadFailure.SERVER_ERROR
        else -> UploadFailure.REJECTED
    }
}
