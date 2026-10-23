package fr.scanmylib.ui.document

import android.content.ActivityNotFoundException
import android.content.res.Resources
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickMultipleVisualMedia
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.platform.LocalResources
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import fr.scanmylib.R
import fr.scanmylib.model.ScanSource

/** What a screen opens to add pages to a document's run: a camera, or the photo picker. */
class ScanSources(
    /** Opens a source at once, with no question: the numbering is set while reviewing the pages. */
    val open: (ScanSource) -> Unit,
    val importPhotos: () -> Unit,
)

/**
 * Registers the sources of pages for the screen that calls it: Google's scanner and the photo
 * picker, whose results join [viewModel]'s run, and the app's camera, a screen of its own
 * ([onOpenCamera]). [onPagesReturned] follows a source that returned pages. A [switchToSource]
 * opens at once, once the settings are read ([onSwitchHandled]): the camera screen asks for it when
 * it could not open the camera. The run's messages show in [snackbarHostState].
 */
@Composable
fun rememberScanSources(
    viewModel: ScanViewModel,
    snackbarHostState: SnackbarHostState,
    onOpenCamera: () -> Unit,
    onPagesReturned: () -> Unit,
    switchToSource: ScanSource?,
    onSwitchHandled: () -> Unit,
): ScanSources {
    val scan by viewModel.scanState.collectAsStateWithLifecycle()
    val resources = LocalResources.current
    val currentOnPagesReturned by rememberUpdatedState(onPagesReturned)
    val launchScanner = rememberDocumentScanner(
        onScanned = { pages ->
            viewModel.onPagesScanned(pages)
            if (pages.isNotEmpty()) currentOnPagesReturned()
        },
        onStarted = viewModel::onScannerStarted,
        onUnavailable = viewModel::onScannerUnavailable,
        onFailed = viewModel::onScannerFailed,
    )
    // The system photo picker needs no storage permission (it falls back to the document picker
    // on phones without it). One contract: a new one at each recomposition would register the
    // launcher again each time.
    val pickPhotosContract = remember { PickMultipleVisualMedia() }
    val pickPhotos = rememberLauncherForActivityResult(pickPhotosContract) { photos: List<Uri> ->
        viewModel.onPhotosPicked(photos)
        if (photos.isNotEmpty()) currentOnPagesReturned()
    }
    val importPhotos = {
        try {
            // In the order the photos are chosen: the order kept for photos without a date.
            pickPhotos.launch(
                PickVisualMediaRequest.Builder()
                    .setMediaType(PickVisualMedia.ImageOnly)
                    .setOrderedSelection(true)
                    .build(),
            )
        } catch (e: ActivityNotFoundException) {
            viewModel.onPhotoPickerUnavailable(e)
        }
    }
    val open = { source: ScanSource ->
        when (source) {
            ScanSource.GOOGLE_SCANNER -> launchScanner(scan.scannerMode)
            ScanSource.CAMERA -> onOpenCamera()
            ScanSource.PHOTO_PICKER -> importPhotos()
        }
    }
    val currentOpen by rememberUpdatedState(open)
    LaunchedEffect(viewModel) {
        viewModel.messages.collect { message ->
            if (message == ScanMessage.ScannerUnavailable && scan.hasCamera) {
                // The app's camera works without Google Play services.
                val result = snackbarHostState.showSnackbar(
                    message.text(resources),
                    actionLabel = resources.getString(R.string.scan_source_camera),
                    withDismissAction = true,
                    duration = SnackbarDuration.Long,
                )
                if (result == SnackbarResult.ActionPerformed) currentOpen(ScanSource.CAMERA)
            } else {
                snackbarHostState.showSnackbar(
                    message.text(resources),
                    withDismissAction = message.important,
                    duration = if (message.important) SnackbarDuration.Long else SnackbarDuration.Short,
                )
            }
        }
    }
    LaunchedEffect(switchToSource, scan.loaded) {
        val source = switchToSource ?: return@LaunchedEffect
        if (!scan.loaded) return@LaunchedEffect
        onSwitchHandled()
        currentOpen(source)
    }
    return ScanSources(open, importPhotos)
}

private fun ScanMessage.text(resources: Resources): String = when (this) {
    ScanMessage.SendFailed -> resources.getString(R.string.message_send_failed)
    ScanMessage.StorageFull -> resources.getString(R.string.message_storage_full)
    ScanMessage.SettingNotSaved -> resources.getString(R.string.message_setting_not_saved)
    ScanMessage.ScannerUnavailable -> resources.getString(R.string.message_scanner_unavailable)
    ScanMessage.ScannerFailed -> resources.getString(R.string.message_scanner_failed)
    ScanMessage.PhotoPickerUnavailable -> resources.getString(R.string.message_photo_picker_unavailable)
}
