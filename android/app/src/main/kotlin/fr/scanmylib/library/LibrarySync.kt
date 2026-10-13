package fr.scanmylib.library

import fr.scanmylib.api.Document
import fr.scanmylib.api.Page
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.ServerDocumentState
import fr.scanmylib.db.ServerPageEntity
import java.time.OffsetDateTime
import java.time.format.DateTimeParseException

// Pure rules for merging what the server reports into the local cache.

/** The cached form of a document listed by the server, confirmed at [confirmedAt] (epoch ms). */
fun Document.toEntity(confirmedAt: Long): DocumentEntity = DocumentEntity(
    id = id,
    title = title,
    author = author,
    kind = kind,
    unwarp = unwarp,
    updatedAt = updatedAt?.let(::parseServerTime) ?: confirmedAt,
    needsUpload = false,
    uploadError = null,
    confirmedAt = confirmedAt,
    server = ServerDocumentState(
        pages = stats.pages,
        done = stats.done,
        queued = stats.queued,
        processing = stats.processing,
        errors = stats.error,
        excluded = stats.excluded,
        duplicates = stats.duplicates,
        coverage = coverage.label,
        missing = formatPageRanges(coverage.gaps),
        unnumbered = coverage.unnumbered,
        coverThumbUrl = coverThumbUrl,
        folder = folder,
    ),
)

/** The cached form of a page listed by the server at rank [position]. */
fun Page.toEntity(position: Int): ServerPageEntity = ServerPageEntity(
    id = id,
    documentId = documentId,
    position = position,
    status = status,
    error = error,
    pageLabel = pageLabel,
    numberSource = numberSource,
    excluded = excluded,
    duplicate = duplicateOf != null,
    thumbUrl = thumbUrl,
)

/** Formats page ranges like the server's coverage label: `[[1, 12], [45, 45]]` -> "1–12, 45". */
fun formatPageRanges(ranges: List<List<Int>>): String = ranges.mapNotNull { range ->
    when {
        range.size != 2 -> null
        range[0] == range[1] -> "${range[0]}"
        else -> "${range[0]}–${range[1]}"
    }
}.joinToString(", ")

/** Epoch milliseconds of an ISO-8601 time with offset, or null if it cannot be parsed. */
fun parseServerTime(text: String): Long? = try {
    OffsetDateTime.parse(text).toInstant().toEpochMilli()
} catch (e: DateTimeParseException) {
    null
}

/**
 * Local pages that were already uploaded when the document was requested but that the server
 * does not list: they were deleted on the PC. Their rows would otherwise stay on the document
 * screen as "uploaded" for good, since only pages the server lists are cleaned up. Pages
 * uploaded while the request was under way are not in [uploadedBeforeRequest], so they stay.
 */
fun uploadedPagesGone(uploadedBeforeRequest: Collection<String>, listed: List<Page>): List<String> {
    val listedIds = listed.mapTo(HashSet()) { it.id }
    return uploadedBeforeRequest.filter { it !in listedIds }
}

/** What to do with a cached document that the server does not know. */
enum class MissingDocumentAction {
    /**
     * Not created on the server yet, confirmed after the listing was requested, or with pages
     * waiting on the phone for the user to send or discard them.
     */
    KEEP,

    /** Deleted on the server while scans were waiting for upload: create it again to deliver them. */
    RECREATE,

    /** Deleted on the server: forget it. */
    DELETE,
}

/**
 * @param hasPagesToUpload whether the document has local pages queued for upload (or refused).
 * @param hasStagedPages whether pages wait for the user's confirmation (see [StagingArea]):
 *   forgetting the document would delete them, while sending them creates it again.
 */
fun actionForMissing(
    document: DocumentEntity,
    hasPagesToUpload: Boolean,
    hasStagedPages: Boolean,
    listedAt: Long,
): MissingDocumentAction = when {
    document.needsUpload || document.confirmedAt >= listedAt -> MissingDocumentAction.KEEP
    hasPagesToUpload -> MissingDocumentAction.RECREATE
    hasStagedPages -> MissingDocumentAction.KEEP
    else -> MissingDocumentAction.DELETE
}

/** Changes to apply to the local cache after a listing of the server's documents. */
data class LibraryUpdate(val upserts: List<DocumentEntity>, val deletions: List<String>)

/**
 * Merges the server's document list into the local cache. Documents listed by the server take
 * the server's state; the others are kept, re-created or deleted (see [actionForMissing]).
 *
 * @param withPagesToUpload ids of documents that have local pages not uploaded yet.
 * @param withStagedPages ids of documents that have pages waiting for the user's confirmation.
 * @param listedAt when the listing was requested (epoch ms).
 * @param now when the listing was received (epoch ms).
 */
fun reconcileLibrary(
    local: List<DocumentEntity>,
    withPagesToUpload: Set<String>,
    withStagedPages: Set<String>,
    remote: List<Document>,
    listedAt: Long,
    now: Long,
): LibraryUpdate {
    val remoteIds = remote.mapTo(HashSet()) { it.id }
    val upserts = remote.mapTo(mutableListOf()) { it.toEntity(confirmedAt = now) }
    val deletions = mutableListOf<String>()
    for (document in local) {
        if (document.id in remoteIds) continue
        when (actionForMissing(document, document.id in withPagesToUpload, document.id in withStagedPages, listedAt)) {
            MissingDocumentAction.KEEP -> Unit
            MissingDocumentAction.RECREATE -> upserts += document.asNotOnServer()
            MissingDocumentAction.DELETE -> deletions += document.id
        }
    }
    return LibraryUpdate(upserts, deletions)
}

/** The document as it must be (re)created on the server by the next sync. */
fun DocumentEntity.asNotOnServer(): DocumentEntity =
    copy(needsUpload = true, uploadError = null, confirmedAt = 0, server = null)
