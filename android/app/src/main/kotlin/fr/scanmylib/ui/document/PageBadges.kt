package fr.scanmylib.ui.document

import androidx.annotation.StringRes
import fr.scanmylib.R
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadState
import fr.scanmylib.ui.components.PageBadge
import fr.scanmylib.ui.components.StatusTone
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.components.tone

internal fun PendingPageEntity.pickBadge(): PageBadge = PageBadge(state.badgeRes, state.iconRes(), state.tone)

internal fun ServerPageEntity.pickBadge(): PageBadge? = when {
    duplicate -> PageBadge(R.string.page_duplicate, R.drawable.ic_content_copy, StatusTone.NEUTRAL)
    excluded -> PageBadge(R.string.page_excluded, R.drawable.ic_block, StatusTone.NEUTRAL)
    status == PageStatus.DONE -> null
    else -> PageBadge(status.badgeRes, status.iconRes(), status.tone)
}

@get:StringRes
private val UploadState.badgeRes: Int
    get() = when (this) {
        UploadState.QUEUED -> R.string.upload_badge_queued
        UploadState.UPLOADING -> R.string.upload_badge_uploading
        UploadState.FAILED -> R.string.upload_badge_failed
        UploadState.UPLOADED -> R.string.upload_badge_uploaded
    }

@get:StringRes
private val PageStatus.badgeRes: Int
    get() = when (this) {
        PageStatus.QUEUED -> R.string.page_badge_queued
        PageStatus.ERROR -> R.string.page_badge_failed
        PageStatus.PROCESSING, PageStatus.DONE, PageStatus.UNKNOWN -> labelRes()
    }
