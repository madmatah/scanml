package fr.scanmylib.ui.components

import androidx.annotation.DrawableRes
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Over a page's image, a badge needs a fill of its own to stand out from the paper. */
enum class StatusBadgePlacement {
    OVER_IMAGE,
    IN_LINE,
}

@Composable
fun StatusBadge(
    text: String,
    @DrawableRes icon: Int,
    tone: StatusTone,
    modifier: Modifier = Modifier,
    placement: StatusBadgePlacement = StatusBadgePlacement.IN_LINE,
    fullText: String = text,
) {
    val colors = when (placement) {
        StatusBadgePlacement.OVER_IMAGE -> pickStatusColors(tone)
        StatusBadgePlacement.IN_LINE -> StatusColors(Color.Transparent, pickInLineColor(tone))
    }
    val iconSize = with(LocalDensity.current) { ICON_SIZE.toDp() }
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier
            .clearAndSetSemantics { contentDescription = fullText }
            .heightIn(min = 24.dp)
            .background(colors.container, MaterialTheme.shapes.small)
            .padding(placement.padding),
    ) {
        Icon(
            painterResource(icon),
            contentDescription = null,
            tint = colors.content,
            modifier = Modifier.size(iconSize),
        )
        Text(
            text,
            style = when (placement) {
                StatusBadgePlacement.OVER_IMAGE -> MaterialTheme.typography.labelMedium
                StatusBadgePlacement.IN_LINE -> MaterialTheme.typography.labelLarge
            },
            color = colors.content,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

// In sp, so that the icon grows with the text it goes with.
private val ICON_SIZE = 16.sp

private val StatusBadgePlacement.padding: PaddingValues
    get() = when (this) {
        StatusBadgePlacement.OVER_IMAGE -> PaddingValues(horizontal = 6.dp, vertical = 2.dp)
        StatusBadgePlacement.IN_LINE -> PaddingValues(vertical = 2.dp)
    }
