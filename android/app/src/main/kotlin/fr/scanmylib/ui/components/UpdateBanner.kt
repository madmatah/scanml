package fr.scanmylib.ui.components

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.util.Log
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import fr.scanmylib.R
import fr.scanmylib.update.UpdateFailure
import fr.scanmylib.update.UpdateState

/**
 * The update the PC offers, for the library and the settings: "ScanMyLib 0.8.0 is available ·
 * Install", Android's permission to ask first, the download, or why it failed, with Android's
 * message behind "Details". Nothing for the other states.
 */
@Composable
fun UpdateBanner(
    state: UpdateState,
    onInstall: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    if (state !is UpdateState.WithUpdate) return
    val context = LocalContext.current
    val version = state.update.version
    val isError = state is UpdateState.Failed
    var showsDetail by remember(state) { mutableStateOf(false) }
    val colors = if (isError) {
        CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
            contentColor = MaterialTheme.colorScheme.onErrorContainer,
        )
    } else {
        CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
        )
    }
    Card(colors = colors, modifier = modifier.fillMaxWidth()) {
        Column(
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(start = 16.dp, top = 12.dp, end = 8.dp, bottom = 4.dp),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(painterResource(if (isError) R.drawable.ic_error else R.drawable.ic_system_update), contentDescription = null)
                val text = when (state) {
                    is UpdateState.Available -> stringResource(R.string.update_available, version)
                    is UpdateState.NeedsPermission -> stringResource(R.string.update_permission, version)
                    is UpdateState.Downloading ->
                        stringResource(R.string.update_downloading, version, (state.progress * 100).toInt())
                    is UpdateState.Installing -> stringResource(R.string.update_installing, version)
                    is UpdateState.Failed -> failureText(state.failure)
                }
                // Read out when it changes, but not at each percent: the progress bar gives it when focused.
                val announced = if (state is UpdateState.Downloading) {
                    stringResource(R.string.update_downloading_announced, version)
                } else {
                    text
                }
                Text(
                    text,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier
                        .weight(1f)
                        .clearAndSetSemantics {
                            contentDescription = announced
                            liveRegion = LiveRegionMode.Polite
                        },
                )
            }
            if (state is UpdateState.Downloading) {
                LinearProgressIndicator(progress = { state.progress }, modifier = Modifier.fillMaxWidth().padding(end = 8.dp))
            }
            Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                when (state) {
                    is UpdateState.Available -> TextButton(onClick = onInstall) { Text(stringResource(R.string.update_install)) }
                    is UpdateState.NeedsPermission ->
                        TextButton(onClick = { context.openInstallPermission() }) { Text(stringResource(R.string.update_allow)) }
                    is UpdateState.Downloading -> TextButton(onClick = onCancel) { Text(stringResource(R.string.cancel)) }
                    is UpdateState.Installing -> {
                        // Android's prompt, left without an answer: shown again from here.
                        state.confirmation?.let { confirmation ->
                            TextButton(onClick = { context.showPrompt(confirmation) }) {
                                Text(stringResource(R.string.update_continue))
                            }
                        }
                        TextButton(onClick = onCancel) { Text(stringResource(R.string.cancel)) }
                    }
                    is UpdateState.Failed -> {
                        if (state.detail != null) {
                            TextButton(onClick = { showsDetail = true }) { Text(stringResource(R.string.update_details)) }
                        }
                        TextButton(onClick = onInstall) { Text(stringResource(R.string.retry)) }
                    }
                }
            }
        }
    }
    val detail = (state as? UpdateState.Failed)?.detail
    if (showsDetail && detail != null) DetailDialog(detail, onClose = { showsDetail = false })
}

/** Android's message on a failed install, as it gave it: selectable, to pass on. */
@Composable
private fun DetailDialog(detail: String, onClose: () -> Unit) {
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(stringResource(R.string.update_details_title)) },
        text = {
            SelectionContainer(Modifier.verticalScroll(rememberScrollState())) {
                Text(detail, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.close)) } },
    )
}

@Composable
private fun failureText(failure: UpdateFailure): String = when (failure) {
    UpdateFailure.DOWNLOAD -> stringResource(R.string.update_failed_download)
    UpdateFailure.STORAGE_FULL -> stringResource(R.string.message_storage_full)
    UpdateFailure.NOT_AS_ANNOUNCED -> stringResource(R.string.update_failed_not_as_announced)
    UpdateFailure.UNREADABLE -> stringResource(R.string.update_failed_unreadable)
    UpdateFailure.OTHER_APP -> stringResource(R.string.update_failed_other_app)
    UpdateFailure.NOT_NEWER -> stringResource(R.string.update_failed_not_newer)
    UpdateFailure.OTHER_SIGNER -> stringResource(R.string.update_failed_other_signer)
    // Android's message, if any, behind "Details".
    UpdateFailure.INSTALL -> stringResource(R.string.update_failed_install)
}

/** Android's prompt to confirm the install, from the screen. */
private fun Context.showPrompt(confirmation: Intent) {
    try {
        startActivity(Intent(confirmation))
    } catch (e: ActivityNotFoundException) {
        Log.w("UpdateBanner", "no installer prompt", e)
    }
}

/** Android's page to allow ScanMyLib to install apps; the updater goes on once back (AppUpdater.onReturn). */
private fun Context.openInstallPermission() {
    try {
        startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, "package:$packageName".toUri()))
    } catch (e: ActivityNotFoundException) {
        Log.w("UpdateBanner", "no page to allow installing apps", e)
    }
}
