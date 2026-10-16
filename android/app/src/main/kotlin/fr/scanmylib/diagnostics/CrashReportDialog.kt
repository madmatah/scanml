package fr.scanmylib.diagnostics

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.util.Log
import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.DialogProperties
import fr.scanmylib.R

/**
 * Shows the report of the last crash, to share or copy so the user can pass it on. A tap outside
 * does not close it; closing keeps the report, which "About" shows until [onDelete] deletes it
 * (null: no "Delete", as at launch).
 */
@Composable
fun CrashReportDialog(report: String, onClose: () -> Unit, onDelete: (() -> Unit)? = null) {
    val context = LocalContext.current
    AlertDialog(
        onDismissRequest = onClose,
        properties = DialogProperties(dismissOnClickOutside = false),
        title = { Text(stringResource(R.string.crash_title)) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                Text(stringResource(R.string.crash_intro))
                Text(
                    report,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 11.sp,
                    lineHeight = 14.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { context.shareReport(report) }) { Text(stringResource(R.string.crash_share)) }
        },
        dismissButton = {
            Row {
                TextButton(onClick = { context.copyReport(report) }) { Text(stringResource(R.string.crash_copy)) }
                if (onDelete != null) {
                    TextButton(onClick = onDelete) {
                        Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error)
                    }
                }
                TextButton(onClick = onClose) { Text(stringResource(R.string.crash_close)) }
            }
        },
    )
}

/** Hands the report to an app the user picks: mail, a messaging app, notes... */
private fun Context.shareReport(report: String) {
    val send = Intent(Intent.ACTION_SEND)
        .setType("text/plain")
        .putExtra(Intent.EXTRA_SUBJECT, getString(R.string.crash_share_subject))
        .putExtra(Intent.EXTRA_TEXT, report)
    try {
        startActivity(Intent.createChooser(send, getString(R.string.crash_share)))
    } catch (e: ActivityNotFoundException) {
        Log.w("CrashReport", "no app to share the report with", e)
        copyReport(report)
    }
}

private fun Context.copyReport(report: String) {
    getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("ScanMyLib", report))
    Toast.makeText(this, R.string.crash_copied, Toast.LENGTH_SHORT).show()
}
