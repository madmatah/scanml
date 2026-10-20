package fr.scanmylib.ui.components

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.graphics.Color

enum class StatusTone {
    NEUTRAL,
    IN_PROGRESS,
    ATTENTION,
    FAILURE,
}

internal class StatusColors(val container: Color, val content: Color)

@Composable
@ReadOnlyComposable
internal fun pickStatusColors(tone: StatusTone): StatusColors {
    val scheme = MaterialTheme.colorScheme
    return when (tone) {
        StatusTone.NEUTRAL -> StatusColors(scheme.surfaceContainerHighest, scheme.onSurfaceVariant)
        StatusTone.IN_PROGRESS -> StatusColors(scheme.primaryContainer, scheme.onPrimaryContainer)
        StatusTone.ATTENTION -> StatusColors(scheme.tertiaryContainer, scheme.onTertiaryContainer)
        StatusTone.FAILURE -> StatusColors(scheme.errorContainer, scheme.onErrorContainer)
    }
}

@Composable
@ReadOnlyComposable
internal fun pickInLineColor(tone: StatusTone): Color = when (tone) {
    StatusTone.NEUTRAL -> MaterialTheme.colorScheme.onSurfaceVariant
    StatusTone.IN_PROGRESS -> MaterialTheme.colorScheme.primary
    StatusTone.ATTENTION -> MaterialTheme.colorScheme.tertiary
    StatusTone.FAILURE -> MaterialTheme.colorScheme.error
}
