@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.document

import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.painter.ColorPainter
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.IntSize
import coil3.compose.AsyncImagePainter
import coil3.compose.LocalPlatformContext
import coil3.compose.rememberAsyncImagePainter
import coil3.request.CachePolicy
import coil3.request.ImageRequest
import coil3.size.Scale
import fr.scanmylib.R
import fr.scanmylib.library.StagedPage
import fr.scanmylib.ui.components.BackButton
import fr.scanmylib.ui.components.ScreenTitle
import fr.scanmylib.ui.components.ZoomState
import fr.scanmylib.ui.components.ZoomableImage

/** Takes the review's [snackbarHostState], so that the removal's "Undo" shows over the page too. */
@Composable
internal fun StagedPagePager(
    pages: List<StagedPage>,
    firstShownPage: Int,
    canRemove: Boolean,
    snackbarHostState: SnackbarHostState,
    onPageShown: (StagedPage) -> Unit,
    onRemove: (StagedPage) -> Unit,
    onBack: () -> Unit,
    pagePainter: @Composable (page: StagedPage, viewport: IntSize, isZoomedIn: Boolean) -> Painter,
    modifier: Modifier = Modifier,
) {
    val pagerState = rememberPagerState(initialPage = firstShownPage) { pages.size }
    // By key, for the pages composed: the page shown swipes only while it is not zoomed in.
    val zoomStates = remember { mutableStateMapOf<String, ZoomState>() }
    val shownPage = pages.getOrNull(pagerState.currentPage)
    val currentPages by rememberUpdatedState(pages)
    // Derived, so that a pinch recomposes the pager only when the page shown starts or stops being zoomed in.
    val isShownPageZoomedIn by remember {
        derivedStateOf { zoomStates[currentPages.getOrNull(pagerState.currentPage)?.key]?.isZoomedIn == true }
    }
    val currentOnPageShown by rememberUpdatedState(onPageShown)
    LaunchedEffect(shownPage) {
        shownPage?.let(currentOnPageShown)
    }
    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = {
                    ScreenTitle(stringResource(R.string.scan_review_page, pagerState.currentPage + 1, pages.size))
                },
                navigationIcon = { BackButton(onBack) },
                actions = {
                    TextButton(
                        onClick = { shownPage?.let(onRemove) },
                        enabled = canRemove && shownPage != null,
                        colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    ) {
                        Text(stringResource(R.string.review_remove))
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        HorizontalPager(
            state = pagerState,
            key = { pages[it].key },
            userScrollEnabled = !isShownPageZoomedIn,
            beyondViewportPageCount = 0,
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) { index ->
            val page = pages[index]
            val zoomState = remember { ZoomState() }
            val isZoomedIn by remember(zoomState) { derivedStateOf { zoomState.isZoomedIn } }
            DisposableEffect(page.key) {
                zoomStates[page.key] = zoomState
                onDispose { zoomStates.remove(page.key) }
            }
            BoxWithConstraints(Modifier.fillMaxSize()) {
                val viewport = IntSize(constraints.maxWidth, constraints.maxHeight)
                ZoomableImage(pagePainter(page, viewport, isZoomedIn), zoomState)
            }
        }
    }
}

/**
 * At 1×, a page is decoded at the viewport's size through the memory cache, where its larger image
 * replaces the grid's thumbnail. Zoomed in, it is decoded at twice the viewport, sharp at 2× and
 * bounded for a photo of 120 megapixels, out of the memory cache, which it would fill, over its 1×
 * image meanwhile.
 */
@Composable
internal fun rememberPagePainter(page: StagedPage, viewport: IntSize, isZoomedIn: Boolean): Painter {
    val context = LocalPlatformContext.current
    val fitSize = pickDecodeSize(viewport, isZoomedIn = false) ?: return remember { ColorPainter(Color.Transparent) }
    val fitRequest = remember(context, page.file, fitSize) {
        ImageRequest.Builder(context)
            .data(page.file)
            .size(fitSize.width, fitSize.height)
            .scale(Scale.FIT)
            .build()
    }
    val fitPainter = rememberAsyncImagePainter(fitRequest)
    val zoomSize = pickDecodeSize(viewport, isZoomedIn) ?: fitSize
    if (zoomSize == fitSize) return fitPainter
    val fitState by fitPainter.state.collectAsState()
    // Coil's own key, which holds what it needs (the file's path and modification time): never built by hand.
    val fitImageKey = (fitState as? AsyncImagePainter.State.Success)?.result?.memoryCacheKey
    val zoomRequest = remember(context, page.file, zoomSize, fitImageKey) {
        ImageRequest.Builder(context)
            .data(page.file)
            .size(zoomSize.width, zoomSize.height)
            .scale(Scale.FIT)
            .memoryCachePolicy(CachePolicy.DISABLED)
            .placeholderMemoryCacheKey(fitImageKey)
            .build()
    }
    return rememberAsyncImagePainter(zoomRequest)
}

/** None for an empty viewport, as in a window too small to hold one: Coil refuses a size of 0. */
internal fun pickDecodeSize(viewport: IntSize, isZoomedIn: Boolean): IntSize? = when {
    viewport.width <= 0 || viewport.height <= 0 -> null
    isZoomedIn -> IntSize(viewport.width * 2, viewport.height * 2)
    else -> viewport
}
