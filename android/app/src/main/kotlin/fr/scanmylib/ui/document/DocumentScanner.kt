package fr.scanmylib.ui.document

import android.app.Activity
import android.net.Uri
import androidx.activity.compose.LocalActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import fr.scanmylib.model.ScannerMode

/** The ML Kit scanner mode that retouches the pages as much as [this] allows, and no more. */
internal fun ScannerMode.gmsScannerMode(): Int = when (this) {
    ScannerMode.CROP_ONLY -> GmsDocumentScannerOptions.SCANNER_MODE_BASE
    ScannerMode.FILTERS -> GmsDocumentScannerOptions.SCANNER_MODE_BASE_WITH_FILTER
    ScannerMode.FULL -> GmsDocumentScannerOptions.SCANNER_MODE_FULL
}

private fun scannerOptions(mode: ScannerMode) = GmsDocumentScannerOptions.Builder()
    .setScannerMode(mode.gmsScannerMode())
    .setResultFormats(GmsDocumentScannerOptions.RESULT_FORMAT_JPEG)
    .setGalleryImportAllowed(true)
    .build()

/**
 * Returns a function that opens Google's document scanner (ML Kit, in Google Play services: no
 * camera permission needed) in the given mode, and reports the scanned pages, in order, as JPEG
 * files: none when the user cancels, or when the scanner fails to hand them over (it then
 * cancels too, e.g. when the phone's storage is full).
 *
 * [onStarted]: the scanner is about to open, so it works on this phone. [onUnavailable]: it could
 * not be started (Google Play services missing, outdated or disabled, its module not downloaded
 * yet...). [onFailed]: anything else went wrong (the screen left meanwhile, a result that cannot
 * be read), which says nothing about the phone.
 */
@Composable
fun rememberDocumentScanner(
    onScanned: (List<Uri>) -> Unit,
    onStarted: () -> Unit,
    onUnavailable: (Exception) -> Unit,
    onFailed: (Exception) -> Unit,
): (ScannerMode) -> Unit {
    val activity = checkNotNull(LocalActivity.current) { "the document scanner needs an activity" }
    val currentOnScanned by rememberUpdatedState(onScanned)
    val currentOnStarted by rememberUpdatedState(onStarted)
    val currentOnUnavailable by rememberUpdatedState(onUnavailable)
    val currentOnFailed by rememberUpdatedState(onFailed)
    // One contract: a new one at each recomposition would register the launcher again each time.
    val contract = remember { ActivityResultContracts.StartIntentSenderForResult() }
    val launcher = rememberLauncherForActivityResult(contract) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            try {
                val pages = GmsDocumentScanningResult.fromActivityResultIntent(result.data)?.pages.orEmpty()
                currentOnScanned(pages.map { it.imageUri })
            } catch (e: Exception) {
                currentOnFailed(e)
            }
        } else {
            currentOnScanned(emptyList())
        }
    }
    return remember(activity, launcher) {
        { mode ->
            try {
                GmsDocumentScanning.getClient(scannerOptions(mode))
                    .getStartScanIntent(activity)
                    .addOnSuccessListener { intentSender ->
                        currentOnStarted()
                        // Runs later, on the main thread: by then the screen (and the launcher's
                        // registration) may be gone.
                        try {
                            launcher.launch(IntentSenderRequest.Builder(intentSender).build())
                        } catch (e: Exception) {
                            currentOnFailed(e)
                        }
                    }
                    .addOnFailureListener { currentOnUnavailable(it) }
            } catch (e: Exception) {
                // Google Play services can be missing, outdated or disabled on the phone.
                currentOnUnavailable(e)
            }
        }
    }
}
