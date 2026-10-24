@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.document

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyGridScope
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.LocalContentColor
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.compose.currentStateAsState
import coil3.PlatformContext
import coil3.compose.AsyncImage
import coil3.compose.LocalPlatformContext
import coil3.memory.MemoryCache
import coil3.request.ImageRequest
import fr.scanmylib.R
import fr.scanmylib.library.Preparation
import fr.scanmylib.library.StagedPage
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.AttentionBanner
import fr.scanmylib.ui.components.BannerSlot
import fr.scanmylib.ui.components.ScreenTitle
import java.io.File

/** Shares the document's [viewModel], so that the review and the document show one state of the run. */
@Composable
fun ReviewScreen(
    onClose: () -> Unit,
    onOpenCamera: () -> Unit,
    switchToSource: ScanSource?,
    onSwitchHandled: () -> Unit,
    viewModel: ScanViewModel,
) {
    val snackbarHostState = remember { SnackbarHostState() }
    val sources = rememberScanSources(
        viewModel = viewModel,
        snackbarHostState = snackbarHostState,
        onOpenCamera = onOpenCamera,
        onPagesReturned = {},
        switchToSource = switchToSource,
        onSwitchHandled = onSwitchHandled,
    )
    val scan by viewModel.scanState.collectAsStateWithLifecycle()
    // From state, and only while resumed: leaving while Google's scanner or the photo picker is in
    // front would unregister the launcher that receives its pages, and lose them.
    val lifecycleState by LocalLifecycleOwner.current.lifecycle.currentStateAsState()
    val isResumed = lifecycleState.isAtLeast(Lifecycle.State.RESUMED)
    val currentOnClose by rememberUpdatedState(onClose)
    val hasEnded = scan.reviewEnd != null
    LaunchedEffect(isResumed, hasEnded) {
        if (isResumed && hasEnded) currentOnClose()
    }
    LaunchedEffect(isResumed, scan.hasNothingToReview) {
        if (isResumed && scan.hasNothingToReview) viewModel.closeReview()
    }
    // Every source returns before the screen resumes, the camera's screen included.
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { viewModel.onSourceClosed() }
    BackHandler(onBack = viewModel::closeReview)
    var choosingCamera by rememberSaveable { mutableStateOf(false) }

    ReviewContent(
        scan = scan,
        snackbarHostState = snackbarHostState,
        onClose = viewModel::closeReview,
        onNumberPage = viewModel::numberPage,
        onCancelPreparation = viewModel::cancelPreparation,
        onDismissOutcome = viewModel::dismissOutcome,
        onDismissAddingInterrupted = viewModel::dismissAddingInterrupted,
        onRemovePage = viewModel::removePage,
        onRestorePage = viewModel::restorePage,
        onDeleteRemovedPage = viewModel::deleteRemovedPage,
        onScan = { sources.open(scan.camera) },
        onImport = sources.importPhotos,
        onChooseCamera = { choosingCamera = true },
        onSend = viewModel::send,
        onDelete = viewModel::discard,
    )

    if (choosingCamera) {
        CameraSheet(
            scan = scan,
            onChoose = { camera, makeDefault ->
                choosingCamera = false
                if (makeDefault) viewModel.makeDefaultCamera(camera)
                sources.open(camera)
            },
            onDismiss = { choosingCamera = false },
        )
    }
}

/** Apart from the view model, so that a test draws the review from invented state. */
@Composable
internal fun ReviewContent(
    scan: ScanUiState,
    snackbarHostState: SnackbarHostState,
    onClose: () -> Unit,
    onNumberPage: (page: StagedPage, number: Int?, nextPagesFollowOn: Boolean) -> Unit,
    onCancelPreparation: () -> Unit,
    onDismissOutcome: () -> Unit,
    onDismissAddingInterrupted: () -> Unit,
    onRemovePage: (StagedPage) -> Unit,
    onRestorePage: (StagedPage) -> Unit,
    onDeleteRemovedPage: (StagedPage) -> Unit,
    onScan: () -> Unit,
    onImport: () -> Unit,
    onChooseCamera: () -> Unit,
    onSend: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
    pageImage: @Composable (page: StagedPage, modifier: Modifier) -> Unit = { page, imageModifier ->
        PageImage(page, imageModifier)
    },
    pagePainter: @Composable (page: StagedPage, viewport: IntSize, isZoomedIn: Boolean) -> Painter =
        { page, viewport, isZoomedIn -> rememberPagePainter(page, viewport, isZoomedIn) },
) {
    val count = scan.stagedPages.size
    var isConfirmingDelete by rememberSaveable { mutableStateOf(false) }
    RemovalUndo(scan.removedPage, snackbarHostState, onRestorePage, onDeleteRemovedPage)
    val gridState = rememberLazyGridState()
    // The tile that takes the focus once a page is removed, or once the pager closes, by key.
    var pageToFocus by remember { mutableStateOf<String?>(null) }
    var shownPage by rememberSaveable { mutableStateOf<String?>(null) }
    val shownIndex = scan.stagedPages.indexOfFirst { it.key == shownPage }
    var numberingPage by rememberSaveable { mutableStateOf<String?>(null) }
    val numberingIndex = scan.stagedPages.indexOfFirst { it.key == numberingPage }
    LaunchedEffect(numberingIndex, scan.isRunRead) {
        if (numberingIndex < 0 && scan.isRunRead) numberingPage = null
    }
    LaunchedEffect(pageToFocus) {
        val target = pageToFocus ?: return@LaunchedEffect
        val index = scan.stagedPages.indexOfFirst { it.key == target }
        if (index < 0) return@LaunchedEffect
        // Once the grid is laid out: a tile out of sight is brought into it, where it can take the focus.
        withFrameNanos {}
        if (gridState.layoutInfo.visibleItemsInfo.none { it.key == target }) {
            gridState.scrollToItem(findFirstTileIndex(scan) + index)
        }
    }
    if (shownIndex >= 0) {
        val closePager = {
            pageToFocus = shownPage
            shownPage = null
        }
        BackHandler(onBack = closePager)
        StagedPagePager(
            pages = scan.stagedPages,
            firstShownPage = shownIndex,
            canRemove = !scan.sending,
            snackbarHostState = snackbarHostState,
            onPageShown = { page -> shownPage = page.key },
            onRemove = { page ->
                val index = scan.stagedPages.indexOfFirst { it.key == page.key }
                shownPage = (scan.stagedPages.getOrNull(index + 1) ?: scan.stagedPages.getOrNull(index - 1))?.key
                onRemovePage(page)
            },
            onBack = closePager,
            modifier = modifier,
            pagePainter = pagePainter,
        )
        return
    }
    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = {
                    ScreenTitle(pluralStringResource(R.plurals.scan_review_title, scan.pageCount, scan.pageCount))
                },
                navigationIcon = {
                    IconButton(onClick = onClose, enabled = !scan.sending) {
                        Icon(
                            painterResource(R.drawable.ic_close),
                            contentDescription = stringResource(R.string.review_close),
                        )
                    }
                },
            )
        },
        bottomBar = { SendBar(scan, onSend) },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        LazyVerticalGrid(
            columns = GridCells.Adaptive(minSize = TILE_MIN_WIDTH),
            state = gridState,
            contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            scan.preparation?.let { preparation ->
                fullWidthItem("preparation") { PreparationProgress(preparation, onCancelPreparation) }
            }
            fullWidthItem("banners") {
                BannerSlot {
                    scan.outcome?.let { outcome -> PreparationOutcomeBanner(outcome, onDismissOutcome) }
                    if (scan.wasAddingInterrupted && count > 0) {
                        AttentionBanner(
                            stringResource(R.string.message_adding_interrupted),
                            R.drawable.ic_outbox,
                            stringResource(R.string.banner_dismiss),
                            onDismissAddingInterrupted,
                        )
                    }
                }
            }
            val hints = scan.hints
            itemsIndexed(scan.stagedPages, key = { _, page -> page.key }) { index, page ->
                val focusRequester = remember { FocusRequester() }
                if (page.key == pageToFocus) {
                    LaunchedEffect(Unit) {
                        // Once the tile is laid out, so that it can take the focus.
                        withFrameNanos {}
                        focusRequester.requestFocus()
                        pageToFocus = null
                    }
                }
                StagedPageTile(
                    position = index + 1,
                    count = count,
                    hint = hints[index],
                    onEnlarge = { if (!scan.sending) shownPage = page.key },
                    onNumber = { numberingPage = page.key }.takeUnless { scan.sending },
                    onRemove = {
                        val nextPage = scan.stagedPages.getOrNull(index + 1) ?: scan.stagedPages.getOrNull(index - 1)
                        pageToFocus = nextPage?.key
                        onRemovePage(page)
                    }.takeUnless { scan.sending },
                    modifier = Modifier.focusRequester(focusRequester),
                    image = { imageModifier -> pageImage(page, imageModifier) },
                )
            }
            items(scan.preparation?.imagesToAdd ?: 0, key = { "preparing-$it" }) { PreparingPageTile() }
            item(key = "add") {
                AddPagesTile(
                    camera = scan.camera,
                    enabled = !scan.sending,
                    onScan = onScan,
                    onImport = onImport,
                    onChooseCamera = onChooseCamera,
                )
            }
            fullWidthItem("delete") {
                TextButton(
                    onClick = { isConfirmingDelete = true },
                    enabled = count > 0 && !scan.preparing && !scan.sending,
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    modifier = Modifier.padding(top = 12.dp),
                ) {
                    Text(stringResource(R.string.scan_review_discard))
                }
            }
        }
    }
    if (numberingIndex >= 0) {
        // A second tap on Done, or Back, can come while the sheet slides away.
        val closeSheet = closeSheet@{
            pageToFocus = numberingPage ?: return@closeSheet
            numberingPage = null
        }
        PageNumberSheet(
            numberings = scan.stagedPages.map { it.numbering },
            index = numberingIndex,
            onDone = { number, nextPagesFollowOn ->
                if (numberingPage != null) onNumberPage(scan.stagedPages[numberingIndex], number, nextPagesFollowOn)
                closeSheet()
            },
            onDismiss = closeSheet,
        )
    }
    if (isConfirmingDelete) {
        DiscardRunDialog(
            count = count,
            onConfirm = {
                isConfirmingDelete = false
                onDelete()
            },
            onDismiss = { isConfirmingDelete = false },
        )
    }
}

/**
 * "Page removed · Undo", for as long as [removedPage]'s removal can be undone: undone with the
 * action, final once the snackbar ends. A removal that a newer one replaces ends without either:
 * the view model has made it final.
 */
@Composable
private fun RemovalUndo(
    removedPage: StagedPage?,
    snackbarHostState: SnackbarHostState,
    onRestorePage: (StagedPage) -> Unit,
    onDeleteRemovedPage: (StagedPage) -> Unit,
) {
    val resources = LocalResources.current
    val currentOnRestorePage by rememberUpdatedState(onRestorePage)
    val currentOnDeleteRemovedPage by rememberUpdatedState(onDeleteRemovedPage)
    LaunchedEffect(removedPage) {
        val page = removedPage ?: return@LaunchedEffect
        // In place of a message showing: the undo is offered for its own time, not after it.
        snackbarHostState.currentSnackbarData?.dismiss()
        val ending = snackbarHostState.showSnackbar(
            resources.getString(R.string.review_page_removed),
            actionLabel = resources.getString(R.string.undo),
            duration = SnackbarDuration.Long,
        )
        when (ending) {
            SnackbarResult.ActionPerformed -> currentOnRestorePage(page)
            SnackbarResult.Dismissed -> currentOnDeleteRemovedPage(page)
        }
    }
}

/** Only an import can be canceled: Google's scanner's pages exist nowhere else. */
@Composable
private fun PreparationProgress(preparation: Preparation, onCancel: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        LinearProgressIndicator(
            progress = { preparation.done.toFloat() / preparation.total.coerceAtLeast(1) },
            modifier = Modifier.fillMaxWidth(),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.review_preparing, preparation.done, preparation.total),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
            )
            if (preparation.isCancellable) {
                TextButton(onClick = onCancel) { Text(stringResource(R.string.cancel)) }
            }
        }
    }
}

@Composable
private fun SendBar(scan: ScanUiState, onSend: () -> Unit) {
    val count = scan.stagedPages.size
    Surface(color = MaterialTheme.colorScheme.surfaceContainer) {
        Column {
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier
                    .navigationBarsPadding()
                    .padding(16.dp),
            ) {
                Text(
                    stringResource(R.string.scan_summary_none),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Button(
                    onClick = onSend,
                    enabled = scan.canSend,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 56.dp),
                ) {
                    when {
                        scan.sending -> {
                            CircularProgressIndicator(
                                color = LocalContentColor.current,
                                strokeWidth = 2.dp,
                                modifier = Modifier.size(20.dp),
                            )
                            Spacer(Modifier.width(12.dp))
                            Text(stringResource(R.string.review_sending))
                        }

                        scan.preparing -> Text(stringResource(R.string.review_preparing_button))

                        else -> Text(pluralStringResource(R.plurals.scan_review_confirm, count, count))
                    }
                }
            }
        }
    }
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

@Composable
private fun PageImage(page: StagedPage, modifier: Modifier = Modifier) {
    val context = LocalPlatformContext.current
    val shownImage = remember { ShownImage() }
    val request = remember(context, page.file) { buildPageImageRequest(context, page.file, shownImage.memoryCacheKey) }
    AsyncImage(
        request,
        contentDescription = null,
        contentScale = ContentScale.Fit,
        onSuccess = { success -> shownImage.memoryCacheKey = success.result.memoryCacheKey },
        modifier = modifier,
    )
}

/** Not a state, so that each image that Coil shows recomposes nothing. */
private class ShownImage {
    var memoryCacheKey: MemoryCache.Key? = null
}

/** A new number renames the file, which Coil caches apart: the image it showed stands in until the new file is read. */
internal fun buildPageImageRequest(
    context: PlatformContext,
    file: File,
    shownImageKey: MemoryCache.Key?,
): ImageRequest = ImageRequest.Builder(context).data(file).placeholderMemoryCacheKey(shownImageKey).build()

/** Where the first tile is in [ReviewContent]'s grid: after the progress of a copy, and the banners. */
private fun findFirstTileIndex(scan: ScanUiState): Int = if (scan.preparation == null) 1 else 2

private fun LazyGridScope.fullWidthItem(key: String, content: @Composable () -> Unit) {
    item(key = key, span = { GridItemSpan(maxLineSpan) }) { content() }
}

// Two columns on a phone, at every text size.
private val TILE_MIN_WIDTH = 160.dp
