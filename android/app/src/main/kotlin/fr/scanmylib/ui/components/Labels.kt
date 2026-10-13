package fr.scanmylib.ui.components

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import fr.scanmylib.R
import fr.scanmylib.api.NumberSource
import fr.scanmylib.api.PageStatus
import fr.scanmylib.db.UploadFailure
import fr.scanmylib.db.UploadState
import fr.scanmylib.model.DocumentKind

// Labels and icons of the states shown in the UI.

@StringRes
fun DocumentKind.labelRes(): Int = when (this) {
    DocumentKind.BOOK -> R.string.kind_book
    DocumentKind.DOCUMENT -> R.string.kind_document
}

@DrawableRes
fun DocumentKind.iconRes(): Int = when (this) {
    DocumentKind.BOOK -> R.drawable.ic_menu_book
    DocumentKind.DOCUMENT -> R.drawable.ic_description
}

@StringRes
fun PageStatus.labelRes(): Int = when (this) {
    PageStatus.QUEUED -> R.string.page_status_queued
    PageStatus.PROCESSING -> R.string.page_status_processing
    PageStatus.DONE -> R.string.page_status_done
    PageStatus.ERROR -> R.string.page_status_error
    PageStatus.UNKNOWN -> R.string.page_status_unknown
}

@DrawableRes
fun PageStatus.iconRes(): Int = when (this) {
    PageStatus.QUEUED, PageStatus.UNKNOWN -> R.drawable.ic_schedule
    PageStatus.PROCESSING -> R.drawable.ic_autorenew
    PageStatus.DONE -> R.drawable.ic_check_circle
    PageStatus.ERROR -> R.drawable.ic_error
}

@StringRes
fun NumberSource.labelRes(): Int = when (this) {
    NumberSource.MANUAL -> R.string.number_source_manual
    NumberSource.DETECTED -> R.string.number_source_detected
    NumberSource.HINT -> R.string.number_source_hint
    NumberSource.INFERRED -> R.string.number_source_inferred
}

@StringRes
fun UploadState.labelRes(): Int = when (this) {
    UploadState.QUEUED -> R.string.upload_state_queued
    UploadState.UPLOADING -> R.string.upload_state_uploading
    UploadState.FAILED -> R.string.upload_state_failed
    UploadState.UPLOADED -> R.string.upload_state_uploaded
}

@DrawableRes
fun UploadState.iconRes(): Int = when (this) {
    UploadState.QUEUED -> R.drawable.ic_schedule
    UploadState.UPLOADING -> R.drawable.ic_cloud_upload
    UploadState.FAILED -> R.drawable.ic_error
    UploadState.UPLOADED -> R.drawable.ic_cloud_done
}

@StringRes
fun UploadFailure.labelRes(): Int = when (this) {
    UploadFailure.NETWORK -> R.string.upload_failure_network
    UploadFailure.SERVER_ERROR -> R.string.upload_failure_server_error
    UploadFailure.UNAUTHORIZED -> R.string.upload_failure_unauthorized
    UploadFailure.DOCUMENT_MISSING -> R.string.upload_failure_document_missing
    UploadFailure.TOO_LARGE -> R.string.upload_failure_too_large
    UploadFailure.UNSUPPORTED_TYPE -> R.string.upload_failure_unsupported_type
    UploadFailure.REJECTED -> R.string.upload_failure_rejected
    UploadFailure.FILE_MISSING -> R.string.upload_failure_file_missing
}

/** State of the OCR engine as reported by `GET /api/status`. */
@Composable
fun ocrStateLabel(state: String): String = when (state) {
    "idle" -> stringResource(R.string.ocr_state_idle)
    "starting" -> stringResource(R.string.ocr_state_starting)
    "ready" -> stringResource(R.string.ocr_state_ready)
    "stopping" -> stringResource(R.string.ocr_state_stopping)
    "error" -> stringResource(R.string.ocr_state_error)
    "unreachable" -> stringResource(R.string.ocr_state_unreachable)
    else -> state
}
