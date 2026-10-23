@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.document

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
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
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.compose.currentStateAsState
import coil3.compose.AsyncImage
import fr.scanmylib.R
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.library.Preparation
import fr.scanmylib.library.StagedPage
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.AttentionBanner
import fr.scanmylib.ui.components.BannerSlot
import fr.scanmylib.ui.components.ScreenTitle
import fr.scanmylib.ui.components.SettingSwitchRow

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
    BackHandler(onBack = viewModel::closeReview)
    var choosingCamera by rememberSaveable { mutableStateOf(false) }
    // The page shown large, by file.
    var shownPage by rememberSaveable { mutableStateOf<String?>(null) }

    ReviewContent(
        scan = scan,
        snackbarHostState = snackbarHostState,
        onClose = viewModel::closeReview,
        onFirstPageChange = viewModel::onFirstPageChange,
        onConsecutiveChange = viewModel::onConsecutiveChange,
        onCancelPreparation = viewModel::cancelPreparation,
        onDismissOutcome = viewModel::dismissOutcome,
        onDismissAddingInterrupted = viewModel::dismissAddingInterrupted,
        onEnlargePage = { page -> if (!scan.sending) shownPage = page.file.path },
        onRemovePage = viewModel::removePage,
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
    val pageIndex = scan.stagedPages.indexOfFirst { it.file.path == shownPage }
    if (pageIndex >= 0) {
        val page = scan.stagedPages[pageIndex]
        StagedPageDialog(
            page = page,
            position = pageIndex + 1,
            count = scan.stagedPages.size,
            onRemove = {
                shownPage = null
                viewModel.removePage(page)
            },
            onDismiss = { shownPage = null },
        )
    }
}

/** Apart from the view model, so that a test draws the review from invented state. */
@Composable
internal fun ReviewContent(
    scan: ScanUiState,
    snackbarHostState: SnackbarHostState,
    onClose: () -> Unit,
    onFirstPageChange: (String) -> Unit,
    onConsecutiveChange: (Boolean) -> Unit,
    onCancelPreparation: () -> Unit,
    onDismissOutcome: () -> Unit,
    onDismissAddingInterrupted: () -> Unit,
    onEnlargePage: (StagedPage) -> Unit,
    onRemovePage: (StagedPage) -> Unit,
    onScan: () -> Unit,
    onImport: () -> Unit,
    onChooseCamera: () -> Unit,
    onSend: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier,
    pageImage: @Composable (page: StagedPage, modifier: Modifier) -> Unit = { page, imageModifier ->
        AsyncImage(page.file, contentDescription = null, contentScale = ContentScale.Fit, modifier = imageModifier)
    },
) {
    val count = scan.stagedPages.size
    val numbering = scan.numbering
    var isConfirmingDelete by rememberSaveable { mutableStateOf(false) }
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
            contentPadding = PaddingValues(start = 16.dp, top = 8.dp, end = 16.dp, bottom = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            fullWidthItem("numbering") { NumberingRow(scan, onFirstPageChange, onConsecutiveChange) }
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
            itemsIndexed(scan.stagedPages, key = { _, page -> page.file.path }) { index, page ->
                StagedPageTile(
                    position = index + 1,
                    count = count,
                    numberHint = numbering?.hintFor(index),
                    onEnlarge = { onEnlargePage(page) },
                    onRemove = { onRemovePage(page) }.takeUnless { scan.sending },
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

/** The first page number, and whether the following pages go on from it; side by side while they fit. */
@Composable
private fun NumberingRow(
    scan: ScanUiState,
    onFirstPageChange: (String) -> Unit,
    onConsecutiveChange: (Boolean) -> Unit,
) {
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val fitsSideBySide = maxWidth / LocalDensity.current.fontScale >= SIDE_BY_SIDE_MIN_WIDTH
        val field = @Composable { fieldModifier: Modifier -> FirstPageField(scan, onFirstPageChange, fieldModifier) }
        val switch = @Composable { switchModifier: Modifier ->
            SettingSwitchRow(
                label = stringResource(R.string.scan_consecutive),
                checked = scan.consecutive,
                onCheckedChange = onConsecutiveChange,
                enabled = scan.firstPage.isNotEmpty(),
                // The grid has margins of its own.
                contentPadding = PaddingValues(),
                modifier = switchModifier,
            )
        }
        if (fitsSideBySide) {
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                field(Modifier.weight(1f))
                switch(Modifier.weight(1f).padding(top = 4.dp))
            }
        } else {
            Column {
                field(Modifier.fillMaxWidth())
                switch(Modifier)
            }
        }
    }
}

@Composable
private fun FirstPageField(scan: ScanUiState, onFirstPageChange: (String) -> Unit, modifier: Modifier = Modifier) {
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
        modifier = modifier,
    )
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
                    describeNumbering(scan.numbering, count),
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

/** What the server will receive as page-number hints, in words. */
@Composable
private fun describeNumbering(numbering: PageNumbering?, count: Int): String {
    val first = numbering?.firstPage
    val last = numbering?.lastHint(count) ?: first
    return when {
        numbering == null -> stringResource(R.string.scan_summary_invalid)
        first == null -> stringResource(R.string.scan_summary_none)
        last == null || last == first -> stringResource(R.string.scan_summary_first_only, first)
        else -> stringResource(R.string.scan_summary_range, first, last)
    }
}

private fun LazyGridScope.fullWidthItem(key: String, content: @Composable () -> Unit) {
    item(key = key, span = { GridItemSpan(maxLineSpan) }) { content() }
}

// Two columns on a phone, at every text size.
private val TILE_MIN_WIDTH = 160.dp

/** Width, in dp of text at its normal size, from which the numbering fields fit side by side. */
private val SIDE_BY_SIDE_MIN_WIDTH = 340.dp
