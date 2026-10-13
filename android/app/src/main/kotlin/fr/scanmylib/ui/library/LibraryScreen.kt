@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.library

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.scanmylib.R
import fr.scanmylib.api.ServerStatus
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.LibraryRow
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.ui.components.MessageCard
import fr.scanmylib.ui.components.ServerImage
import fr.scanmylib.ui.components.StatusLine
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.ocrStateLabel
import fr.scanmylib.ui.components.pageStatsText

@Composable
fun LibraryScreen(
    onOpenDocument: (String) -> Unit,
    onOpenSettings: () -> Unit,
    viewModel: LibraryViewModel = viewModel(factory = LibraryViewModel.Factory),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    var creatingDocument by rememberSaveable { mutableStateOf(false) }
    val currentOnOpenDocument by rememberUpdatedState(onOpenDocument)
    LaunchedEffect(viewModel) {
        viewModel.documentsToOpen.collect { currentOnOpenDocument(it) }
    }
    // While visible, the screen follows the upload of the pages, then their processing on the PC.
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(viewModel, lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { viewModel.keepUpToDate() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.app_name)) },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(painterResource(R.drawable.ic_settings), stringResource(R.string.settings_title))
                    }
                },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { creatingDocument = true },
                icon = { Icon(painterResource(R.drawable.ic_add), contentDescription = null) },
                text = { Text(stringResource(R.string.library_new_document)) },
            )
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.refreshing,
            onRefresh = viewModel::refresh,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 88.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                item(key = "pc") { PcStatusCard(state.pc) }
                if (state.documents.isEmpty()) {
                    item(key = "empty") { EmptyLibrary() }
                }
                items(state.documents, key = { it.document.id }) { row ->
                    DocumentCard(
                        row,
                        stagedPages = state.stagedPages[row.document.id] ?: 0,
                        server = state.server,
                        onClick = { onOpenDocument(row.document.id) },
                    )
                }
            }
        }
    }

    if (creatingDocument) {
        NewDocumentDialog(
            onDismiss = { creatingDocument = false },
            onCreate = {
                creatingDocument = false
                viewModel.createDocument(it)
            },
        )
    }
}

@Composable
private fun PcStatusCard(pc: PcState) {
    when (pc) {
        PcState.Unknown -> Unit
        is PcState.Online -> MessageCard(pcOnlineText(pc.status), R.drawable.ic_cloud_done)
        PcState.Unreachable -> MessageCard(stringResource(R.string.library_pc_unreachable), R.drawable.ic_cloud_off)
        PcState.TokenRefused -> MessageCard(
            stringResource(R.string.library_pc_token_refused),
            R.drawable.ic_error,
            isError = true,
        )
        is PcState.Error -> MessageCard(
            stringResource(R.string.library_pc_error, pc.detail),
            R.drawable.ic_error,
            isError = true,
        )
    }
}

@Composable
private fun pcOnlineText(status: ServerStatus): String {
    val ocr = ocrStateLabel(status.ocr.state)
    val ocrError = status.ocr.lastError
    val waiting = status.queue.queued + status.queue.processing
    return when {
        status.ocr.state == "error" && ocrError != null -> stringResource(R.string.library_pc_online_ocr_error, ocrError)
        waiting == 0 -> stringResource(R.string.library_pc_online_idle, ocr)
        else -> pluralStringResource(R.plurals.library_pc_online_busy, waiting, ocr, waiting)
    }
}

@Composable
private fun EmptyLibrary() {
    Text(
        stringResource(R.string.library_empty),
        style = MaterialTheme.typography.bodyLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 48.dp, horizontal = 16.dp),
    )
}

@Composable
private fun DocumentCard(row: LibraryRow, stagedPages: Int, server: ServerConfig?, onClick: () -> Unit) {
    val document = row.document
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(12.dp)) {
            Cover(document, server)
            Column(verticalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.weight(1f)) {
                Text(
                    document.title,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (document.author.isNotEmpty()) {
                    Text(
                        document.author,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                val serverState = document.server
                if (serverState == null) {
                    Text(stringResource(R.string.document_not_on_pc_yet), style = MaterialTheme.typography.bodySmall)
                } else {
                    if (serverState.coverage.isNotEmpty()) {
                        Text(
                            stringResource(R.string.document_coverage, serverState.coverage),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Text(
                        pageStatsText(serverState),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                UploadStatus(row, stagedPages)
            }
        }
    }
}

@Composable
private fun Cover(document: DocumentEntity, server: ServerConfig?) {
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .size(width = 56.dp, height = 72.dp)
            .clip(MaterialTheme.shapes.small)
            .background(MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Icon(
            painterResource(document.kind.iconRes()),
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        document.server?.coverThumbUrl?.let { url ->
            ServerImage(server, url, contentDescription = null, modifier = Modifier.matchParentSize())
        }
    }
}

/** Where the document's local pages are: waiting for the user's confirmation, for upload, or refused. */
@Composable
private fun UploadStatus(row: LibraryRow, stagedPages: Int) {
    if (stagedPages > 0) {
        // Not sent yet: opening the document shows them, to send or discard.
        StatusLine(
            pluralStringResource(R.plurals.library_pages_to_confirm, stagedPages, stagedPages),
            R.drawable.ic_schedule,
            color = MaterialTheme.colorScheme.tertiary,
        )
    }
    if (row.pagesToUpload > 0) {
        StatusLine(
            pluralStringResource(R.plurals.library_pages_to_upload, row.pagesToUpload, row.pagesToUpload),
            R.drawable.ic_cloud_upload,
            color = MaterialTheme.colorScheme.primary,
        )
    }
    if (row.failedPages > 0) {
        StatusLine(
            pluralStringResource(R.plurals.library_pages_failed, row.failedPages, row.failedPages),
            R.drawable.ic_error,
            color = MaterialTheme.colorScheme.error,
        )
    }
    if (row.document.uploadError != null) {
        StatusLine(
            stringResource(R.string.library_document_refused),
            R.drawable.ic_error,
            color = MaterialTheme.colorScheme.error,
        )
    }
}
