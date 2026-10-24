package fr.scanmylib.ui.document

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.focused
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fr.scanmylib.R
import fr.scanmylib.library.PageHint
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.PAGE_ASPECT_RATIO
import fr.scanmylib.ui.components.PageFrame
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.theme.PageChipContainer
import fr.scanmylib.ui.theme.PageChipContent

/**
 * One node for TalkBack and Switch Access, whose actions stand for the number chip and the page's
 * menu, none while [onNumber] or [onRemove] is null; the chip and the menu stay targets of their
 * own for a pointer.
 */
@Composable
fun StagedPageTile(
    position: Int,
    count: Int,
    hint: PageHint,
    onEnlarge: () -> Unit,
    onNumber: (() -> Unit)?,
    onRemove: (() -> Unit)?,
    modifier: Modifier = Modifier,
    image: @Composable (Modifier) -> Unit,
) {
    val description = when (hint) {
        PageHint.Auto -> stringResource(R.string.review_page_description_auto, position, count)

        is PageHint.Given -> stringResource(R.string.review_page_description, position, count, hint.number)

        is PageHint.FollowingOn ->
            stringResource(R.string.review_page_description_following_on, position, count, hint.number)
    }
    val enlargeLabel = stringResource(R.string.review_enlarge)
    val changeNumberLabel = stringResource(R.string.review_change_number)
    val removeLabel = stringResource(R.string.review_remove)
    var isFocused by remember { mutableStateOf(false) }
    Column(
        modifier = modifier
            .onFocusChanged { isFocused = it.isFocused }
            // In place of the words drawn over the image and under it.
            .clearAndSetSemantics {
                contentDescription = description
                role = Role.Button
                // Which the clearing hides, from the click below.
                focused = isFocused
                onClick(label = enlargeLabel) {
                    onEnlarge()
                    true
                }
                customActions = listOfNotNull(
                    onNumber?.let { changeNumber ->
                        CustomAccessibilityAction(changeNumberLabel) {
                            changeNumber()
                            true
                        }
                    },
                    onRemove?.let { remove ->
                        CustomAccessibilityAction(removeLabel) {
                            remove()
                            true
                        }
                    },
                )
            }
            .clickable(onClick = onEnlarge),
    ) {
        PageFrame(Modifier.fillMaxWidth()) {
            Box(
                Modifier
                    .matchParentSize()
                    .background(MaterialTheme.colorScheme.surfaceContainerLowest),
            ) {
                image(Modifier.matchParentSize())
            }
            Text(
                position.toString(),
                style = MaterialTheme.typography.labelMedium,
                color = PageChipContent,
                textAlign = TextAlign.Center,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(8.dp)
                    .background(PageChipContainer, ORDER_BADGE_SHAPE)
                    .padding(horizontal = 6.dp, vertical = 4.dp)
                    .defaultMinSize(minWidth = 12.dp),
            )
        }
        NumberStrip(hint, onEnlarge, onNumber, onRemove)
    }
}

/** The number the page is sent with, under the image, where the paper's colors cannot hide it, then its menu. */
@Composable
private fun NumberStrip(hint: PageHint, onEnlarge: () -> Unit, onNumber: (() -> Unit)?, onRemove: (() -> Unit)?) {
    Row(
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = STRIP_MIN_HEIGHT),
    ) {
        Box(Modifier.weight(1f, fill = false)) { NumberChip(hint, onNumber) }
        PageMenu(onEnlarge, onNumber, onRemove)
    }
}

/** Without a description: the tile's one node reads the same actions out, as custom actions. */
@Composable
private fun PageMenu(onEnlarge: () -> Unit, onNumber: (() -> Unit)?, onRemove: (() -> Unit)?) {
    var isExpanded by remember { mutableStateOf(false) }
    Box {
        IconButton(onClick = { isExpanded = true }, enabled = onNumber != null || onRemove != null) {
            Icon(painterResource(R.drawable.ic_more_vert), contentDescription = null)
        }
        DropdownMenu(expanded = isExpanded, onDismissRequest = { isExpanded = false }) {
            DropdownMenuItem(
                text = { Text(stringResource(R.string.review_enlarge)) },
                onClick = {
                    isExpanded = false
                    onEnlarge()
                },
            )
            DropdownMenuItem(
                text = { Text(stringResource(R.string.review_number_menu)) },
                onClick = {
                    isExpanded = false
                    onNumber?.invoke()
                },
                enabled = onNumber != null,
            )
            DropdownMenuItem(
                text = { Text(stringResource(R.string.review_remove)) },
                onClick = {
                    isExpanded = false
                    onRemove?.invoke()
                },
                enabled = onRemove != null,
                colors = MenuDefaults.itemColors(textColor = MaterialTheme.colorScheme.error),
            )
        }
    }
}

/** Never told by its color alone: a number, the word "Auto", or the link icon of a number that follows on. */
@Composable
private fun NumberChip(hint: PageHint, onNumber: (() -> Unit)?) {
    val colors = MaterialTheme.colorScheme
    val (container, content) = when (hint) {
        PageHint.Auto -> Color.Transparent to colors.onSurfaceVariant
        is PageHint.Given -> colors.primary to colors.onPrimary
        is PageHint.FollowingOn -> colors.secondaryContainer to colors.onSecondaryContainer
    }
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .heightIn(min = STRIP_MIN_HEIGHT)
            .then(if (onNumber == null) Modifier else Modifier.clickable(onClick = onNumber)),
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .heightIn(min = NUMBER_CHIP_MIN_HEIGHT)
                .background(container, NUMBER_SHAPE)
                .then(
                    if (hint == PageHint.Auto) Modifier.border(1.dp, colors.outline, NUMBER_SHAPE) else Modifier,
                )
                .padding(horizontal = 12.dp, vertical = 6.dp),
        ) {
            if (hint is PageHint.FollowingOn) {
                Icon(
                    painterResource(R.drawable.ic_link),
                    contentDescription = null,
                    tint = content,
                    modifier = Modifier.size(with(LocalDensity.current) { LINK_ICON_SIZE.toDp() }),
                )
            }
            Text(
                when (val number = hint.number) {
                    null -> stringResource(R.string.review_number_auto)
                    else -> stringResource(R.string.page_label, number.toString())
                },
                style = MaterialTheme.typography.labelLarge.copy(fontFeatureSettings = TABULAR_FIGURES),
                color = content,
            )
        }
    }
}

/** Hidden from TalkBack: the progress above the grid says it. */
@Composable
fun PreparingPageTile(modifier: Modifier = Modifier) {
    Column(modifier.clearAndSetSemantics {}) {
        PageFrame(Modifier.fillMaxWidth()) {
            Box(
                Modifier
                    .matchParentSize()
                    .background(MaterialTheme.colorScheme.surfaceContainerHighest),
            )
        }
        Spacer(Modifier.heightIn(min = STRIP_MIN_HEIGHT))
    }
}

/** [onScan] opens [camera]; [onChooseCamera], the choice of another one. */
@Composable
fun AddPagesTile(
    camera: ScanSource,
    enabled: Boolean,
    onScan: () -> Unit,
    onImport: () -> Unit,
    onChooseCamera: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val outline = MaterialTheme.colorScheme.outline
    BoxWithConstraints(modifier.fillMaxWidth()) {
        Column(
            verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = maxWidth / PAGE_ASPECT_RATIO + STRIP_MIN_HEIGHT)
                .drawBehind {
                    val strokeWidth = DASHED_OUTLINE_WIDTH.toPx()
                    val dash = DASH_LENGTH.toPx()
                    drawRoundRect(
                        color = outline,
                        cornerRadius = CornerRadius(TILE_CORNER_RADIUS.toPx()),
                        style = Stroke(
                            width = strokeWidth,
                            pathEffect = PathEffect.dashPathEffect(floatArrayOf(dash, dash)),
                        ),
                    )
                }
                .padding(12.dp),
        ) {
            Text(
                stringResource(R.string.scan_review_add),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurface,
            )
            FilledTonalButton(onClick = onScan, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
                Icon(painterResource(camera.iconRes()), contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.document_scan))
            }
            OutlinedButton(onClick = onImport, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
                Icon(
                    painterResource(R.drawable.ic_photo_library),
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.scan_source_picker))
            }
            TextButton(onClick = onChooseCamera, enabled = enabled, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.camera_sheet_title))
            }
        }
    }
}

private val STRIP_MIN_HEIGHT = 48.dp
private val NUMBER_CHIP_MIN_HEIGHT = 32.dp

// In sp, so that the link grows with the number it stands before.
private val LINK_ICON_SIZE = 16.sp

internal const val TABULAR_FIGURES = "tnum"

private val ORDER_BADGE_SHAPE = RoundedCornerShape(6.dp)
private val NUMBER_SHAPE = RoundedCornerShape(8.dp)
private val TILE_CORNER_RADIUS = 4.dp
private val DASHED_OUTLINE_WIDTH = 1.5.dp
private val DASH_LENGTH = 6.dp
