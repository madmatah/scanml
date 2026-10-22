package fr.scanmylib.ui.document

import android.net.Uri
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.lifecycle.SavedStateHandle
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.library.PhotoImportResult
import fr.scanmylib.library.RunPreparation
import fr.scanmylib.library.StagedPage
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.StagingInput
import fr.scanmylib.settings.SettingsRepository
import java.io.File
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import org.junit.rules.TemporaryFolder

internal const val DOCUMENT_ID = "3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c"
private val SCAN_TIME = Instant.parse("2026-10-12T08:00:00Z")

/** A page handed to the upload queue: its file in the run, and its number hint. */
internal data class QueuedPage(val stagedName: String, val hint: Int?)

/**
 * Stands in for the upload queue: it takes the run's files away, as the real one moves them, or
 * throws [refusal], if any, and leaves them in the run, as the real one does when it fails.
 */
internal class FakeUploadQueue(private val staging: StagingArea, private val refusal: Exception? = null) {
    val pages = mutableListOf<QueuedPage>()

    suspend fun send(numbering: PageNumbering): Int = staging.send(DOCUMENT_ID) { run ->
        refusal?.let { throw it }
        run.forEachIndexed { index, page ->
            if (!page.file.delete()) throw IOException("cannot take ${page.file}")
            pages += QueuedPage(page.file.name, numbering.hintFor(index))
        }
        run.size
    }
}

internal class ThreePagesToSend(
    val staging: StagingArea,
    val queue: FakeUploadQueue,
    val viewModel: ScanViewModel,
    val stagedPages: List<StagedPage>,
)

/** Three pages in the run, which the view model shows; their send fails with [sendRefusal], if any. */
@OptIn(ExperimentalCoroutinesApi::class)
internal suspend fun TestScope.stageThreePages(
    folder: TemporaryFolder,
    sendRefusal: Exception? = null,
): ThreePagesToSend {
    val staging = StagingArea(File(folder.root, "staging"), io = UnconfinedTestDispatcher(testScheduler))
    val inputs = (1..3).map { index ->
        val image = staging.incomingFile(DOCUMENT_ID)
        image.writeBytes(byteArrayOf(index.toByte()))
        StagingInput(image, SCAN_TIME.plusSeconds(index.toLong()))
    }
    val stagedPages = staging.add(DOCUMENT_ID, inputs)
    val queue = FakeUploadQueue(staging, sendRefusal)
    val viewModel = makeViewModel(folder, staging, sendRun = queue::send)
    backgroundScope.launch { viewModel.scanState.collect {} }
    viewModel.scanState.first { it.loaded && it.stagedPages == stagedPages }
    return ThreePagesToSend(staging, queue, viewModel, stagedPages)
}

@OptIn(ExperimentalCoroutinesApi::class)
internal fun TestScope.makeViewModel(
    folder: TemporaryFolder,
    staging: StagingArea,
    addScannedPages: suspend (List<Uri>, (Int) -> Unit) -> Unit = { _, _ -> },
    addPhotos: suspend (List<Uri>, (Int) -> Unit) -> PhotoImportResult = { _, _ -> PhotoImportResult(added = 0) },
    sendRun: suspend (PageNumbering) -> Int = { 0 },
): ScanViewModel {
    val dataStore = PreferenceDataStoreFactory.create(scope = backgroundScope) {
        File(folder.root, "settings.preferences_pb")
    }
    return ScanViewModel(
        SavedStateHandle(),
        DOCUMENT_ID,
        staging,
        RunPreparation(this),
        SettingsRepository(dataStore),
        addScannedPages = addScannedPages,
        addPhotos = addPhotos,
        sendRun = sendRun,
        freeStorage = { Long.MAX_VALUE },
        hasCamera = true,
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
