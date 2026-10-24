package fr.scanmylib.library

import android.content.ContentResolver
import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import fr.scanmylib.db.PendingPageDao
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.UploadState
import fr.scanmylib.sync.SyncScheduler
import java.io.File
import java.io.FileNotFoundException
import java.io.FileOutputStream
import java.io.IOException
import java.time.Clock
import java.time.Instant
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

/** Outcome of an import from the photo picker. */
data class PhotoImportResult(
    /** Photos added to the run. */
    val added: Int,
    /** Photos left out because the server refuses their format (HEIC, GIF...). */
    val unsupported: Int = 0,
    /** Photos left out because they are over the server's size limits. */
    val tooLarge: Int = 0,
    /** Photos left out because they could not be copied (deleted since, cloud photo offline...). */
    val unreadable: Int = 0,
)

/**
 * Turns scanning runs into pages waiting for upload. Whatever their source (Google's scanner, the
 * camera screen, the photo picker), the pages first wait in the [StagingArea] for the user's
 * confirmation; [send] then moves them to the scan store, records them in the database as one
 * session, and schedules an upload. The images are never re-encoded.
 */
class ScanImporter(
    private val context: Context,
    private val pendingPages: PendingPageDao,
    private val scanFiles: ScanFileStore,
    private val staging: StagingArea,
    private val syncScheduler: SyncScheduler,
    private val clock: Clock,
) {
    /**
     * Copies the pages of a run of Google's scanner, in order, to [documentId]'s run, then deletes
     * the scanner's files; [onProgress] receives the number of pages copied so far. On failure,
     * the copies not added yet are deleted and the error rethrown.
     */
    suspend fun addScannedPages(documentId: String, images: List<Uri>, onProgress: (Int) -> Unit = {}) {
        if (images.isEmpty()) return
        val scannedAt = clock.instant()
        val copies = mutableListOf<File>()
        try {
            for ((index, image) in images.withIndex()) {
                val copy = staging.incomingFile(documentId).also(copies::add)
                withContext(Dispatchers.IO) { copyContent(image, copy) }
                onProgress(index + 1)
            }
            staging.add(documentId, copies.map { StagingInput(it, scannedAt) })
        } catch (e: Exception) {
            deleteQuietly(copies) // the copies already added are no longer there
            throw e
        }
        withContext(Dispatchers.IO) { images.forEach(::deleteScannerOutput) }
    }

    /**
     * Copies photos chosen in the photo picker to [documentId]'s run, ordered by the time they were
     * taken (see [importPhotos]); [onProgress] receives the number of photos done so far.
     */
    suspend fun addPhotos(documentId: String, photos: List<Uri>, onProgress: (Int) -> Unit = {}): PhotoImportResult =
        importPhotos(
            documentId = documentId,
            photos = photos,
            staging = staging,
            importedAt = clock.instant(),
            copy = ::copyContent,
            check = ::rejectionOf,
            takenAt = ::takenAt,
            onProgress = onProgress,
            onUnreadable = { photo, e -> Log.w(TAG, "photo not imported: $photo", e) },
        )

    /**
     * Queues the pages of [documentId]'s run for upload, as one session, each with its number.
     * Either all pages are queued, or none and the run stays as it was.
     *
     * @return the number of queued pages.
     */
    suspend fun send(documentId: String): Int {
        val count = staging.send(documentId) { pages ->
            // Once files start moving, finish (or undo) whatever happens to the caller.
            withContext(NonCancellable) {
                queueRun(
                    documentId,
                    pages,
                    scanFiles,
                    clock,
                    staging.sendJournal(documentId),
                    pendingPages::insertAll,
                )
            }
            pages.size
        }
        if (count > 0) {
            try {
                syncScheduler.requestSync()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // The pages are queued all the same: the upload starts when the app next comes to the front.
                Log.w(TAG, "upload not scheduled", e)
            }
        }
        return count
    }

    /**
     * Copies [source] to [target], up to a byte past what the server accepts: a huge or endless
     * stream (a photo shared by any app) stops there, and is then refused as too large. An import
     * can be canceled between two blocks.
     */
    private suspend fun copyContent(source: Uri, target: File) {
        val input = context.contentResolver.openInputStream(source)
            ?: throw FileNotFoundException("cannot open $source")
        input.use { content ->
            FileOutputStream(target).use { output ->
                val buffer = ByteArray(COPY_BUFFER_SIZE)
                var copied = 0L
                while (copied <= MAX_SCAN_BYTES) {
                    currentCoroutineContext().ensureActive()
                    val read = content.read(buffer)
                    if (read < 0) break
                    output.write(buffer, 0, read)
                    copied += read
                }
            }
        }
    }

    /** Whether the server would refuse the image in [file]. */
    private fun rejectionOf(file: File): PhotoRejection? {
        val format = ImageFormat.of(file) ?: return PhotoRejection.UNSUPPORTED_FORMAT
        return photoRejection(format, file.length(), pixelCount(file))
    }

    /** Width × height of the image in [file], read from its header only; null if unknown. */
    private fun pixelCount(file: File): Long? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, bounds)
        return if (bounds.outWidth > 0 && bounds.outHeight > 0) bounds.outWidth.toLong() * bounds.outHeight else null
    }

    /** When the photo in [image] was taken, according to its EXIF metadata. */
    private fun takenAt(image: File): Instant? = try {
        val exif = ExifInterface(image)
        exifCaptureTime(
            dateTime = exif.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL),
            subSeconds = exif.getAttribute(ExifInterface.TAG_SUBSEC_TIME_ORIGINAL),
            offset = exif.getAttribute(ExifInterface.TAG_OFFSET_TIME_ORIGINAL),
            zone = clock.zone,
        )
    } catch (e: IOException) {
        Log.w(TAG, "unreadable EXIF metadata", e)
        null
    } catch (e: RuntimeException) {
        // Malformed metadata must not stop the import: the photo is just not dated.
        Log.w(TAG, "unreadable EXIF metadata", e)
        null
    }

    /** The scanner writes its JPEG files into this app's cache directory: remove them once copied. */
    private fun deleteScannerOutput(image: Uri) {
        if (image.scheme != ContentResolver.SCHEME_FILE) return
        val file = File(image.path ?: return).canonicalFile
        if (file.path.startsWith(context.cacheDir.canonicalPath + File.separator)) file.delete()
    }
}

/**
 * Copies [photos] with [copy] to [documentId]'s run, ordered by the time they were taken
 * ([takenAt], see [orderByCaptureTime]); photos without a date are dated [importedAt]. Photos the
 * server would refuse ([check]) are left out, and so are the photos that cannot be copied: one
 * unreadable photo (deleted since, cloud photo offline...) does not cost the others. [onProgress]
 * receives the number of photos done so far.
 *
 * Throws when no photo at all could be copied (the phone's storage may be full), or when the
 * copies cannot join the run; the copies not added yet are then deleted.
 */
internal suspend fun <T> importPhotos(
    documentId: String,
    photos: List<T>,
    staging: StagingArea,
    importedAt: Instant,
    copy: suspend (T, File) -> Unit,
    check: (File) -> PhotoRejection?,
    takenAt: (File) -> Instant?,
    onProgress: (Int) -> Unit = {},
    onUnreadable: (T, Exception) -> Unit = { _, _ -> },
): PhotoImportResult {
    val copies = mutableListOf<File>()
    val accepted = mutableListOf<Pair<File, Instant?>>()
    var unsupported = 0
    var tooLarge = 0
    var unreadable = 0
    var lastError: Exception? = null
    try {
        for ((index, photo) in photos.withIndex()) {
            val target = staging.incomingFile(documentId).also(copies::add)
            val rejection = try {
                withContext(Dispatchers.IO) {
                    copy(photo, target)
                    check(target)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                onUnreadable(photo, e)
                unreadable++
                lastError = e
                deleteQuietly(listOf(target))
                onProgress(index + 1)
                continue
            }
            when (rejection) {
                null -> accepted += target to withContext(Dispatchers.IO) { takenAt(target) }
                PhotoRejection.UNSUPPORTED_FORMAT -> unsupported++
                PhotoRejection.TOO_LARGE -> tooLarge++
            }
            if (rejection != null) deleteQuietly(listOf(target))
            onProgress(index + 1)
        }
        // Nothing could be copied: rather the cause (storage full...) than "N photos left out".
        lastError?.let { if (unreadable == photos.size) throw it }
        if (accepted.isNotEmpty()) {
            val ordered = orderByCaptureTime(accepted) { (_, time) -> time }
            staging.add(documentId, ordered.map { (file, time) -> StagingInput(file, time ?: importedAt) })
        }
    } catch (e: Exception) {
        deleteQuietly(copies) // the copies already added are no longer there
        throw e
    }
    return PhotoImportResult(
        added = accepted.size,
        unsupported = unsupported,
        tooLarge = tooLarge,
        unreadable = unreadable,
    )
}

/**
 * Moves the [pages] of a run to [scanFiles] and records them with [insert] as one session of
 * [documentId], each with its number ([hintPages]). If anything fails, the files moved so far go
 * back to the run and the error is rethrown.
 *
 * The moves are first written to [journal]: should the process die before the pages are recorded,
 * the next one puts them back in the run ([recoverInterruptedSend]) instead of leaving them in the
 * scan store, where nothing would ever upload, show or delete them.
 */
internal suspend fun queueRun(
    documentId: String,
    pages: List<StagedPage>,
    scanFiles: ScanFileStore,
    clock: Clock,
    journal: File,
    insert: suspend (List<PendingPageEntity>) -> Unit,
) {
    if (pages.isEmpty()) return
    val sessionId = UUID.randomUUID().toString()
    val queuedAt = clock.millis()
    val hints = hintPages(pages.map { it.numbering })
    val entities = pages.mapIndexed { index, page ->
        val pageId = UUID.randomUUID().toString()
        PendingPageEntity(
            id = pageId,
            documentId = documentId,
            sessionId = sessionId,
            seq = index + 1,
            capturedAt = OffsetDateTime.ofInstant(page.capturedAt, clock.zone)
                .truncatedTo(ChronoUnit.SECONDS)
                .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
            pageNumberHint = hints[index].number,
            fileName = ScanFileStore.fileName(pageId),
            state = UploadState.QUEUED,
            failure = null,
            lastError = null,
            attempts = 0,
            queuedAt = queuedAt,
        )
    }
    val moved = mutableListOf<Pair<StagedPage, String>>()
    try {
        withContext(Dispatchers.IO) {
            writeSendJournal(journal, pages.zip(entities) { page, entity -> SentPage(entity.id, page.file.name) })
            pages.zip(entities).forEach { (page, entity) -> moved += page to scanFiles.adopt(entity.id, page.file) }
        }
        insert(entities)
    } catch (e: Exception) {
        val restored = withContext(NonCancellable + Dispatchers.IO) {
            moved.map { (page, fileName) -> scanFiles.file(fileName).renameTo(page.file) }.all { it }
        }
        // Kept if a page could not be put back: the next process tries again.
        if (restored) deleteQuietly(listOf(journal))
        throw e
    }
    deleteQuietly(listOf(journal))
}

/**
 * Finishes a send that a previous process left unfinished in [journal] (see [queueRun]): the pages
 * it moved to [scanFiles] without recording them go back to [runDirectory]; the recorded ones
 * ([isRecorded]) are in the upload queue and stay there. Never throws but to cancel: on failure,
 * the journal stays for the next process.
 */
internal suspend fun recoverInterruptedSend(
    journal: File,
    runDirectory: File,
    scanFiles: ScanFileStore,
    isRecorded: suspend (pageId: String) -> Boolean,
) {
    try {
        for (page in withContext(Dispatchers.IO) { readSendJournal(journal) }) {
            if (isRecorded(page.pageId)) continue
            withContext(Dispatchers.IO) {
                val moved = scanFiles.file(ScanFileStore.fileName(page.pageId))
                val staged = File(runDirectory, page.stagedName)
                if (moved.isFile && !staged.exists() && !moved.renameTo(staged)) {
                    throw IOException("cannot put $moved back in the run")
                }
            }
        }
        withContext(Dispatchers.IO) { journal.delete() }
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        Log.w(TAG, "interrupted send not recovered", e)
    }
}

/** A page that [queueRun] moves out of a run: the image of page [pageId], named [stagedName] in the run. */
internal data class SentPage(val pageId: String, val stagedName: String)

/** Writes [pages] to [journal], one per line, synced to disk. */
internal fun writeSendJournal(journal: File, pages: List<SentPage>) {
    FileOutputStream(journal).use { output ->
        output.write(pages.joinToString("") { "${it.pageId}\t${it.stagedName}\n" }.toByteArray(Charsets.UTF_8))
        output.fd.sync()
    }
}

/** The pages written by [writeSendJournal]; malformed lines (a write cut short) are skipped. */
internal fun readSendJournal(journal: File): List<SentPage> = journal.readLines(Charsets.UTF_8).mapNotNull { line ->
    val fields = line.split('\t')
    if (fields.size == 2 && fields.all(JOURNAL_NAME::matches)) SentPage(fields[0], fields[1]) else null
}

/** Page ids and staged file names: never a path. */
private val JOURNAL_NAME = Regex("[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}")

private suspend fun deleteQuietly(files: List<File>) {
    withContext(NonCancellable + Dispatchers.IO) { files.forEach(File::delete) }
}

private const val TAG = "ScanImporter"

private const val COPY_BUFFER_SIZE = 64 * 1024
