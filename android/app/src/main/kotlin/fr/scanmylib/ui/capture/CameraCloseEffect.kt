package fr.scanmylib.ui.capture

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.LocalLifecycleOwner

/**
 * The nav host closes only a resumed screen, and a close it refuses stays set. The resumes are
 * counted as events, since a pause and a resume between two frames leave the lifecycle's state as it
 * was, and the state is read at the call, since the screen may pause between the launch of an
 * attempt and its run. The nav host checks the state again, as defense in depth: neither relies on the other.
 */
@Composable
internal fun CameraCloseEffect(
    closing: CameraClose?,
    onClose: (werePhotosKept: Boolean) -> Boolean,
    onCloseHandled: (CameraClose) -> Unit,
) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var resumeCount by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { resumeCount++ }
    val currentOnClose by rememberUpdatedState(onClose)
    val currentOnCloseHandled by rememberUpdatedState(onCloseHandled)
    LaunchedEffect(closing, resumeCount) {
        val isResumed = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        if (closing != null && isResumed && currentOnClose(closing.werePhotosKept)) currentOnCloseHandled(closing)
    }
}
