package fr.scanmylib.update

import android.content.ActivityNotFoundException
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.util.Log
import androidx.core.content.IntentCompat
import fr.scanmylib.ScanMyLibApplication

/**
 * Receives the results of the update's installer session (not exported: only the app's own
 * pending intent reaches it). When Android needs the user to confirm the current install, it
 * shows its prompt.
 */
class UpdateInstallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        val sessionId = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -1)
        val confirmation = if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            IntentCompat.getParcelableExtra(intent, Intent.EXTRA_INTENT, Intent::class.java)
        } else {
            null
        }
        val updates = (context.applicationContext as ScanMyLibApplication).container.updates
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        // Never the prompt of an install the user canceled.
        if (!updates.onInstallResult(sessionId, status, message, confirmation)) return
        // Shown now if the app is in front; otherwise Android blocks it, and the banner offers it.
        try {
            confirmation?.let { context.startActivity(Intent(it).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        } catch (e: ActivityNotFoundException) {
            Log.w("UpdateInstall", "no installer prompt", e)
        }
    }
}
