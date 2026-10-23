package fr.scanmylib.ui.components

import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.rememberTransformableState
import androidx.compose.foundation.gestures.transformable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.isUnspecified
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.toSize
import fr.scanmylib.R

@Stable
class ZoomState {
    var scale by mutableFloatStateOf(MIN_SCALE)
        private set

    /** The image's center, from the viewport's center, in pixels. */
    var offset by mutableStateOf(Offset.Zero)
        private set

    val isZoomedIn: Boolean get() = scale > MIN_SCALE

    internal var viewport = Size.Zero
    internal var imageSize = Size.Unspecified

    internal fun transform(zoomChange: Float, panChange: Offset) {
        scale = clampScale(scale * zoomChange)
        offset = clampOffset(offset + panChange, scale, viewport, imageSize)
    }

    internal fun zoomTo(newScale: Float) {
        scale = clampScale(newScale)
        offset = clampOffset(offset, scale, viewport, imageSize)
    }
}

/** At 1×, a one-finger swipe goes through, to the pager that holds the image. */
@Composable
fun ZoomableImage(painter: Painter, state: ZoomState, modifier: Modifier = Modifier) {
    state.imageSize = painter.intrinsicSize
    val transformableState = rememberTransformableState { zoomChange, panChange, _ ->
        state.transform(zoomChange, panChange)
    }
    val zoomInLabel = stringResource(R.string.zoom_in)
    val zoomOutLabel = stringResource(R.string.zoom_out)
    // Derived, so that a pinch recomposes the image only when an action comes or goes, not at each frame.
    val canZoomIn by remember(state) { derivedStateOf { state.scale < MAX_SCALE } }
    val canZoomOut by remember(state) { derivedStateOf { state.isZoomedIn } }
    Box(
        modifier = modifier
            .fillMaxSize()
            .clipToBounds()
            .onSizeChanged { state.viewport = it.toSize() }
            .semantics {
                customActions = listOfNotNull(
                    CustomAccessibilityAction(zoomInLabel) {
                        state.zoomTo(state.scale * ZOOM_STEP)
                        true
                    }.takeIf { canZoomIn },
                    CustomAccessibilityAction(zoomOutLabel) {
                        state.zoomTo(state.scale / ZOOM_STEP)
                        true
                    }.takeIf { canZoomOut },
                )
            }
            .pointerInput(state) {
                detectTapGestures(onDoubleTap = { state.zoomTo(pickScaleAfterDoubleTap(state.scale)) })
            }
            .transformable(transformableState, canPan = { state.isZoomedIn }),
    ) {
        Image(
            painter,
            contentDescription = null,
            contentScale = ContentScale.Fit,
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer {
                    scaleX = state.scale
                    scaleY = state.scale
                    translationX = state.offset.x
                    translationY = state.offset.y
                },
        )
    }
}

internal fun clampScale(scale: Float): Float = scale.coerceIn(MIN_SCALE, MAX_SCALE)

internal fun pickScaleAfterDoubleTap(scale: Float): Float = if (scale > MIN_SCALE) MIN_SCALE else DOUBLE_TAP_SCALE

internal fun clampOffset(offset: Offset, scale: Float, viewport: Size, imageSize: Size): Offset {
    val fitted = fitImageSize(imageSize, viewport)
    val maxX = ((fitted.width * scale - viewport.width) / 2).coerceAtLeast(0f)
    val maxY = ((fitted.height * scale - viewport.height) / 2).coerceAtLeast(0f)
    return Offset(offset.x.coerceWithin(maxX), offset.y.coerceWithin(maxY))
}

/** Within [-bound, bound], and exactly 0 when [bound] is: never -0, which an [Offset] tells from 0. */
private fun Float.coerceWithin(bound: Float): Float = if (bound > 0f) coerceIn(-bound, bound) else 0f

private fun fitImageSize(imageSize: Size, viewport: Size): Size {
    if (imageSize.isUnspecified || imageSize.width <= 0f || imageSize.height <= 0f) return viewport
    val ratio = minOf(viewport.width / imageSize.width, viewport.height / imageSize.height)
    return Size(imageSize.width * ratio, imageSize.height * ratio)
}

private const val MIN_SCALE = 1f
private const val MAX_SCALE = 2.5f
private const val DOUBLE_TAP_SCALE = 2f

private const val ZOOM_STEP = 1.5f
