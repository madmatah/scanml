package fr.scanmylib.library

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.time.Instant
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.onStart
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * A page waiting for the user to send it to the upload queue, or to discard it.
 *
 * @property seq position in the run, from 1. Numbers can have gaps (a photo deleted during the
 *   run): the pages are numbered again when they are sent.
 * @property capturedAt when the page was photographed: the time of the shot, the EXIF time of an
 *   imported photo, or the time of the scanner run.
 */
data class StagedPage(val file: File, val seq: Int, val capturedAt: Instant)

/** A complete image written in a [StagingArea.incomingFile], to add to a run. */
data class StagingInput(val file: File, val capturedAt: Instant)

/**
 * Pages captured, scanned or imported for a document, kept in the app's private storage until the
 * user sends them to the upload queue or discards them: one run per document, in its own
 * directory. Each page is a file named after its position and capture time, so the directory
 * alone describes the run: it survives the process being killed and the app being closed, and is
 * offered again when the document is opened.
 *
 * Images are written in an `incoming` subdirectory first and join the run once complete; what an
 * interrupted shot or copy leaves there is deleted when the run is first read by a new process.
 *
 * @param io the dispatcher of the disk's work; tests give their own, to run it in a fixed order.
 * @param recoverSend called when a run is first read by a new process and holds the journal of a
 *   send that the previous process did not finish (see [sendJournal]): it must put back in the run
 *   directory the pages that left the run without reaching the upload queue, delete the journal,
 *   and never throw.
 */
class StagingArea(
    private val root: File,
    private val io: CoroutineDispatcher = Dispatchers.IO,
    private val recoverSend: suspend (journal: File, runDirectory: File) -> Unit = { _, _ -> },
) {

    private val mutex = Mutex()

    /** The runs read so far, by document id, each in order. */
    private val runs = MutableStateFlow<Map<String, List<StagedPage>>>(emptyMap())

    /** Documents whose run had images cut short by the end of the previous process, not reported yet. */
    private val interrupted = mutableSetOf<String>()

    /** The pages of [documentId]'s run, in order; empty when there is none. */
    fun observe(documentId: String): Flow<List<StagedPage>> = runs
        .onStart { mutex.withLock { loadLocked(documentId) } }
        .map { it[documentId].orEmpty() }
        .distinctUntilChanged()

    /** The pages of [documentId]'s run, in order. */
    suspend fun pages(documentId: String): List<StagedPage> = mutex.withLock { loadLocked(documentId) }

    /** The number of pages of each run that has some, by document id. */
    fun observeRunSizes(): Flow<Map<String, Int>> = runs
        .onStart { mutex.withLock { loadAllLocked() } }
        .map { runs -> runs.filterValues { it.isNotEmpty() }.mapValues { (_, pages) -> pages.size } }
        .distinctUntilChanged()

    /** Ids of the documents whose run has pages. */
    suspend fun documentsWithPages(): Set<String> = mutex.withLock { withPagesLocked() }

    /**
     * Whether images on their way to [documentId]'s run (a photo being saved, photos being
     * imported) were cut short when the previous process ended; true once only.
     */
    suspend fun takeInterrupted(documentId: String): Boolean = mutex.withLock {
        loadLocked(documentId)
        interrupted.remove(documentId)
    }

    /** A new file in which to write an image before [add]ing it to [documentId]'s run. */
    suspend fun incomingFile(documentId: String): File = mutex.withLock {
        // Reading the run first cleans up the incoming directory: never after this file exists.
        loadLocked(documentId)
        withContext(io) {
            val incoming = File(directory(documentId), INCOMING)
            if (!incoming.isDirectory && !incoming.mkdirs()) throw IOException("cannot create $incoming")
            File(incoming, "${UUID.randomUUID()}.tmp")
        }
    }

    /**
     * Adds complete images, written in [incomingFile]s, as the next pages of [documentId]'s run,
     * in the given order. Each image is synced to disk before it joins the run.
     *
     * @return the added pages.
     */
    suspend fun add(documentId: String, inputs: List<StagingInput>): List<StagedPage> = mutex.withLock {
        val run = loadLocked(documentId)
        val added = mutableListOf<StagedPage>()
        try {
            withContext(io) {
                var seq = run.maxOfOrNull { it.seq } ?: 0
                for (input in inputs) {
                    if (input.file.length() == 0L) throw IOException("empty image: ${input.file}")
                    FileOutputStream(input.file, true).use { it.fd.sync() }
                    seq++
                    val file = File(directory(documentId), fileName(seq, input.capturedAt))
                    val page = StagedPage(file, seq, input.capturedAt)
                    if (!input.file.renameTo(page.file)) throw IOException("cannot add ${input.file} to the run")
                    added += page
                }
            }
        } finally {
            // Pages moved before a failure are in the run on disk: keep the memory in step.
            runs.update { it + (documentId to run + added) }
        }
        added
    }

    /** Deletes one page of [documentId]'s run. */
    suspend fun remove(documentId: String, page: StagedPage) {
        mutex.withLock {
            val run = loadLocked(documentId)
            withContext(io) {
                if (!page.file.delete() && page.file.exists()) throw IOException("cannot delete ${page.file}")
            }
            runs.update { it + (documentId to run - page) }
        }
    }

    /** Deletes [documentId]'s run. */
    suspend fun discard(documentId: String) {
        mutex.withLock {
            withContext(io) { directory(documentId).deleteRecursively() }
            runs.update { it + (documentId to emptyList()) }
        }
    }

    /**
     * Where the sender of [documentId]'s run records the pages it moves out of the run, before
     * moving them; deleted once they are queued for upload (or back in the run). Its presence at
     * the next start means the process died meanwhile: see the `recoverSend` constructor parameter.
     */
    fun sendJournal(documentId: String): File = File(directory(documentId), SEND_JOURNAL)

    /**
     * Hands [documentId]'s run over to [send], which must move every page file out of the run, or
     * throw and leave them in place. Returns what [send] returns.
     */
    suspend fun <T> send(documentId: String, send: suspend (List<StagedPage>) -> T): T = mutex.withLock {
        val run = loadLocked(documentId)
        try {
            send(run)
        } finally {
            // Normally all pages or none have moved: the files tell.
            withContext(NonCancellable + io) {
                val left = run.filter { it.file.exists() }
                runs.update { it + (documentId to left) }
                if (left.isEmpty()) {
                    // Only removed when empty: a shot may still be on its way.
                    File(directory(documentId), INCOMING).delete()
                    directory(documentId).delete()
                }
            }
        }
    }

    /**
     * Deletes the runs of the documents that no longer exist: [existingDocuments] receives the ids
     * of the documents whose run has pages, and returns the ids of the documents that still exist
     * once it has updated the library. No page joins or leaves a run meanwhile, so a run that
     * [existingDocuments] saw empty cannot get pages before it is deleted.
     */
    suspend fun retainRuns(existingDocuments: suspend (documentsWithPages: Set<String>) -> Set<String>) {
        mutex.withLock {
            val kept = existingDocuments(withPagesLocked())
            val deleted = withContext(io) {
                root.listFiles().orEmpty()
                    .filter { it.isDirectory && it.name !in kept }
                    .onEach { it.deleteRecursively() }
                    .mapTo(HashSet()) { it.name }
            }
            runs.update { it - deleted }
        }
    }

    private suspend fun withPagesLocked(): Set<String> = loadAllLocked().filterValues { it.isNotEmpty() }.keys

    /** Reads every run on disk; returns all the runs. */
    private suspend fun loadAllLocked(): Map<String, List<StagedPage>> {
        val documentIds = withContext(io) {
            root.listFiles().orEmpty().filter { it.isDirectory && DOCUMENT_ID.matches(it.name) }.map { it.name }
        }
        documentIds.forEach { loadLocked(it) }
        return runs.value
    }

    private suspend fun loadLocked(documentId: String): List<StagedPage> {
        runs.value[documentId]?.let { return it }
        val directory = directory(documentId)
        val journal = File(directory, SEND_JOURNAL)
        if (withContext(io) { journal.exists() }) recoverSend(journal, directory)
        val (run, cutShort) = withContext(io) {
            val incoming = File(directory, INCOMING)
            val cutShort = incoming.listFiles().orEmpty().isNotEmpty()
            incoming.deleteRecursively()
            directory.listFiles().orEmpty().mapNotNull(::parseFileName).sortedWith(PAGE_ORDER) to cutShort
        }
        if (cutShort) interrupted += documentId
        runs.update { it + (documentId to run) }
        return run
    }

    private fun directory(documentId: String): File {
        // Document ids are UUIDs (generated by the phone or the web UI): never a path.
        require(DOCUMENT_ID.matches(documentId)) { "unexpected document id: $documentId" }
        return File(root, documentId)
    }

    companion object {
        private const val INCOMING = "incoming"
        private const val SEND_JOURNAL = "sending"
        private val DOCUMENT_ID = Regex("[A-Za-z0-9-]{1,64}")
        private val FILE_NAME = Regex("""(\d{1,9})_(\d{1,15})\.jpg""")
        private val PAGE_ORDER = compareBy<StagedPage>({ it.seq }, { it.capturedAt })

        /** `<seq>_<capture time in epoch ms>.jpg`, e.g. `00012_1760293530123.jpg`. */
        internal fun fileName(seq: Int, capturedAt: Instant): String =
            String.format(Locale.ROOT, "%05d_%d.jpg", seq, capturedAt.toEpochMilli())

        /** The page stored in [file], or null if the file is not a staged page. */
        internal fun parseFileName(file: File): StagedPage? {
            val match = FILE_NAME.matchEntire(file.name) ?: return null
            val seq = match.groupValues[1].toInt().takeIf { it >= 1 } ?: return null
            return StagedPage(file, seq, Instant.ofEpochMilli(match.groupValues[2].toLong()))
        }
    }
}
