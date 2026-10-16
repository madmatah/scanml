package fr.scanmylib.ui.document

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadState
import fr.scanmylib.library.serverThumbUrl
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.ui.components.LocalImage
import fr.scanmylib.ui.components.ServerImage
import fr.scanmylib.ui.components.StatusLine
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.labelRes
import java.io.File

/**
 * A scan made on this phone, with its upload state: its [image] on the phone, or the PC's
 * thumbnail once uploaded without a local copy.
 */
@Composable
fun LocalPageTile(page: PendingPageEntity, image: File?, server: ServerConfig?, onClick: () -> Unit) {
    val failed = page.state == UploadState.FAILED
    PageTile(
        title = page.pageNumberHint?.let { stringResource(R.string.page_label, it.toString()) }
            ?: stringResource(R.string.page_without_number),
        onClick = onClick,
        image = { modifier ->
            val serverThumbUrl = page.serverThumbUrl()
            if (serverThumbUrl != null) {
                ServerImage(server, serverThumbUrl, contentDescription = null, modifier = modifier)
            } else {
                LocalImage(image, contentDescription = null, modifier = modifier)
            }
        },
        status = {
            StatusLine(
                stringResource(page.state.labelRes()),
                page.state.iconRes(),
                color = if (failed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        },
    )
}

/** A page known by the server, with its OCR state. */
@Composable
fun ServerPageTile(page: ServerPageEntity, server: ServerConfig?, onClick: () -> Unit) {
    PageTile(
        title = page.pageLabel?.let { stringResource(R.string.page_label, it) }
            ?: stringResource(R.string.page_without_number),
        onClick = onClick,
        image = { modifier -> ServerImage(server, page.thumbUrl, contentDescription = null, modifier = modifier) },
        status = {
            when {
                page.duplicate -> StatusLine(stringResource(R.string.page_duplicate), R.drawable.ic_content_copy)
                page.excluded -> StatusLine(stringResource(R.string.page_excluded), R.drawable.ic_block)
                else -> StatusLine(
                    stringResource(page.status.badgeRes()),
                    page.status.iconRes(),
                    color = if (page.status == PageStatus.ERROR) {
                        MaterialTheme.colorScheme.error
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
        },
    )
}

@Composable
private fun PageTile(
    title: String,
    onClick: () -> Unit,
    image: @Composable (Modifier) -> Unit,
    status: @Composable () -> Unit,
) {
    Card(onClick = onClick) {
        Box(
            Modifier
                .fillMaxWidth()
                .aspectRatio(PAGE_ASPECT_RATIO)
                .background(MaterialTheme.colorScheme.surfaceVariant),
        ) {
            image(Modifier.matchParentSize())
        }
        Column(Modifier.padding(horizontal = 8.dp, vertical = 6.dp)) {
            Text(title, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            status()
        }
    }
}

/** The status in the few words a tile has room for; the page's dialog says it in full. */
private fun PageStatus.badgeRes(): Int = when (this) {
    PageStatus.QUEUED -> R.string.page_badge_queued
    PageStatus.ERROR -> R.string.page_badge_failed
    else -> labelRes()
}

/** Portrait page (A4 is about 1:1.41). */
private const val PAGE_ASPECT_RATIO = 1f / 1.41f
