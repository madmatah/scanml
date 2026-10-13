package fr.scanmylib.ui.components

import androidx.annotation.DrawableRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.pairing.ConnectionCheck

@Composable
fun BackButton(onClick: () -> Unit) {
    IconButton(onClick = onClick) {
        Icon(painterResource(R.drawable.ic_arrow_back), contentDescription = stringResource(R.string.back))
    }
}

/** A highlighted message with an icon: a problem, or the state of the connection to the PC. */
@Composable
fun MessageCard(
    text: String,
    @DrawableRes icon: Int,
    modifier: Modifier = Modifier,
    isError: Boolean = false,
) {
    val colors = if (isError) {
        CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
            contentColor = MaterialTheme.colorScheme.onErrorContainer,
        )
    } else {
        CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer,
            contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
        )
    }
    Card(colors = colors, modifier = modifier.fillMaxWidth()) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(16.dp),
        ) {
            Icon(painterResource(icon), contentDescription = null)
            Text(text, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/** A small icon and text, e.g. the upload state of a page. */
@Composable
fun StatusLine(
    text: String,
    @DrawableRes icon: Int,
    modifier: Modifier = Modifier,
    color: Color = MaterialTheme.colorScheme.onSurfaceVariant,
) {
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier,
    ) {
        Icon(painterResource(icon), contentDescription = null, tint = color, modifier = Modifier.size(16.dp))
        Text(text, style = MaterialTheme.typography.labelMedium, color = color, maxLines = 1)
    }
}

/** User-facing explanation of a [ConnectionCheck]. */
@Composable
fun connectionCheckMessage(check: ConnectionCheck): String = when (check) {
    is ConnectionCheck.Ok ->
        stringResource(R.string.connection_ok, check.status.version, ocrStateLabel(check.status.ocr.state))
    ConnectionCheck.Unreachable -> stringResource(R.string.connection_unreachable)
    ConnectionCheck.NotScanMyLib -> stringResource(R.string.connection_not_scanmylib)
    ConnectionCheck.IncompatibleServer -> stringResource(R.string.connection_incompatible)
    ConnectionCheck.TokenRefused -> stringResource(R.string.connection_token_refused)
    is ConnectionCheck.Failed -> stringResource(R.string.connection_failed, check.detail)
}
