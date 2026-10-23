@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.document

import android.content.res.Resources
import android.net.Uri
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.focusable
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
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.min
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.compose.currentStateAsState
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.scanmylib.R
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.AttentionBanner
import fr.scanmylib.ui.components.BackButton
import fr.scanmylib.ui.components.BannerSlot
import fr.scanmylib.ui.components.ErrorBanner
import fr.scanmylib.ui.components.ScreenTitle
import fr.scanmylib.ui.components.SectionHeader
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.components.pageStatsText
import fr.scanmylib.ui.components.sanitizeTextFromPc
import fr.scanmylib.ui.theme.cardColor
import java.io.File
import kotlinx.coroutines.launch

@Composable
fun DocumentScreen(
    onBack: () -> Unit,
    onOpenCamera: () -> Unit,
    onOpenReview: () -> Unit,
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
    scanViewModel: ScanViewModel = viewModel(factory = ScanViewModel.Factory),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val scan by scanViewModel.scanState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val resources = LocalResources.current
    // While visible, the screen follows the upload of the pages, then their processing on the PC.
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(viewModel, lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { viewModel.keepUpToDate() }
    }
    val currentOnOpenReview by rememberUpdatedState(onOpenReview)
    val openReview = {
        scanViewModel.onReviewOpened()
        currentOnOpenReview()
    }
    val sources = rememberScanSources(
        viewModel = scanViewModel,
        snackbarHostState = snackbarHostState,
        onOpenCamera = onOpenCamera,
        onPagesReturned = openReview,
        switchToSource = switchToSource,
        onSwitchHandled = onSwitchHandled,
    )
    val currentSources by rememberUpdatedState(sources)
    LaunchedEffect(viewModel) {
        viewModel.messages.collect { message ->
            snackbarHostState.showSnackbar(
                message.text(resources),
                withDismissAction = message.important,
                duration = if (message.important) SnackbarDuration.Long else SnackbarDuration.Short,
            )
        }
    }
    var choosingCamera by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(scanViewModel, sharedPhotos) {
        if (scanViewModel.importSharedPhotos(sharedPhotos)) openReview()
    }
    // Again once the settings are read: before, the default camera is not known.
    LaunchedEffect(scanViewModel, scanOnOpen, scan.loaded) {
        if (scanOnOpen && scan.loaded && scanViewModel.takeActionOnOpen()) currentSources.open(scan.camera)
    }
    LaunchedEffect(scanViewModel, importOnOpen) {
        if (importOnOpen && scanViewModel.takeActionOnOpen()) currentSources.importPhotos()
    }
    // Ids rather than entities: the dialogs follow the live state of the page.
    var selectedLocalPage by rememberSaveable { mutableStateOf<String?>(null) }
    var selectedServerPage by rememberSaveable { mutableStateOf<String?>(null) }
    val document = state.document
    // Only while resumed: the end is told once the review has left, on the document.
    val lifecycleState by lifecycleOwner.lifecycle.currentStateAsState()
    val isResumed = lifecycleState.isAtLeast(Lifecycle.State.RESUMED)

    DocumentContent(
        state = state,
        scan = scan,
        reviewEnd = scan.reviewEnd.takeIf { isResumed },
        snackbarHostState = snackbarHostState,
        localImage = viewModel::localImage,
        onBack = onBack,
        onRefresh = viewModel::refresh,
        onRetryDocumentUpload = viewModel::retryDocumentUpload,
        onImport = sources.importPhotos,
        onScan = { sources.open(scan.camera) },
        onChooseCamera = { choosingCamera = true },
        onOpenLocalPage = { selectedLocalPage = it },
        onOpenServerPage = { selectedServerPage = it },
        onReview = openReview,
        onDismissOutcome = scanViewModel::dismissOutcome,
        onDismissAddingInterrupted = scanViewModel::dismissAddingInterrupted,
        onReviewEndShown = scanViewModel::onReviewEndShown,
    )

    if (choosingCamera && document != null) {
        CameraSheet(
            scan = scan,
            onChoose = { camera, makeDefault ->
                choosingCamera = false
                if (makeDefault) scanViewModel.makeDefaultCamera(camera)
                sources.open(camera)
            },
            onDismiss = { choosingCamera = false },
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

/** Apart from the view models, so that a test draws the document from invented state. */
@Composable
internal fun DocumentContent(
    state: DocumentUiState,
    scan: ScanUiState,
    reviewEnd: ReviewEnd?,
    snackbarHostState: SnackbarHostState,
    localImage: (PendingPageEntity) -> File?,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onRetryDocumentUpload: () -> Unit,
    onImport: () -> Unit,
    onScan: () -> Unit,
    onChooseCamera: () -> Unit,
    onOpenLocalPage: (pageId: String) -> Unit,
    onOpenServerPage: (pageId: String) -> Unit,
    onReview: () -> Unit,
    onDismissOutcome: () -> Unit,
    onDismissAddingInterrupted: () -> Unit,
    onReviewEndShown: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val document = state.document
    val pages = state.pages
    val gridState = rememberLazyGridState()
    val focusRequesters = remember { ReviewEndFocusRequesters() }
    var focusTarget by remember { mutableStateOf<ReviewEndFocus?>(null) }
    val resources = LocalResources.current
    // The snackbar outlives the effect, which the end's clearing cancels.
    val snackbarScope = rememberCoroutineScope()
    val currentOnReviewEndShown by rememberUpdatedState(onReviewEndShown)
    LaunchedEffect(reviewEnd) {
        val end = reviewEnd ?: return@LaunchedEffect
        currentOnReviewEndShown()
        focusTarget = end.focusTarget
        val message = end.message(resources) ?: return@LaunchedEffect
        snackbarScope.launch { snackbarHostState.showSnackbar(message) }
    }
    val hasReviewButton = scan.preparing || scan.stagedPages.isNotEmpty()
    val isFocusTargetPlaced = when (focusTarget) {
        ReviewEndFocus.REVIEW_BUTTON -> document != null && hasReviewButton
        ReviewEndFocus.PAGES_ON_THE_PHONE -> document != null && pages.local.isNotEmpty()
        ReviewEndFocus.SCAN_BUTTON -> document != null
        null -> false
    }
    LaunchedEffect(focusTarget, isFocusTargetPlaced) {
        val target = focusTarget ?: return@LaunchedEffect
        if (!isFocusTargetPlaced) return@LaunchedEffect
        if (target == ReviewEndFocus.PAGES_ON_THE_PHONE) gridState.scrollToItem(PAGES_ON_THE_PHONE_INDEX)
        // Once the target is laid out, so that it can take the focus.
        withFrameNanos {}
        focusRequesters.of(target).requestFocus()
        focusTarget = null
    }
    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = { ScreenTitle(sanitizeTextFromPc(document?.title.orEmpty())) },
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
                        onClick = onImport,
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
                        onScan = onScan,
                        onChooseCamera = onChooseCamera,
                        modifier = Modifier.focusRequester(focusRequesters.scanButton),
                    )
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.refreshing,
            onRefresh = onRefresh,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            when {
                state.loading -> Unit

                document == null -> DocumentGone()

                else -> LazyVerticalGrid(
                    columns = GridCells.Adaptive(
                        minSize = min(TILE_MIN_WIDTH * LocalDensity.current.fontScale, TILE_MIN_WIDTH_CAP),
                    ),
                    contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 88.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    state = gridState,
                    modifier = Modifier.fillMaxSize(),
                ) {
                    fullWidthItem("summary") {
                        Column {
                            DocumentSummary(document)
                            val hasBanner = document.uploadError != null || scan.outcome != null ||
                                hasReviewButton || scan.wasAddingInterrupted
                            BannerSlot(Modifier.padding(top = if (hasBanner) 8.dp else 0.dp)) {
                                document.uploadError?.let { error ->
                                    ErrorBanner(
                                        stringResource(R.string.document_upload_refused, sanitizeTextFromPc(error)),
                                        R.drawable.ic_error,
                                        stringResource(R.string.retry),
                                        onRetryDocumentUpload,
                                    )
                                }
                                PagesToSendBanner(
                                    scan = scan,
                                    onReview = onReview,
                                    onDismissAddingInterrupted = onDismissAddingInterrupted,
                                    reviewButtonModifier = Modifier.focusRequester(focusRequesters.reviewButton),
                                )
                                scan.outcome?.let { outcome -> PreparationOutcomeBanner(outcome, onDismissOutcome) }
                            }
                        }
                    }
                    if (pages.local.isNotEmpty()) {
                        fullWidthItem("local") {
                            SectionHeader(
                                pluralStringResource(
                                    R.plurals.document_local_pages,
                                    pages.local.size,
                                    pages.local.size,
                                ),
                                modifier = Modifier
                                    .focusRequester(focusRequesters.pagesOnThePhone)
                                    .focusable(),
                            )
                        }
                        items(pages.local, key = { it.id }) { page ->
                            LocalPageTile(
                                page,
                                remember(page.fileName) { localImage(page) },
                                state.server,
                                onClick = { onOpenLocalPage(page.id) },
                            )
                        }
                    }
                    fullWidthItem("server") {
                        SectionHeader(
                            pluralStringResource(R.plurals.document_server_pages, pages.server.size, pages.server.size),
                        )
                    }
                    if (pages.isEmpty) {
                        fullWidthItem("empty") { NoPagesYet() }
                    }
                    items(pages.server, key = { it.id }) { page ->
                        ServerPageTile(page, state.server, onClick = { onOpenServerPage(page.id) })
                    }
                }
            }
        }
    }
}

/**
 * "Scan", split: the main part opens [camera] at once; the chevron, or a long press, offers the
 * cameras to choose from ([onChooseCamera]). Disabled until the default camera is known.
 */
@Composable
private fun ScanButton(
    camera: ScanSource,
    enabled: Boolean,
    onScan: () -> Unit,
    onChooseCamera: () -> Unit,
    modifier: Modifier = Modifier,
) {
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
                modifier = modifier
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

/**
 * The pages waiting on the phone, which the review shows: while they are being prepared, the count
 * of images only, so that the banner is read out once per copy rather than at each image.
 */
@Composable
private fun PagesToSendBanner(
    scan: ScanUiState,
    onReview: () -> Unit,
    onDismissAddingInterrupted: () -> Unit,
    reviewButtonModifier: Modifier,
) {
    val pageCount = scan.stagedPages.size
    val preparation = scan.preparation
    if (preparation == null && pageCount == 0) {
        if (scan.wasAddingInterrupted) {
            AttentionBanner(
                stringResource(R.string.document_adding_interrupted_no_pages),
                R.drawable.ic_outbox,
                stringResource(R.string.banner_dismiss),
                onDismissAddingInterrupted,
            )
        }
        return
    }
    val text = when {
        preparation != null ->
            pluralStringResource(R.plurals.document_preparing_pages, preparation.total, preparation.total)

        scan.wasAddingInterrupted ->
            pluralStringResource(R.plurals.document_pages_to_send_interrupted, pageCount, pageCount)

        else -> pluralStringResource(R.plurals.document_pages_to_send, pageCount, pageCount)
    }
    AttentionBanner(
        text,
        R.drawable.ic_outbox,
        stringResource(R.string.document_review),
        onReview,
        actionModifier = reviewButtonModifier,
    )
}

/** Where the focus goes once the review has ended: where the user goes on from. */
private enum class ReviewEndFocus { REVIEW_BUTTON, PAGES_ON_THE_PHONE, SCAN_BUTTON }

private class ReviewEndFocusRequesters {
    val reviewButton = FocusRequester()
    val pagesOnThePhone = FocusRequester()
    val scanButton = FocusRequester()

    fun of(target: ReviewEndFocus): FocusRequester = when (target) {
        ReviewEndFocus.REVIEW_BUTTON -> reviewButton
        ReviewEndFocus.PAGES_ON_THE_PHONE -> pagesOnThePhone
        ReviewEndFocus.SCAN_BUTTON -> scanButton
    }
}

private val ReviewEnd.focusTarget: ReviewEndFocus get() = when (this) {
    ReviewEnd.PagesKept -> ReviewEndFocus.REVIEW_BUTTON
    is ReviewEnd.PagesSent -> ReviewEndFocus.PAGES_ON_THE_PHONE
    is ReviewEnd.PagesDeleted, ReviewEnd.Emptied -> ReviewEndFocus.SCAN_BUTTON
}

private fun ReviewEnd.message(resources: Resources): String? = when (this) {
    ReviewEnd.PagesKept -> resources.getString(R.string.review_pages_kept)
    is ReviewEnd.PagesSent -> resources.getQuantityString(R.plurals.message_pages_queued, count, count)
    is ReviewEnd.PagesDeleted -> resources.getQuantityString(R.plurals.review_pages_deleted, count, count)
    ReviewEnd.Emptied -> null
}

// The summary, then the header of the pages on the phone.
private const val PAGES_ON_THE_PHONE_INDEX = 1

// A page's tile widens with the text, so that its badge is never cut, up to two columns on a phone.
private val TILE_MIN_WIDTH = 104.dp
private val TILE_MIN_WIDTH_CAP = 160.dp

/** Screen width, in dp of text at its normal size, from which "Import" shows its label. */
private const val ROOMY_WIDTH_DP = 380

private fun LazyGridScope.fullWidthItem(key: String, content: @Composable () -> Unit) {
    item(key = key, span = { GridItemSpan(maxLineSpan) }) { content() }
}

@Composable
private fun DocumentSummary(document: DocumentEntity, modifier: Modifier = Modifier) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.cardColor,
            contentColor = MaterialTheme.colorScheme.onSurface,
        ),
        modifier = modifier.fillMaxWidth(),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    painterResource(document.kind.iconRes()),
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                val kind = stringResource(document.kind.labelRes())
                val author = sanitizeTextFromPc(document.author)
                Text(
                    if (author.isEmpty()) kind else "$kind · $author",
                    style = MaterialTheme.typography.titleSmall,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
            val server = document.server
            if (server == null) {
                Text(
                    stringResource(R.string.document_not_on_pc_yet_long),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                val noCoverage = stringResource(R.string.document_coverage_none)
                val coverage = sanitizeTextFromPc(server.coverage).ifEmpty { noCoverage }
                Text(stringResource(R.string.document_coverage, coverage), color = MaterialTheme.colorScheme.onSurface)
                val missing = sanitizeTextFromPc(server.missing)
                if (missing.isNotEmpty()) {
                    Text(
                        stringResource(R.string.document_missing, missing),
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                }
                if (server.unnumbered > 0) {
                    Text(
                        pluralStringResource(R.plurals.document_unnumbered, server.unnumbered, server.unnumbered),
                        color = MaterialTheme.colorScheme.onSurface,
                    )
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
                val folder = sanitizeTextFromPc(server.folder)
                if (folder.isNotEmpty()) {
                    Text(
                        stringResource(R.string.document_folder, folder),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (document.unwarp) {
                Text(
                    stringResource(R.string.document_unwarp_on),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
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
    is DocumentMessage.ServerError -> resources.getString(R.string.message_server_error, sanitizeTextFromPc(detail))
    DocumentMessage.PageBusy -> resources.getString(R.string.message_page_busy)
}
