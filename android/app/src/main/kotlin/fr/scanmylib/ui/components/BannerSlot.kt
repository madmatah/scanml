package fr.scanmylib.ui.components

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

/**
 * Android reads out the changes of a live region that is already there, not a region that appears
 * (https://developer.android.com/reference/android/view/View#setAccessibilityLiveRegion(int)), and a node of no size
 * may be left out of the accessibility tree: the slot keeps a width and a height while it is empty, so that a banner
 * that appears in it is read out.
 */
@Composable
fun BannerSlot(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(
        modifier
            .fillMaxWidth()
            .heightIn(min = 1.dp)
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        content()
    }
}
