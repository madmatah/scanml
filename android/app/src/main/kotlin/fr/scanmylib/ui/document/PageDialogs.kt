package fr.scanmylib.ui.document

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadFailure
import fr.scanmylib.db.UploadState
import fr.scanmylib.ui.components.MAX_PAGE_LABEL_GRAPHEMES
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.components.sanitizeTextFromPc

/** Details of a local scan, with retry (if refused) and delete (unless uploading). */
@Composable
fun LocalPageDialog(page: PendingPageEntity, onRetry: () -> Unit, onDelete: () -> Unit, onDismiss: () -> Unit) {
    val deletable = page.state == UploadState.QUEUED || page.state == UploadState.FAILED
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.local_page_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(page.state.labelRes()), style = MaterialTheme.typography.titleSmall)
                page.pageNumberHint?.let { Text(stringResource(R.string.local_page_hint, it)) }
                page.failure?.let { failure ->
                    val reason = stringResource(failure.labelRes())
                    when {
                        page.state == UploadState.FAILED -> Text(
                            stringResource(R.string.local_page_failed, reason),
                            color = MaterialTheme.colorScheme.error,
                        )

                        // Retrying cannot help until the phone is paired again.
                        failure == UploadFailure.UNAUTHORIZED -> Text(
                            stringResource(R.string.local_page_needs_pairing),
                            color = MaterialTheme.colorScheme.error,
                        )

                        else -> Text(stringResource(R.string.local_page_will_retry, reason))
                    }
                }
                page.lastError?.let {
                    Text(
                        stringResource(R.string.error_detail, sanitizeTextFromPc(it)),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (page.attempts > 0) {
                    Text(
                        pluralStringResource(R.plurals.local_page_attempts, page.attempts, page.attempts),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        confirmButton = {
            if (page.state == UploadState.FAILED) {
                TextButton(onClick = onRetry) { Text(stringResource(R.string.retry)) }
            } else {
                TextButton(onClick = onDismiss) { Text(stringResource(R.string.close)) }
            }
        },
        dismissButton = {
            if (deletable) {
                TextButton(onClick = onDelete) {
                    Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error)
                }
            }
        },
    )
}

/** Details of a page known by the server. */
@Composable
fun ServerPageDialog(page: ServerPageEntity, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            val label = sanitizeTextFromPc(page.pageLabel.orEmpty(), MAX_PAGE_LABEL_GRAPHEMES)
            Text(
                if (label.isEmpty()) {
                    stringResource(R.string.page_without_number)
                } else {
                    stringResource(R.string.page_label, label)
                },
            )
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(stringResource(page.status.labelRes()), style = MaterialTheme.typography.titleSmall)
                page.numberSource?.let { Text(stringResource(it.labelRes())) }
                if (page.duplicate) Text(stringResource(R.string.server_page_duplicate))
                if (page.excluded) Text(stringResource(R.string.server_page_excluded))
                page.error?.let {
                    Text(
                        stringResource(R.string.error_detail, sanitizeTextFromPc(it)),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.close)) }
        },
    )
}
