package fr.scanmylib.db

import androidx.room.Dao
import androidx.room.Embedded
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

/** A document of the library with the state of its local scans. */
data class LibraryRow(
    @Embedded val document: DocumentEntity,
    /** Local pages waiting for (or in) upload. */
    val pagesToUpload: Int,
    /** Local pages the server refused. */
    val failedPages: Int,
)

@Dao
interface DocumentDao {
    @Query(
        """
        SELECT documents.*,
            (SELECT COUNT(*) FROM pending_pages AS p
                WHERE p.documentId = documents.id AND p.state IN ('QUEUED', 'UPLOADING')) AS pagesToUpload,
            (SELECT COUNT(*) FROM pending_pages AS p
                WHERE p.documentId = documents.id AND p.state = 'FAILED') AS failedPages
        FROM documents
        ORDER BY documents.updatedAt DESC
        """,
    )
    fun observeLibrary(): Flow<List<LibraryRow>>

    @Query("SELECT * FROM documents WHERE id = :id")
    fun observe(id: String): Flow<DocumentEntity?>

    @Query("SELECT * FROM documents WHERE id = :id")
    suspend fun get(id: String): DocumentEntity?

    @Query("SELECT * FROM documents")
    suspend fun getAll(): List<DocumentEntity>

    /** Documents to create on the server, oldest first; rejected ones wait for a retry. */
    @Query("SELECT * FROM documents WHERE needsUpload = 1 AND uploadError IS NULL ORDER BY updatedAt")
    suspend fun awaitingUpload(): List<DocumentEntity>

    @Query("SELECT COUNT(*) FROM documents WHERE needsUpload = 1 AND uploadError IS NULL")
    suspend fun countAwaitingUpload(): Int

    @Insert
    suspend fun insert(document: DocumentEntity)

    /** Inserts or updates in place: an update never cascades to the document's pages. */
    @Upsert
    suspend fun upsert(documents: List<DocumentEntity>)

    @Query("UPDATE documents SET needsUpload = 1 WHERE id = :id")
    suspend fun markNeedsUpload(id: String)

    @Query("UPDATE documents SET uploadError = :error WHERE id = :id")
    suspend fun setUploadError(id: String, error: String?)

    /** Deletes documents (with their cached pages), except those with local pages not uploaded yet. */
    @Query(
        """
        DELETE FROM documents WHERE id IN (:ids) AND NOT EXISTS (
            SELECT 1 FROM pending_pages AS p WHERE p.documentId = documents.id AND p.state != 'UPLOADED')
        """,
    )
    suspend fun deleteUnlessPending(ids: List<String>)
}

@Dao
interface PendingPageDao {
    @Query("SELECT * FROM pending_pages WHERE documentId = :documentId ORDER BY queuedAt, seq")
    fun observeForDocument(documentId: String): Flow<List<PendingPageEntity>>

    @Query("SELECT * FROM pending_pages WHERE id = :id")
    suspend fun get(id: String): PendingPageEntity?

    @Insert
    suspend fun insertAll(pages: List<PendingPageEntity>)

    @Query("SELECT COUNT(*) FROM pending_pages WHERE state IN ('QUEUED', 'UPLOADING')")
    suspend fun countAwaitingUpload(): Int

    /** Documents with local pages that are not on the server yet (failed ones included). */
    @Query("SELECT DISTINCT documentId FROM pending_pages WHERE state != 'UPLOADED'")
    suspend fun documentsWithPagesToUpload(): List<String>

    /** The next page to upload: the oldest queued one whose document the server knows. */
    @Query(
        """
        SELECT pending_pages.* FROM pending_pages
        JOIN documents ON documents.id = pending_pages.documentId
        WHERE pending_pages.state = 'QUEUED' AND documents.needsUpload = 0
        ORDER BY pending_pages.queuedAt, pending_pages.seq
        LIMIT 1
        """,
    )
    suspend fun nextToUpload(): PendingPageEntity?

    /** Marks a queued page as uploading; returns 0 if it is not queued any more (deleted meanwhile). */
    @Query("UPDATE pending_pages SET state = 'UPLOADING' WHERE id = :id AND state = 'QUEUED'")
    suspend fun claimForUpload(id: String): Int

    /** Pages left uploading by an interrupted run go back to the queue. */
    @Query("UPDATE pending_pages SET state = 'QUEUED' WHERE state = 'UPLOADING'")
    suspend fun requeueInterrupted()

    @Query(
        """
        UPDATE pending_pages SET state = 'UPLOADED', fileName = :keptFileName, failure = NULL,
            lastError = NULL WHERE id = :id
        """,
    )
    suspend fun markUploaded(id: String, keptFileName: String?)

    @Query(
        """
        UPDATE pending_pages SET state = :state, failure = :failure, lastError = :detail,
            attempts = attempts + 1 WHERE id = :id
        """,
    )
    suspend fun recordFailure(id: String, state: UploadState, failure: UploadFailure, detail: String?)

    @Query("UPDATE pending_pages SET state = 'QUEUED', failure = NULL, lastError = NULL WHERE id = :id AND state = 'FAILED'")
    suspend fun retry(id: String): Int

    /** Deletes a page unless it is being uploaded; returns the number of deleted rows. */
    @Query("DELETE FROM pending_pages WHERE id = :id AND state IN ('QUEUED', 'FAILED')")
    suspend fun deleteIfIdle(id: String): Int

    /** Forgets uploaded pages that the server now lists and that have no local copy left. */
    @Query(
        """
        DELETE FROM pending_pages WHERE documentId = :documentId AND state = 'UPLOADED'
            AND fileName IS NULL AND id IN (SELECT id FROM server_pages WHERE documentId = :documentId)
        """,
    )
    suspend fun pruneConfirmed(documentId: String)

    @Query("SELECT id FROM pending_pages WHERE documentId = :documentId AND state = 'UPLOADED'")
    suspend fun uploadedIds(documentId: String): List<String>

    /** Uploaded pages that the cached pages of their document do not list (yet). */
    @Query("SELECT id FROM pending_pages WHERE state = 'UPLOADED' AND id NOT IN (SELECT id FROM server_pages)")
    fun observeUnlistedUploads(): Flow<List<String>>

    /** Forgets uploaded pages that have no local copy left (see [fr.scanmylib.library.uploadedPagesGone]). */
    @Query("DELETE FROM pending_pages WHERE id IN (:ids) AND state = 'UPLOADED' AND fileName IS NULL")
    suspend fun forgetUploaded(ids: List<String>)

    /** Files of the local copies kept after upload ("keep local copies" setting). */
    @Query("SELECT fileName FROM pending_pages WHERE state = 'UPLOADED' AND fileName IS NOT NULL")
    fun observeKeptCopies(): Flow<List<String>>

    @Query("SELECT fileName FROM pending_pages WHERE state = 'UPLOADED' AND fileName IS NOT NULL")
    suspend fun keptCopies(): List<String>

    @Query(
        """
        SELECT fileName FROM pending_pages
        WHERE documentId IN (:documentIds) AND state = 'UPLOADED' AND fileName IS NOT NULL
        """,
    )
    suspend fun keptCopiesOf(documentIds: List<String>): List<String>

    @Query("UPDATE pending_pages SET fileName = NULL WHERE state = 'UPLOADED' AND fileName IN (:fileNames)")
    suspend fun forgetKeptCopies(fileNames: List<String>)

    @Query("DELETE FROM pending_pages WHERE state = 'UPLOADED'")
    suspend fun deleteUploaded()
}

@Dao
interface ServerPageDao {
    @Query("SELECT * FROM server_pages WHERE documentId = :documentId ORDER BY position")
    fun observeForDocument(documentId: String): Flow<List<ServerPageEntity>>

    @Query("DELETE FROM server_pages WHERE documentId = :documentId")
    suspend fun deleteForDocument(documentId: String)

    @Query("DELETE FROM server_pages")
    suspend fun deleteAll()

    @Insert
    suspend fun insertAll(pages: List<ServerPageEntity>)
}
