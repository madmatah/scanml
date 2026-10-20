package fr.scanmylib.ui.document

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import fr.scanmylib.R
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.library.PageLabel
import fr.scanmylib.library.parsePageLabel
import fr.scanmylib.library.serverThumbUrl
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.ui.components.LocalImage
import fr.scanmylib.ui.components.MAX_PAGE_LABEL_GRAPHEMES
import fr.scanmylib.ui.components.PageThumbnail
import fr.scanmylib.ui.components.ServerImage
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.components.sanitizeTextFromPc
import java.io.File

/**
 * A scan made on this phone, with its upload state: its [image] on the phone, or the PC's
 * thumbnail once uploaded without a local copy.
 */
@Composable
fun LocalPageTile(page: PendingPageEntity, image: File?, server: ServerConfig?, onClick: () -> Unit) {
    PageThumbnail(
        label = page.pageNumberHint?.let { PageLabel.OnePage(it.toString()) } ?: PageLabel.Unnumbered,
        status = stringResource(page.state.labelRes()),
        badge = page.pickBadge(),
        onClick = onClick,
        image = { modifier ->
            val serverThumbUrl = page.serverThumbUrl()
            if (serverThumbUrl != null) {
                ServerImage(server, serverThumbUrl, contentDescription = null, modifier = modifier)
            } else {
                LocalImage(image, contentDescription = null, modifier = modifier)
            }
        },
    )
}

/** A page known by the server, with its OCR state. */
@Composable
fun ServerPageTile(page: ServerPageEntity, server: ServerConfig?, onClick: () -> Unit) {
    PageThumbnail(
        label = parsePageLabel(sanitizeTextFromPc(page.pageLabel.orEmpty(), MAX_PAGE_LABEL_GRAPHEMES)),
        status = page.statusText(),
        badge = page.pickBadge(),
        isSetAside = page.duplicate || page.excluded,
        onClick = onClick,
        image = { modifier -> ServerImage(server, page.thumbUrl, contentDescription = null, modifier = modifier) },
    )
}

@Composable
private fun ServerPageEntity.statusText(): String = when {
    duplicate -> stringResource(R.string.server_page_duplicate)
    excluded -> stringResource(R.string.server_page_excluded)
    else -> stringResource(status.labelRes())
}
