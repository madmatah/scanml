package fr.scanmylib.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.pluralStringResource
import fr.scanmylib.R
import fr.scanmylib.db.ServerDocumentState

/** The pages of a document on the PC and what differs from normal, e.g. "42 pages · 2 being read". */
@Composable
fun pageStatsText(state: ServerDocumentState): String {
    val parts = mutableListOf(pluralStringResource(R.plurals.stats_pages, state.pages, state.pages))
    val inProgress = state.queued + state.processing
    if (inProgress > 0) parts += pluralStringResource(R.plurals.stats_in_progress, inProgress, inProgress)
    if (state.errors > 0) parts += pluralStringResource(R.plurals.stats_errors, state.errors, state.errors)
    return parts.joinToString(" · ")
}
