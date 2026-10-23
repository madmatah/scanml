package fr.scanmylib.ui.document

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import fr.scanmylib.R
import fr.scanmylib.library.PreparationOutcome
import fr.scanmylib.ui.components.AttentionBanner
import fr.scanmylib.ui.components.ErrorBanner

/** How the last copies to the run ended, on the document and in the review alike. */
@Composable
fun PreparationOutcomeBanner(outcome: PreparationOutcome, onDismiss: () -> Unit, modifier: Modifier = Modifier) {
    val dismissLabel = stringResource(R.string.banner_dismiss)
    when (outcome) {
        is PreparationOutcome.PhotosSkipped -> AttentionBanner(
            listOfNotNull(
                outcome.unsupported.takeIf { it > 0 }?.let {
                    pluralStringResource(R.plurals.message_unsupported_photos, it, it)
                },
                outcome.tooLarge.takeIf { it > 0 }?.let {
                    pluralStringResource(R.plurals.message_too_large_photos, it, it)
                },
                outcome.unreadable.takeIf { it > 0 }?.let {
                    pluralStringResource(R.plurals.message_unreadable_photos, it, it)
                },
            ).joinToString(" "),
            R.drawable.ic_photo_library,
            dismissLabel,
            onDismiss,
            modifier,
        )

        PreparationOutcome.ImportFailed -> ErrorBanner(
            stringResource(R.string.message_import_failed),
            R.drawable.ic_error,
            dismissLabel,
            onDismiss,
            modifier,
        )

        PreparationOutcome.StorageFull -> ErrorBanner(
            stringResource(R.string.message_storage_full),
            R.drawable.ic_error,
            dismissLabel,
            onDismiss,
            modifier,
        )
    }
}
