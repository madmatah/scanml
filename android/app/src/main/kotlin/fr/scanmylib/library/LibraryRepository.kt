package fr.scanmylib.library

import androidx.room.withTransaction
import fr.scanmylib.api.ApiException
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ScanMyLibDatabase
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.sync.SyncScheduler
import java.io.File
import java.time.Clock
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

/** Local copies of scans kept after upload. */
data class KeptCopies(val count: Int, val bytes: Long)

/**
 * The document library: the local cache of the server's documents and pages, documents created on
 * the phone, and the local scans waiting for upload.
 */
class LibraryRepository(
    private val database: ScanMyLibDatabase,
    private val api: (ServerConfig) -> ScanMyLibApi,
    private val scanFiles: ScanFileStore,
    private val staging: StagingArea,
    private val syncScheduler: SyncScheduler,
    private val clock: Clock,
) {
    private val documents = database.documentDao()
    private val pendingPages = database.pendingPageDao()
    private val serverPages = database.serverPageDao()

    fun observeLibrary(): Flow<List<LibraryRow>> = documents.observeLibrary()

    fun observeDocument(id: String): Flow<DocumentEntity?> = documents.observe(id)

    fun observeScannedPages(documentId: String): Flow<List<IntRange>> = documents.observe(documentId)
        .map { document -> document?.server?.coverage?.let(::parsePageRanges).orEmpty() }
        .distinctUntilChanged()

    fun observePages(documentId: String): Flow<DocumentPages> = combine(
        pendingPages.observeForDocument(documentId),
        serverPages.observeForDocument(documentId),
        DocumentPages::merge,
    )

    /** Ids of the uploaded pages that the cached pages of their document do not list yet. */
    fun observeUnlistedUploads(): Flow<List<String>> = pendingPages.observeUnlistedUploads()

    /** The image of a local scan, if still on the phone. */
    fun imageOf(page: PendingPageEntity): File? = page.fileName?.let(scanFiles::file)

    fun observeKeptCopies(): Flow<KeptCopies> = pendingPages.observeKeptCopies()
        .map { fileNames -> KeptCopies(fileNames.size, scanFiles.sizeOf(fileNames)) }
        .flowOn(Dispatchers.IO)

    /** Creates a document on the phone and returns its id; the next upload creates it on the server. */
    suspend fun createDocument(title: String, author: String, kind: DocumentKind, unwarp: Boolean): String {
        val id = UUID.randomUUID().toString()
        documents.insert(
            DocumentEntity(
                id = id,
                title = title.trim(),
                author = author.trim(),
                kind = kind,
                unwarp = unwarp,
                updatedAt = clock.millis(),
                needsUpload = true,
                uploadError = null,
                confirmedAt = 0,
                server = null,
            ),
        )
        syncScheduler.requestSync()
        return id
    }

    /**
     * Refreshes the cached document list from [server].
     *
     * @throws ApiException if the server cannot be reached or refuses the request.
     */
    suspend fun refreshLibrary(server: ServerConfig) {
        val listedAt = clock.millis()
        val remote = api(server).documents()
        var orphanedCopies = emptyList<String>()
        // Pages waiting for the user's confirmation keep their document; the runs of the documents
        // deleted since have nowhere to go. No run gets pages meanwhile.
        staging.retainRuns { withStagedPages ->
            orphanedCopies = database.withTransaction {
                val update = reconcileLibrary(
                    local = documents.getAll(),
                    withPagesToUpload = pendingPages.documentsWithPagesToUpload().toSet(),
                    withStagedPages = withStagedPages,
                    remote = remote,
                    listedAt = listedAt,
                    now = clock.millis(),
                )
                documents.upsert(update.upserts)
                val copies = pendingPages.keptCopiesOf(update.deletions)
                documents.deleteUnlessPending(update.deletions)
                copies
            }
            documents.getAll().mapTo(HashSet()) { it.id }
        }
        deleteFiles(orphanedCopies)
    }

    /**
     * Refreshes one document and its pages. A document the server does not know is kept,
     * created again or forgotten, as in [refreshLibrary].
     *
     * @throws ApiException if the server cannot be reached or refuses the request.
     */
    suspend fun refreshDocument(server: ServerConfig, documentId: String) {
        val requestedAt = clock.millis()
        // Read before the request: the server's answer must list these pages, unless deleted on the PC.
        val uploadedBeforeRequest = pendingPages.uploadedIds(documentId)
        val detail = try {
            api(server).document(documentId)
        } catch (e: ApiException.Http) {
            if (e.code != HTTP_NOT_FOUND) throw e
            onDocumentMissing(documentId, requestedAt)
            return
        }
        val now = clock.millis()
        val listed = detail.pages.filter { it.documentId == documentId }
        database.withTransaction {
            documents.upsert(listOf(detail.document.toEntity(confirmedAt = now)))
            serverPages.deleteForDocument(documentId)
            serverPages.insertAll(listed.mapIndexed { position, page -> page.toEntity(position) })
            pendingPages.pruneConfirmed(documentId)
            uploadedPagesGone(uploadedBeforeRequest, listed)
                .chunked(MAX_SQL_PARAMETERS)
                .forEach { pendingPages.forgetUploaded(it) }
        }
    }

    private suspend fun onDocumentMissing(documentId: String, listedAt: Long) {
        var orphanedCopies = emptyList<String>()
        val hasStagedPages = staging.pages(documentId).isNotEmpty()
        val action = database.withTransaction {
            val document = documents.get(documentId) ?: return@withTransaction null
            val hasPagesToUpload = documentId in pendingPages.documentsWithPagesToUpload()
            actionForMissing(document, hasPagesToUpload, hasStagedPages, listedAt).also { action ->
                when (action) {
                    MissingDocumentAction.KEEP -> Unit

                    MissingDocumentAction.RECREATE -> {
                        documents.upsert(listOf(document.asNotOnServer()))
                        serverPages.deleteForDocument(documentId)
                    }

                    MissingDocumentAction.DELETE -> {
                        orphanedCopies = pendingPages.keptCopiesOf(listOf(documentId))
                        documents.deleteUnlessPending(listOf(documentId))
                    }
                }
            }
        }
        deleteFiles(orphanedCopies)
        if (action == MissingDocumentAction.RECREATE) syncScheduler.requestSync()
    }

    /**
     * Prepares the cache for a different server: what belongs to the previous one is forgotten,
     * and the documents with scans still to upload (or to confirm) will be created on the new one.
     */
    suspend fun switchServer() {
        val withStagedPages = staging.documentsWithPages()
        val orphanedCopies = database.withTransaction {
            val withPagesToUpload = pendingPages.documentsWithPagesToUpload().toSet()
            val (kept, dropped) = documents.getAll().partition {
                it.needsUpload || it.id in withPagesToUpload || it.id in withStagedPages
            }
            val copies = pendingPages.keptCopies()
            pendingPages.deleteUploaded()
            serverPages.deleteAll()
            documents.upsert(kept.map { it.asNotOnServer() })
            dropped.map { it.id }.chunked(MAX_SQL_PARAMETERS).forEach { documents.deleteUnlessPending(it) }
            copies
        }
        deleteFiles(orphanedCopies)
    }

    /** Lets the next upload try again to create a document the server refused. */
    suspend fun retryDocumentUpload(documentId: String) {
        documents.setUploadError(documentId, null)
        syncScheduler.requestSync()
    }

    /** Queues again a page the server refused. */
    suspend fun retryPage(pageId: String) {
        if (pendingPages.retry(pageId) > 0) syncScheduler.requestSync()
    }

    /** Deletes a local scan; returns false if it cannot be deleted because it is being uploaded. */
    suspend fun deleteLocalPage(pageId: String): Boolean {
        val page = pendingPages.get(pageId) ?: return true
        if (pendingPages.deleteIfIdle(pageId) == 0) return false
        page.fileName?.let { deleteFiles(listOf(it)) }
        return true
    }

    /** Deletes the local copies kept after upload. */
    suspend fun deleteKeptCopies() {
        val fileNames = pendingPages.keptCopies()
        database.withTransaction {
            fileNames.chunked(MAX_SQL_PARAMETERS).forEach { pendingPages.forgetKeptCopies(it) }
        }
        deleteFiles(fileNames)
    }

    private suspend fun deleteFiles(fileNames: List<String>) {
        if (fileNames.isEmpty()) return
        withContext(Dispatchers.IO) { fileNames.forEach(scanFiles::delete) }
    }

    private companion object {
        const val HTTP_NOT_FOUND = 404

        /**
         * Room binds one parameter per list element, and the SQLite of Android 11 and older
         * (before 3.32) refuses statements with more than 999 parameters: long lists go in chunks.
         */
        const val MAX_SQL_PARAMETERS = 500
    }
}
