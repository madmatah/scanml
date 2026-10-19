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
import androidx.compose.material3.FilledTonalIconButton
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
import fr.scanmylib.ui.components.UpdateBanner
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.readingUnavailable
import fr.scanmylib.update.UpdateState

@Composable
fun LibraryScreen(
    onOpenDocument: (String) -> Unit,
    onScanDocument: (String) -> Unit,
    onNewDocument: () -> Unit,
    onOpenSettings: () -> Unit,
    viewModel: LibraryViewModel = viewModel(factory = LibraryViewModel.Factory),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val update by viewModel.updateState.collectAsStateWithLifecycle()
    // While visible, the screen follows the upload of the pages, then their processing on the PC,
    // and asks the PC for an update when due.
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(viewModel, lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { viewModel.keepUpToDate() }
    }
    LibraryContent(
        state = state,
        update = update,
        onOpenDocument = onOpenDocument,
        onScanDocument = onScanDocument,
        onNewDocument = onNewDocument,
        onOpenSettings = onOpenSettings,
        onRefresh = viewModel::refresh,
        onInstallUpdate = viewModel::installUpdate,
        onCancelUpdate = viewModel::cancelUpdate,
    )
}

/** Apart from the view model, so that a test draws the library from invented state. */
@Composable
internal fun LibraryContent(
    state: LibraryUiState,
    update: UpdateState,
    onOpenDocument: (String) -> Unit,
    onScanDocument: (String) -> Unit,
    onNewDocument: () -> Unit,
    onOpenSettings: () -> Unit,
    onRefresh: () -> Unit,
    onInstallUpdate: () -> Unit,
    onCancelUpdate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Scaffold(
        modifier = modifier,
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
                onClick = onNewDocument,
                icon = { Icon(painterResource(R.drawable.ic_add), contentDescription = null) },
                text = { Text(stringResource(R.string.library_new_document)) },
            )
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.refreshing,
            onRefresh = onRefresh,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 88.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                // First, even while empty (the PC's state unknown): the list keeps its first visible
                // item in place, so an item that appears later, like the update, shows below it
                // rather than above the screen.
                item(key = "pc") { PcStatusCard(state.pc) }
                // After the PC's card: a PC that refuses the token comes first.
                if (update is UpdateState.WithUpdate) {
                    item(key = "update") {
                        UpdateBanner(update, onInstall = onInstallUpdate, onCancel = onCancelUpdate)
                    }
                }
                if (state.documents.isEmpty()) {
                    item(key = "empty") { EmptyLibrary() }
                }
                items(state.documents, key = { it.document.id }) { row ->
                    DocumentCard(
                        row,
                        stagedPages = state.stagedPages[row.document.id] ?: 0,
                        server = state.server,
                        onClick = { onOpenDocument(row.document.id) },
                        onScan = { onScanDocument(row.document.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun PcStatusCard(pc: PcState) {
    when (pc) {
        PcState.Unknown -> Unit

        is PcState.Online -> MessageCard(
            pcOnlineText(pc.status),
            if (pc.status.readingUnavailable) R.drawable.ic_error else R.drawable.ic_cloud_done,
        )

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
    val ocrError = status.ocr.lastError
    val waiting = status.queue.queued + status.queue.processing
    return when {
        status.ocr.state == "error" && ocrError != null -> stringResource(
            R.string.library_pc_online_ocr_error,
            ocrError,
        )

        status.readingUnavailable -> stringResource(R.string.library_pc_online_reading_unavailable)

        waiting == 0 -> stringResource(R.string.library_pc_online_idle)

        else -> pluralStringResource(R.plurals.library_pc_online_busy, waiting, waiting)
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

/**
 * A document: its title, author, pages and what differs from normal ([cardLines]), and a button
 * that opens it straight into its default camera ([onScan]).
 */
@Composable
private fun DocumentCard(
    row: LibraryRow,
    stagedPages: Int,
    server: ServerConfig?,
    onClick: () -> Unit,
    onScan: () -> Unit,
) {
    val document = row.document
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(start = 12.dp, top = 12.dp, end = 4.dp, bottom = 12.dp),
        ) {
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
                document.server?.takeIf { it.pages > 0 }?.let { serverState ->
                    Text(
                        pagesSummary(serverState.pages, serverState.coverage),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                cardLines(row, stagedPages).forEach { CardLineText(it) }
            }
            FilledTonalIconButton(onClick = onScan) {
                Icon(
                    painterResource(R.drawable.ic_document_scanner),
                    contentDescription = stringResource(R.string.library_scan_in, document.title),
                )
            }
        }
    }
}

/** "25 pages · pp. 12–31, 88–90": the pages on the PC, and the numbers they cover. */
@Composable
private fun pagesSummary(pages: Int, coverage: String): String {
    val count = pluralStringResource(R.plurals.stats_pages, pages, pages)
    return if (coverage.isEmpty()) count else stringResource(R.string.library_pages_summary, count, coverage)
}

@Composable
private fun CardLineText(line: CardLine) {
    when (line) {
        is CardLine.ToSend -> StatusLine(
            pluralStringResource(R.plurals.library_pages_to_confirm, line.count, line.count),
            R.drawable.ic_schedule,
            color = MaterialTheme.colorScheme.tertiary,
        )

        is CardLine.Refused -> StatusLine(
            pluralStringResource(R.plurals.library_pages_failed, line.count, line.count),
            R.drawable.ic_error,
            color = MaterialTheme.colorScheme.error,
        )

        CardLine.DocumentRefused -> StatusLine(
            stringResource(R.string.library_document_refused),
            R.drawable.ic_error,
            color = MaterialTheme.colorScheme.error,
        )

        is CardLine.ReadFailed -> StatusLine(
            pluralStringResource(R.plurals.library_pages_read_failed, line.count, line.count),
            R.drawable.ic_error,
            color = MaterialTheme.colorScheme.error,
        )

        is CardLine.InTransit -> StatusLine(
            pluralStringResource(R.plurals.library_pages_in_transit, line.count, line.count),
            R.drawable.ic_cloud_upload,
        )

        is CardLine.BeingRead -> StatusLine(
            pluralStringResource(R.plurals.library_pages_being_read, line.count, line.count),
            R.drawable.ic_autorenew,
            color = MaterialTheme.colorScheme.primary,
        )

        CardLine.NotOnPcYet -> StatusLine(stringResource(R.string.document_not_on_pc_yet), R.drawable.ic_cloud_off)
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
