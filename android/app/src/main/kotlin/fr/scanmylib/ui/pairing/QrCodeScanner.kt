package fr.scanmylib.ui.pairing

import androidx.activity.compose.LocalActivity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning

/**
 * Returns a function that opens Google's code scanner and reports the text of the scanned QR
 * code. The scanner runs in Google Play services: the app needs no camera permission.
 */
@Composable
fun rememberQrCodeScanner(onScanned: (String) -> Unit, onUnavailable: (Exception) -> Unit): () -> Unit {
    // The scanner starts its own (invisible) activity: it must be launched from an activity.
    val activity = checkNotNull(LocalActivity.current) { "the QR code scanner needs an activity" }
    val currentOnScanned by rememberUpdatedState(onScanned)
    val currentOnUnavailable by rememberUpdatedState(onUnavailable)
    return remember(activity) {
        {
            val options = GmsBarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .build()
            try {
                GmsBarcodeScanning.getClient(activity, options)
                    .startScan()
                    .addOnSuccessListener { barcode -> barcode.rawValue?.let { currentOnScanned(it) } }
                    .addOnFailureListener { currentOnUnavailable(it) }
            } catch (e: Exception) {
                // Google Play services can be missing, outdated or disabled on the phone.
                currentOnUnavailable(e)
            }
        }
    }
}
