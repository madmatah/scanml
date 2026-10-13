package fr.scanmylib.db

import androidx.room.Embedded
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.PageStatus
import fr.scanmylib.model.DocumentKind

/** A document of the library: cached from the server, or created on the phone. */
@Entity(tableName = "documents")
data class DocumentEntity(
    @PrimaryKey val id: String,
    val title: String,
    val author: String,
    val kind: DocumentKind,
    val unwarp: Boolean,
    /** Sort key (epoch ms): the server's `updated_at`, or the creation time until then. */
    val updatedAt: Long,
    /** The document must be created on the server (PUT) before its pages are uploaded. */
    val needsUpload: Boolean,
    /** Why the server rejected the PUT; the document waits until the user retries. */
    val uploadError: String?,
    /** When the server last confirmed the document (epoch ms), 0 if never. */
    val confirmedAt: Long,
    /** The server's view of the document, null until the server has listed it. */
    @Embedded(prefix = "server_") val server: ServerDocumentState?,
)

/** OCR progress and page coverage of a document, as reported by the server. */
data class ServerDocumentState(
    val pages: Int,
    val done: Int,
    val queued: Int,
    val processing: Int,
    val errors: Int,
    val excluded: Int,
    val duplicates: Int,
    /** Covered page numbers, e.g. "1–12, 45–60". */
    val coverage: String,
    /** Missing page numbers between the first and the last one, e.g. "13–44". */
    val missing: String,
    val unnumbered: Int,
    val coverThumbUrl: String?,
    val folder: String,
)

/** Upload progress of a local scan. */
enum class UploadState {
    QUEUED,
    UPLOADING,

    /** Rejected for good (see [UploadFailure]); waits for the user to retry or delete it. */
    FAILED,

    /** On the server; the row stays until the server lists the page (or while a local copy is kept). */
    UPLOADED,
}

/** Why the last upload attempt of a page failed. */
enum class UploadFailure(val retryable: Boolean) {
    /** Server unreachable: PC off, other network... */
    NETWORK(retryable = true),

    /** Server-side error (5xx, overload, unreadable answer). */
    SERVER_ERROR(retryable = true),

    /** The server refused the token: the phone must be paired again. */
    UNAUTHORIZED(retryable = true),

    /** The server does not know the document, even after creating it again. */
    DOCUMENT_MISSING(retryable = false),
    TOO_LARGE(retryable = false),
    UNSUPPORTED_TYPE(retryable = false),

    /** Any other refusal (invalid request). */
    REJECTED(retryable = false),

    /** The local image file is gone. */
    FILE_MISSING(retryable = false),
}

/** A page scanned on this phone, from the scanner until the server has it. */
@Entity(
    tableName = "pending_pages",
    foreignKeys = [
        ForeignKey(
            entity = DocumentEntity::class,
            parentColumns = ["id"],
            childColumns = ["documentId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("documentId")],
)
data class PendingPageEntity(
    @PrimaryKey val id: String,
    val documentId: String,
    val sessionId: String,
    val seq: Int,
    /** ISO-8601 with offset, sent as `captured_at`. */
    val capturedAt: String,
    val pageNumberHint: Int?,
    /** Image in the scan store; null once deleted after the upload. */
    val fileName: String?,
    val state: UploadState,
    val failure: UploadFailure?,
    /** Technical detail of the last failure (server message, exception). */
    val lastError: String?,
    val attempts: Int,
    /** When the page was queued (epoch ms): pages are uploaded in this order. */
    val queuedAt: Long,
)

/** A page as listed by the server, cached to show documents offline. */
@Entity(
    tableName = "server_pages",
    foreignKeys = [
        ForeignKey(
            entity = DocumentEntity::class,
            parentColumns = ["id"],
            childColumns = ["documentId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("documentId")],
)
data class ServerPageEntity(
    @PrimaryKey val id: String,
    val documentId: String,
    /** Rank in the server's order: reading order first, then pages left out of the document. */
    val position: Int,
    val status: PageStatus,
    val error: String?,
    val pageLabel: String?,
    val numberSource: NumberSource?,
    val excluded: Boolean,
    val duplicate: Boolean,
    val thumbUrl: String?,
)
