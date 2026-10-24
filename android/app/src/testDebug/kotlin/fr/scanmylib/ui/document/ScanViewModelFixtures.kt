package fr.scanmylib.ui.document

import android.net.Uri
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.lifecycle.SavedStateHandle
import fr.scanmylib.library.PhotoImportResult
import fr.scanmylib.library.RunPreparation
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.StagingInput
import fr.scanmylib.library.hintPages
import fr.scanmylib.settings.SettingsRepository
import java.io.File
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import org.junit.rules.TemporaryFolder

internal const val DOCUMENT_ID = "3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c"
private val SCAN_TIME = Instant.parse("2026-10-12T08:00:00Z")

/** A page handed to the upload queue: its file in the run, and its number hint. */
internal data class QueuedPage(val stagedName: String, val hint: Int?)

/**
 * Stands in for the upload queue: once [gate] opens, if any, it takes the run's files away, as the
 * real one moves them, or throws [refusal], if any, and leaves them in the run, as the real one
 * does when it fails.
 */
internal class FakeUploadQueue(
    private val staging: StagingArea,
    private val gate: CompletableDeferred<Unit>? = null,
    private val refusal: Exception? = null,
) {
    val pages = mutableListOf<QueuedPage>()

    suspend fun send(): Int = staging.send(DOCUMENT_ID) { run ->
        gate?.await()
        refusal?.let { throw it }
        val hints = hintPages(run.map { it.numbering })
        run.forEachIndexed { index, page ->
            if (!page.file.delete()) throw IOException("cannot take ${page.file}")
            pages += QueuedPage(page.file.name, hints[index].number)
        }
        run.size
    }
}

/** A document's run, which [viewModel] shows, and the copies into it. */
internal class RunUnderReview(
    val staging: StagingArea,
    val preparation: RunPreparation,
    val queue: FakeUploadQueue,
    val viewModel: ScanViewModel,
    val stagedPages: List<StagedPage>,
)

/** Three pages in the run, which the view model shows; their send waits for [sendGate], if any. */
internal suspend fun TestScope.stageThreePages(
    folder: TemporaryFolder,
    sendGate: CompletableDeferred<Unit>? = null,
    sendRefusal: Exception? = null,
): RunUnderReview = stagePages(folder, pageCount = 3, sendGate, sendRefusal)

/**
 * [pageCount] pages in the run, which the view model shows; their send waits for [sendGate], if
 * any, then fails with [sendRefusal], if any; Google's scanner's pages are copied with
 * [addScannedPages].
 */
@OptIn(ExperimentalCoroutinesApi::class)
internal suspend fun TestScope.stagePages(
    folder: TemporaryFolder,
    pageCount: Int,
    sendGate: CompletableDeferred<Unit>? = null,
    sendRefusal: Exception? = null,
    addScannedPages: suspend (List<Uri>, (Int) -> Unit) -> Unit = { _, _ -> },
): RunUnderReview {
    val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
    val stagedPages = staging.add(DOCUMENT_ID, writeImages(staging, pageCount))
    return showTheRun(folder, staging, stagedPages, sendGate, sendRefusal, addScannedPages)
}

internal suspend fun writeImages(staging: StagingArea, count: Int): List<StagingInput> = (1..count).map { index ->
    val image = staging.incomingFile(DOCUMENT_ID)
    image.writeBytes(byteArrayOf(index.toByte()))
    StagingInput(image, SCAN_TIME.plusSeconds(index.toLong()))
}

/** A document without pages to send, which the view model shows. */
@OptIn(ExperimentalCoroutinesApi::class)
internal suspend fun TestScope.makeEmptyRun(folder: TemporaryFolder): RunUnderReview {
    val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
    return showTheRun(folder, staging, stagedPages = emptyList())
}

/** A document whose images on their way to the run were cut short by the end of the previous process. */
@OptIn(ExperimentalCoroutinesApi::class)
internal suspend fun TestScope.makeRunCutShort(folder: TemporaryFolder): RunUnderReview {
    val root = File(folder.root, "staging")
    val incoming = File(root, "$DOCUMENT_ID/incoming")
    incoming.mkdirs()
    File(incoming, "cut-short.tmp").writeBytes(byteArrayOf(1))
    val staging = StagingArea(root, io = UnconfinedTestDispatcher(testScheduler))
    return showTheRun(folder, staging, stagedPages = emptyList())
}

private suspend fun TestScope.showTheRun(
    folder: TemporaryFolder,
    staging: StagingArea,
    stagedPages: List<StagedPage>,
    sendGate: CompletableDeferred<Unit>? = null,
    sendRefusal: Exception? = null,
    addScannedPages: suspend (List<Uri>, (Int) -> Unit) -> Unit = { _, _ -> },
): RunUnderReview {
    val queue = FakeUploadQueue(staging, sendGate, sendRefusal)
    val preparation = RunPreparation(this)
    val viewModel = makeViewModel(folder, staging, preparation, addScannedPages, sendRun = queue::send)
    backgroundScope.launch { viewModel.scanState.collect {} }
    viewModel.scanState.first { it.loaded && it.isRunRead && it.stagedPages == stagedPages }
    return RunUnderReview(staging, preparation, queue, viewModel, stagedPages)
}

@OptIn(ExperimentalCoroutinesApi::class)
internal fun TestScope.makeViewModel(
    folder: TemporaryFolder,
    staging: StagingArea,
    preparation: RunPreparation = RunPreparation(this),
    addScannedPages: suspend (List<Uri>, (Int) -> Unit) -> Unit = { _, _ -> },
    addPhotos: suspend (List<Uri>, (Int) -> Unit) -> PhotoImportResult = { _, _ -> PhotoImportResult(added = 0) },
    sendRun: suspend () -> Int = { 0 },
    scannedPages: Flow<List<IntRange>> = flowOf(emptyList()),
): ScanViewModel {
    val dataStore = PreferenceDataStoreFactory.create(scope = backgroundScope) {
        File(folder.root, "settings.preferences_pb")
    }
    return ScanViewModel(
        SavedStateHandle(),
        DOCUMENT_ID,
        staging,
        preparation,
        SettingsRepository(dataStore),
        addScannedPages = addScannedPages,
        addPhotos = addPhotos,
        sendRun = sendRun,
        scannedPages = scannedPages,
        freeStorage = { Long.MAX_VALUE },
        hasCamera = true,
        applicationScope = this,
        io = UnconfinedTestDispatcher(testScheduler),
    )
}

/** Stands in for the copy of Google's scanner's pages: it waits on [gate] once the first page is copied. */
internal class FakeScanner(private val staging: StagingArea, private val gate: CompletableDeferred<Unit>) {
    val firstPageCopied = CompletableDeferred<Unit>()

    suspend fun copy(pages: List<Uri>, onProgress: (Int) -> Unit) {
        val copies = pages.mapIndexed { index, page ->
            val copy = staging.incomingFile(DOCUMENT_ID)
            copy.writeText(page.toString())
            onProgress(index + 1)
            if (index == 0) {
                firstPageCopied.complete(Unit)
                gate.await()
            }
            StagingInput(copy, SCAN_TIME)
        }
        staging.add(DOCUMENT_ID, copies)
    }
}
