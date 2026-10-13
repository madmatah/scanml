package fr.scanmylib.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.pluralStringResource
import fr.scanmylib.R
import fr.scanmylib.db.ServerDocumentState

/** OCR progress of a document, e.g. "42 pages · 40 processed · 2 in progress". */
@Composable
fun pageStatsText(state: ServerDocumentState): String {
    val parts = mutableListOf(pluralStringResource(R.plurals.stats_pages, state.pages, state.pages))
    if (state.done > 0) parts += pluralStringResource(R.plurals.stats_done, state.done, state.done)
    val inProgress = state.queued + state.processing
    if (inProgress > 0) parts += pluralStringResource(R.plurals.stats_in_progress, inProgress, inProgress)
    if (state.errors > 0) parts += pluralStringResource(R.plurals.stats_errors, state.errors, state.errors)
    return parts.joinToString(" · ")
}
