package fr.scanmylib.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// The titles of books and documents, and the app's name, in the phone's serif (Noto Serif on
// Android): nothing to download or to ship. The interface keeps Material's styles, in the phone's
// sans, since Material sets its dialog titles in headlineSmall too.

private const val TABULAR_FIGURES = "tnum"

private val MaterialTypography = Typography()

internal val ScanMyLibTypography = Typography(
    // Counts and page numbers: figures of one width, so that they line up.
    labelMedium = MaterialTypography.labelMedium.copy(fontFeatureSettings = TABULAR_FIGURES),
)

val Typography.wordmark: TextStyle
    get() = Wordmark

val Typography.cardTitle: TextStyle
    get() = CardTitle

private val Wordmark = MaterialTypography.titleLarge.copy(
    fontFamily = FontFamily.Serif,
    fontWeight = FontWeight.SemiBold,
)

private val CardTitle = MaterialTypography.titleMedium.copy(
    fontFamily = FontFamily.Serif,
    fontWeight = FontWeight.SemiBold,
    fontSize = 17.sp,
    lineHeight = 24.sp,
    letterSpacing = 0.sp,
)
