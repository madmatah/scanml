package fr.scanmylib.ui.document

import android.content.pm.PackageManager
import androidx.annotation.StringRes
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.DialogProperties
import coil3.compose.AsyncImage
import fr.scanmylib.R
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.library.StagedPage
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.LocalImage

/**
 * Before scanning: where the pages come from, their optional numbering, then the scanner. The
 * pages join the run waiting for confirmation, if there is one. Messages show in the dialog
 * ([snackbarHostState]): behind it, they would be dimmed.
 */
@Composable
fun ScanSetupDialog(
    scan: ScanUiState,
    snackbarHostState: SnackbarHostState,
    onSourceChange: (ScanSource) -> Unit,
    onFirstPageChange: (String) -> Unit,
    onConsecutiveChange: (Boolean) -> Unit,
    onStart: () -> Unit,
    onDismiss: () -> Unit,
) {
    val context = LocalContext.current
    val hasCamera = remember(context) { context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) }
    val sourceAvailable = scan.source != ScanSource.CAMERA || hasCamera
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.scan_setup_title)) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                val waiting = scan.stagedPages.size
                if (waiting > 0) {
                    Text(
                        pluralStringResource(R.plurals.scan_setup_adding, waiting, waiting),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                Column(Modifier.selectableGroup()) {
                    ScanSource.entries.forEach { source ->
                        SourceOption(
                            source = source,
                            selected = scan.source == source,
                            enabled = source != ScanSource.CAMERA || hasCamera,
                            onSelect = { onSourceChange(source) },
                        )
                    }
                }
                Text(stringResource(R.string.scan_setup_help), style = MaterialTheme.typography.bodyMedium)
                NumberingFields(scan, onFirstPageChange, onConsecutiveChange)
                SnackbarHost(snackbarHostState)
            }
        },
        confirmButton = {
            TextButton(onClick = onStart, enabled = scan.numbering != null && sourceAvailable) {
                Text(stringResource(scan.source.startLabelRes()))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
        },
    )
}

@Composable
private fun SourceOption(source: ScanSource, selected: Boolean, enabled: Boolean, onSelect: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .selectable(selected = selected, enabled = enabled, role = Role.RadioButton, onClick = onSelect)
            .padding(vertical = 4.dp),
    ) {
        RadioButton(selected = selected, onClick = null, enabled = enabled)
        Column(
            Modifier
                .weight(1f)
                .padding(start = 12.dp),
        ) {
            Text(stringResource(source.labelRes()), style = MaterialTheme.typography.bodyLarge)
            Text(
                stringResource(source.descriptionRes()),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@StringRes
private fun ScanSource.labelRes(): Int = when (this) {
    ScanSource.GOOGLE_SCANNER -> R.string.scan_source_google
    ScanSource.CAMERA -> R.string.scan_source_camera
    ScanSource.PHOTO_PICKER -> R.string.scan_source_picker
}

@StringRes
private fun ScanSource.descriptionRes(): Int = when (this) {
    ScanSource.GOOGLE_SCANNER -> R.string.scan_source_google_help
    ScanSource.CAMERA -> R.string.scan_source_camera_help
    ScanSource.PHOTO_PICKER -> R.string.scan_source_picker_help
}

@StringRes
private fun ScanSource.startLabelRes(): Int = when (this) {
    ScanSource.GOOGLE_SCANNER -> R.string.scan_setup_start
    ScanSource.CAMERA -> R.string.scan_setup_start_camera
    ScanSource.PHOTO_PICKER -> R.string.scan_setup_start_picker
}

/**
 * After scanning: the pages of the run, in order, whose numbering can still be set or corrected
 * before they are queued. A page can be looked at and taken out ([onRemovePage]), more pages can
 * join the run ([onAddPages]), and the run can wait for later ([onLater], or Back): it stays on
 * the phone. A tap outside does nothing, and discarding the run asks first, so that a stray tap
 * cannot lose it. Messages show in the dialog ([snackbarHostState]): behind it, they would be
 * dimmed.
 */
@Composable
fun ScanReviewDialog(
    scan: ScanUiState,
    snackbarHostState: SnackbarHostState,
    onFirstPageChange: (String) -> Unit,
    onConsecutiveChange: (Boolean) -> Unit,
    onConfirm: () -> Unit,
    onDiscard: () -> Unit,
    onRemovePage: (StagedPage) -> Unit,
    onAddPages: () -> Unit,
    onLater: () -> Unit,
) {
    val count = scan.stagedPages.size
    var confirmingDiscard by rememberSaveable { mutableStateOf(false) }
    // The page shown large, by file.
    var shownPage by rememberSaveable { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = { if (!scan.sending) onLater() },
        properties = DialogProperties(dismissOnClickOutside = false),
        title = { Text(pluralStringResource(R.plurals.scan_review_title, count, count)) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
            ) {
                StagedPagesStrip(scan.stagedPages, onClick = { if (!scan.sending) shownPage = it.file.path })
                TextButton(onClick = onAddPages, enabled = !scan.sending) {
                    Icon(painterResource(R.drawable.ic_add), contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text(stringResource(R.string.scan_review_add))
                }
                NumberingFields(scan, onFirstPageChange, onConsecutiveChange)
                Text(
                    numberingSummary(scan.numbering, count),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                SnackbarHost(snackbarHostState)
            }
        },
        confirmButton = {
            TextButton(onClick = onConfirm, enabled = scan.numbering != null && !scan.sending) {
                Text(stringResource(R.string.scan_review_confirm))
            }
        },
        dismissButton = {
            Row {
                TextButton(onClick = { confirmingDiscard = true }, enabled = !scan.sending) {
                    Text(stringResource(R.string.scan_review_discard))
                }
                TextButton(onClick = onLater, enabled = !scan.sending) {
                    Text(stringResource(R.string.scan_review_later))
                }
            }
        },
    )
    if (confirmingDiscard) {
        DiscardRunDialog(
            count = count,
            onConfirm = {
                confirmingDiscard = false
                onDiscard()
            },
            onDismiss = { confirmingDiscard = false },
        )
    }
    val pageIndex = scan.stagedPages.indexOfFirst { it.file.path == shownPage }
    if (pageIndex >= 0) {
        val page = scan.stagedPages[pageIndex]
        StagedPageDialog(
            page = page,
            position = pageIndex + 1,
            count = count,
            onRemove = {
                shownPage = null
                onRemovePage(page)
            },
            onDismiss = { shownPage = null },
        )
    }
}

/** A page of the run, large, which can be taken out of it. */
@Composable
private fun StagedPageDialog(page: StagedPage, position: Int, count: Int, onRemove: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.scan_review_page, position, count)) },
        text = {
            AsyncImage(
                model = page.file,
                contentDescription = null,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 480.dp),
            )
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.close)) }
        },
        dismissButton = {
            TextButton(onClick = onRemove) {
                Text(stringResource(R.string.scan_review_remove_page), color = MaterialTheme.colorScheme.error)
            }
        },
    )
}

/** Asks before deleting the [count] pages of a run: they exist nowhere else. */
@Composable
private fun DiscardRunDialog(count: Int, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(pluralStringResource(R.plurals.scan_discard_title, count, count)) },
        text = { Text(stringResource(R.string.scan_discard_message)) },
        confirmButton = {
            TextButton(onClick = onConfirm) {
                Text(stringResource(R.string.delete), color = MaterialTheme.colorScheme.error)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
        },
    )
}

/** Thumbnails of the pages of the run, in the order they will be sent; tapping one shows it. */
@Composable
private fun StagedPagesStrip(pages: List<StagedPage>, onClick: (StagedPage) -> Unit) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        items(pages, key = { it.file.path }) { page ->
            LocalImage(
                page.file,
                contentDescription = null,
                modifier = Modifier
                    .size(width = 48.dp, height = 68.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .clickable { onClick(page) },
            )
        }
    }
}

/** While scanned or imported images are copied to the run; an import can be canceled. */
@Composable
fun PreparingPagesDialog(preparation: Preparation, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = { if (preparation.cancellable) onCancel() },
        properties = DialogProperties(dismissOnBackPress = preparation.cancellable, dismissOnClickOutside = false),
        confirmButton = {
            if (preparation.cancellable) {
                TextButton(onClick = onCancel) { Text(stringResource(R.string.cancel)) }
            }
        },
        text = {
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(32.dp))
                Column {
                    Text(stringResource(R.string.scan_preparing), style = MaterialTheme.typography.bodyLarge)
                    if (preparation.total > 1) {
                        Text(
                            stringResource(R.string.scan_preparing_progress, preparation.done, preparation.total),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        },
    )
}

@Composable
private fun NumberingFields(
    scan: ScanUiState,
    onFirstPageChange: (String) -> Unit,
    onConsecutiveChange: (Boolean) -> Unit,
) {
    val invalid = scan.numbering == null
    OutlinedTextField(
        value = scan.firstPage,
        onValueChange = onFirstPageChange,
        label = { Text(stringResource(R.string.scan_first_page)) },
        isError = invalid,
        supportingText = {
            Text(
                if (invalid) {
                    stringResource(R.string.scan_first_page_invalid, PageNumbering.MAX_FIRST_PAGE)
                } else {
                    stringResource(R.string.scan_first_page_help)
                },
            )
        },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth(),
    )
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(stringResource(R.string.scan_consecutive))
            Text(
                stringResource(R.string.scan_consecutive_help),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Switch(
            checked = scan.consecutive,
            onCheckedChange = onConsecutiveChange,
            enabled = scan.firstPage.isNotEmpty(),
        )
    }
}

/** What the server will receive as page-number hints, in words. */
@Composable
private fun numberingSummary(numbering: PageNumbering?, count: Int): String {
    val first = numbering?.firstPage
    val last = numbering?.lastHint(count) ?: first
    return when {
        numbering == null -> stringResource(R.string.scan_summary_invalid)
        first == null -> stringResource(R.string.scan_summary_none)
        last == null || last == first -> stringResource(R.string.scan_summary_first_only, first)
        else -> stringResource(R.string.scan_summary_range, first, last)
    }
}
