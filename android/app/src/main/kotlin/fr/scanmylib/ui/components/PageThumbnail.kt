package fr.scanmylib.ui.components

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.library.PageLabel
import fr.scanmylib.ui.theme.PageChipContainer
import fr.scanmylib.ui.theme.PageChipContent

data class PageBadge(@StringRes val text: Int, @DrawableRes val icon: Int, val tone: StatusTone)

@Composable
fun PageThumbnail(
    label: PageLabel,
    status: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    badge: PageBadge? = null,
    isSetAside: Boolean = false,
    image: @Composable (Modifier) -> Unit,
) {
    val chip = when (label) {
        PageLabel.Unnumbered -> stringResource(R.string.page_without_number)
        is PageLabel.OnePage -> stringResource(R.string.page_label, label.page)
        is PageLabel.Spread -> stringResource(R.string.page_label_spread, label.firstPage, label.lastPage)
    }
    val description = when (label) {
        PageLabel.Unnumbered -> stringResource(R.string.page_description_unnumbered, status)
        is PageLabel.OnePage -> stringResource(R.string.page_description, label.page, status)
        is PageLabel.Spread -> stringResource(R.string.page_description_spread, label.firstPage, label.lastPage, status)
    }
    val openLabel = stringResource(R.string.page_open)
    Box(
        modifier = modifier
            .aspectRatio(PAGE_ASPECT_RATIO)
            .clip(MaterialTheme.shapes.extraSmall)
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, MaterialTheme.shapes.extraSmall)
            // In place of the words drawn over the image, and of the tap's own, which it clears too.
            .clearAndSetSemantics {
                contentDescription = description
                role = Role.Button
                onClick(label = openLabel) {
                    onClick()
                    true
                }
            }
            .clickable(onClick = onClick),
    ) {
        Box(
            Modifier
                .matchParentSize()
                .background(MaterialTheme.colorScheme.surfaceContainerLowest)
                .graphicsLayer {
                    alpha = if (isSetAside) SET_ASIDE_ALPHA else 1f
                    // The image alone takes the alpha, over its fill: it needs no offscreen buffer.
                    compositingStrategy = CompositingStrategy.ModulateAlpha
                },
        ) {
            image(Modifier.matchParentSize())
        }
        if (badge != null) {
            StatusBadge(
                stringResource(badge.text),
                badge.icon,
                badge.tone,
                placement = StatusBadgePlacement.OVER_IMAGE,
                fullText = status,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(6.dp),
            )
        }
        Text(
            chip,
            style = MaterialTheme.typography.labelMedium,
            color = PageChipContent,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(8.dp)
                .background(PageChipContainer, PAGE_CHIP_SHAPE)
                .padding(horizontal = 6.dp, vertical = 2.dp),
        )
    }
}

// A4's sides, 1:√2: most pages are close to it.
private const val PAGE_ASPECT_RATIO = 1f / 1.414f

private const val SET_ASIDE_ALPHA = 0.5f

private val PAGE_CHIP_SHAPE = RoundedCornerShape(6.dp)
