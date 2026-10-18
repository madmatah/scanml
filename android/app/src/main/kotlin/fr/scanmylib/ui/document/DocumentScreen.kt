@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.document

import android.content.ActivityNotFoundException
import android.content.res.Resources
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickMultipleVisualMedia
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyGridScope
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.scanmylib.R
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.BackButton
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.components.pageStatsText

@Composable
fun DocumentScreen(
    onBack: () -> Unit,
    onOpenCamera: () -> Unit,
    /** Photos shared from another app, to import into the run when the screen first opens. */
    sharedPhotos: List<Uri> = emptyList(),
    /** Opens the default camera when the screen first opens, once the settings are read. */
    scanOnOpen: Boolean = false,
    /** Opens the photo picker when the screen first opens. */
    importOnOpen: Boolean = false,
    /** A source to open now: the camera screen could not open the camera ([onSwitchHandled] once done). */
    switchToSource: ScanSource? = null,
    onSwitchHandled: () -> Unit = {},
    viewModel: DocumentViewModel = viewModel(factory = DocumentViewModel.Factory),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val scan by viewModel.scanState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val resources = LocalResources.current
    // While visible, the screen follows the upload of the pages, then their processing on the PC.
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(viewModel, lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { viewModel.keepUpToDate() }
    }
    val launchScanner = rememberDocumentScanner(
        onScanned = viewModel::onPagesScanned,
        onStarted = viewModel::onScannerStarted,
        onUnavailable = viewModel::onScannerUnavailable,
        onFailed = viewModel::onScannerFailed,
    )
    // The system photo picker needs no storage permission (it falls back to the document picker
    // on phones without it). One contract: a new one at each recomposition would register the
    // launcher again each time.
    val pickPhotosContract = remember { PickMultipleVisualMedia() }
    val pickPhotos = rememberLauncherForActivityResult(pickPhotosContract, viewModel::onPhotosPicked)
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
    // A camera opens at once, with no question: the numbering is set while reviewing the pages.
    val openCamera = { camera: ScanSource, makeDefault: Boolean ->
        if (makeDefault) viewModel.makeDefaultCamera(camera)
        when (camera) {
            ScanSource.GOOGLE_SCANNER -> launchScanner(scan.scannerMode)
            ScanSource.CAMERA -> onOpenCamera()
            ScanSource.PHOTO_PICKER -> importPhotos()
        }
    }
    val currentOpenCamera by rememberUpdatedState(openCamera)
    LaunchedEffect(viewModel) {
        viewModel.messages.collect { message ->
            if (message == DocumentMessage.ScannerUnavailable && scan.hasCamera) {
                // The app's camera works without Google Play services.
                val result = snackbarHostState.showSnackbar(
                    message.text(resources),
                    actionLabel = resources.getString(R.string.scan_source_camera),
                    withDismissAction = true,
                    duration = SnackbarDuration.Long,
                )
                if (result == SnackbarResult.ActionPerformed) currentOpenCamera(ScanSource.CAMERA, false)
            } else {
                snackbarHostState.showSnackbar(
                    message.text(resources),
                    withDismissAction = message.important,
                    duration = if (message.important) SnackbarDuration.Long else SnackbarDuration.Short,
                )
            }
        }
    }
    var choosingCamera by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(viewModel, sharedPhotos) {
        if (sharedPhotos.isNotEmpty()) viewModel.importSharedPhotos(sharedPhotos)
    }
    // Again once the settings are read: before, the default camera is not known.
    LaunchedEffect(viewModel, scanOnOpen, scan.loaded) {
        if (scanOnOpen && scan.loaded && viewModel.takeActionOnOpen()) currentOpenCamera(scan.camera, false)
    }
    LaunchedEffect(viewModel, importOnOpen) {
        if (importOnOpen && viewModel.takeActionOnOpen()) importPhotos()
    }
    LaunchedEffect(switchToSource, scan.loaded) {
        val source = switchToSource ?: return@LaunchedEffect
        if (!scan.loaded) return@LaunchedEffect
        onSwitchHandled()
        if (source == ScanSource.PHOTO_PICKER) importPhotos() else currentOpenCamera(source, false)
    }
    // Ids rather than entities: the dialogs follow the live state of the page.
    var selectedLocalPage by rememberSaveable { mutableStateOf<String?>(null) }
    var selectedServerPage by rememberSaveable { mutableStateOf<String?>(null) }
    val document = state.document
    // A run waiting for confirmation shows unless more pages are being added to it.
    val reviewVisible = !scan.preparing && scan.stagedPages.isNotEmpty()
    // Messages show in the review dialog: behind it, they would be dimmed.
    val messagesInDialog = reviewVisible

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(document?.title.orEmpty(), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { BackButton(onBack) },
            )
        },
        floatingActionButton = {
            if (document != null) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // On a narrow screen, or with large text, "Import" keeps its icon only.
                    val density = LocalDensity.current
                    val width = with(density) { LocalWindowInfo.current.containerSize.width.toDp() }
                    val roomy = width.value / density.fontScale >= ROOMY_WIDTH_DP
                    val importLabel = stringResource(R.string.scan_source_picker)
                    ExtendedFloatingActionButton(
                        onClick = importPhotos,
                        expanded = roomy,
                        icon = { Icon(painterResource(R.drawable.ic_photo_library), contentDescription = null) },
                        text = { Text(importLabel) },
                        containerColor = MaterialTheme.colorScheme.secondaryContainer,
                        contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
                        modifier = Modifier.semantics { contentDescription = importLabel },
                    )
                    ScanButton(
                        camera = scan.camera,
                        enabled = scan.loaded,
                        onScan = { openCamera(scan.camera, false) },
                        onChooseCamera = { choosingCamera = true },
                    )
                }
            }
        },
        snackbarHost = { if (!messagesInDialog) SnackbarHost(snackbarHostState) },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.refreshing,
            onRefresh = viewModel::refresh,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            when {
                state.loading -> Unit

                document == null -> DocumentGone()

                else -> LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 104.dp),
                    contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 88.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxSize(),
                ) {
                    fullWidthItem("summary") {
                        DocumentSummary(document, onRetryUpload = viewModel::retryDocumentUpload)
                    }
                    val pages = state.pages
                    if (pages.local.isNotEmpty()) {
                        fullWidthItem("local") {
                            SectionTitle(
                                pluralStringResource(
                                    R.plurals.document_local_pages,
                                    pages.local.size,
                                    pages.local.size,
                                ),
                            )
                        }
                        items(pages.local, key = { it.id }) { page ->
                            LocalPageTile(
                                page,
                                viewModel.localImage(page),
                                state.server,
                                onClick = { selectedLocalPage = page.id },
                            )
                        }
                    }
                    fullWidthItem("server") {
                        SectionTitle(
                            pluralStringResource(R.plurals.document_server_pages, pages.server.size, pages.server.size),
                        )
                    }
                    if (pages.isEmpty) {
                        fullWidthItem("empty") { NoPagesYet() }
                    }
                    items(pages.server, key = { it.id }) { page ->
                        ServerPageTile(page, state.server, onClick = { selectedServerPage = page.id })
                    }
                }
            }
        }
    }

    if (choosingCamera && document != null) {
        CameraSheet(
            scan = scan,
            onChoose = { camera, makeDefault ->
                choosingCamera = false
                openCamera(camera, makeDefault)
            },
            onDismiss = { choosingCamera = false },
        )
    }
    scan.preparation?.let { preparation ->
        PreparingPagesDialog(preparation, onCancel = viewModel::cancelPreparation)
    }
    if (reviewVisible) {
        ScanReviewDialog(
            scan = scan,
            snackbarHostState = snackbarHostState,
            onFirstPageChange = viewModel::onFirstPageChange,
            onConsecutiveChange = viewModel::onConsecutiveChange,
            onConfirm = viewModel::confirmScan,
            onDiscard = viewModel::discardScan,
            onRemovePage = viewModel::removeStagedPage,
            onScanMore = { camera -> openCamera(camera, false) },
            onImportMore = importPhotos,
            // The run stays on the phone; the library shows it waits.
            onLater = onBack,
        )
    }
    state.pages.local.firstOrNull { it.id == selectedLocalPage }?.let { page ->
        LocalPageDialog(
            page = page,
            onRetry = {
                viewModel.retryPage(page.id)
                selectedLocalPage = null
            },
            onDelete = {
                viewModel.deletePage(page.id)
                selectedLocalPage = null
            },
            onDismiss = { selectedLocalPage = null },
        )
    }
    state.pages.server.firstOrNull { it.id == selectedServerPage }?.let { page ->
        ServerPageDialog(page, onDismiss = { selectedServerPage = null })
    }
}

/**
 * "Scan", split: the main part opens [camera] at once; the chevron, or a long press, offers the
 * cameras to choose from ([onChooseCamera]). Disabled until the default camera is known.
 */
@Composable
private fun ScanButton(camera: ScanSource, enabled: Boolean, onScan: () -> Unit, onChooseCamera: () -> Unit) {
    val chooseLabel = stringResource(R.string.document_choose_camera)
    val cameraLabel = stringResource(camera.labelRes())
    Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        Surface(
            shape = RoundedCornerShape(topStart = 16.dp, bottomStart = 16.dp, topEnd = 4.dp, bottomEnd = 4.dp),
            color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            shadowElevation = 6.dp,
            modifier = Modifier.height(56.dp),
        ) {
            // Inside the surface, so that the ripple follows its shape.
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxHeight()
                    .combinedClickable(
                        enabled = enabled,
                        role = Role.Button,
                        onLongClickLabel = chooseLabel,
                        onLongClick = onChooseCamera,
                        onClick = onScan,
                    )
                    // Which camera opens: "Scan, Google scanner".
                    .semantics { stateDescription = cameraLabel }
                    .padding(start = 16.dp, end = 20.dp),
            ) {
                Icon(painterResource(camera.iconRes()), contentDescription = null)
                Text(stringResource(R.string.document_scan), style = MaterialTheme.typography.labelLarge)
            }
        }
        Surface(
            onClick = onChooseCamera,
            shape = RoundedCornerShape(topStart = 4.dp, bottomStart = 4.dp, topEnd = 16.dp, bottomEnd = 16.dp),
            color = MaterialTheme.colorScheme.primaryContainer,
            contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            shadowElevation = 6.dp,
            modifier = Modifier.size(width = 48.dp, height = 56.dp),
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(painterResource(R.drawable.ic_expand_more), contentDescription = chooseLabel)
            }
        }
    }
}

/** Screen width, in dp of text at its normal size, from which "Import" shows its label. */
private const val ROOMY_WIDTH_DP = 380

private fun LazyGridScope.fullWidthItem(key: String, content: @Composable () -> Unit) {
    item(key = key, span = { GridItemSpan(maxLineSpan) }) { content() }
}

@Composable
private fun DocumentSummary(document: DocumentEntity, onRetryUpload: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(painterResource(document.kind.iconRes()), contentDescription = null)
                val kind = stringResource(document.kind.labelRes())
                Text(
                    if (document.author.isEmpty()) kind else "$kind · ${document.author}",
                    style = MaterialTheme.typography.titleSmall,
                )
            }
            val server = document.server
            if (server == null) {
                Text(stringResource(R.string.document_not_on_pc_yet_long), style = MaterialTheme.typography.bodyMedium)
            } else {
                val noCoverage = stringResource(R.string.document_coverage_none)
                Text(stringResource(R.string.document_coverage, server.coverage.ifEmpty { noCoverage }))
                if (server.missing.isNotEmpty()) {
                    Text(stringResource(R.string.document_missing, server.missing))
                }
                if (server.unnumbered > 0) {
                    Text(pluralStringResource(R.plurals.document_unnumbered, server.unnumbered, server.unnumbered))
                }
                Text(
                    pageStatsText(server),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (server.duplicates > 0) {
                    Text(
                        pluralStringResource(R.plurals.document_duplicates, server.duplicates, server.duplicates),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (server.excluded > 0) {
                    Text(
                        pluralStringResource(R.plurals.document_excluded, server.excluded, server.excluded),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (server.folder.isNotEmpty()) {
                    Text(
                        stringResource(R.string.document_folder, server.folder),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (document.unwarp) {
                Text(stringResource(R.string.document_unwarp_on), style = MaterialTheme.typography.bodySmall)
            }
            document.uploadError?.let { error ->
                Text(stringResource(R.string.document_upload_refused, error), color = MaterialTheme.colorScheme.error)
                TextButton(onClick = onRetryUpload) { Text(stringResource(R.string.retry)) }
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 8.dp))
}

@Composable
private fun NoPagesYet() {
    Text(
        stringResource(R.string.document_no_pages),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        textAlign = TextAlign.Center,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 32.dp),
    )
}

@Composable
private fun DocumentGone() {
    Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
        Text(
            stringResource(R.string.document_gone),
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(32.dp),
        )
    }
}

private fun DocumentMessage.text(resources: Resources): String = when (this) {
    DocumentMessage.Unreachable -> resources.getString(R.string.message_pc_unreachable)

    DocumentMessage.TokenRefused -> resources.getString(R.string.message_token_refused)

    is DocumentMessage.ServerError -> resources.getString(R.string.message_server_error, detail)

    is DocumentMessage.PagesQueued -> resources.getQuantityString(R.plurals.message_pages_queued, count, count)

    DocumentMessage.ImportFailed -> resources.getString(R.string.message_import_failed)

    DocumentMessage.SendFailed -> resources.getString(R.string.message_send_failed)

    DocumentMessage.StorageFull -> resources.getString(R.string.message_storage_full)

    is DocumentMessage.PhotosSkipped -> listOfNotNull(
        unsupported.takeIf { it > 0 }?.let {
            resources.getQuantityString(R.plurals.message_unsupported_photos, it, it)
        },
        tooLarge.takeIf { it > 0 }?.let { resources.getQuantityString(R.plurals.message_too_large_photos, it, it) },
        unreadable.takeIf { it > 0 }?.let { resources.getQuantityString(R.plurals.message_unreadable_photos, it, it) },
    ).joinToString(" ")

    DocumentMessage.AddingInterrupted -> resources.getString(R.string.message_adding_interrupted)

    DocumentMessage.SettingNotSaved -> resources.getString(R.string.message_setting_not_saved)

    DocumentMessage.ScannerUnavailable -> resources.getString(R.string.message_scanner_unavailable)

    DocumentMessage.ScannerFailed -> resources.getString(R.string.message_scanner_failed)

    DocumentMessage.PhotoPickerUnavailable -> resources.getString(R.string.message_photo_picker_unavailable)

    DocumentMessage.PageBusy -> resources.getString(R.string.message_page_busy)
}
