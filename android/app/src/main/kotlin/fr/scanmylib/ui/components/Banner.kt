package fr.scanmylib.ui.components

import androidx.annotation.DrawableRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp

@Composable
fun AttentionBanner(
    text: String,
    @DrawableRes icon: Int,
    actionLabel: String,
    onAction: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Banner(text, icon, actionLabel, onAction, pickStatusColors(StatusTone.ATTENTION), modifier)
}

@Composable
fun ErrorBanner(
    text: String,
    @DrawableRes icon: Int,
    actionLabel: String,
    onAction: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Banner(text, icon, actionLabel, onAction, pickStatusColors(StatusTone.FAILURE), modifier)
}

@Composable
private fun Banner(
    text: String,
    @DrawableRes icon: Int,
    actionLabel: String,
    onAction: () -> Unit,
    colors: StatusColors,
    modifier: Modifier = Modifier,
) {
    Surface(
        color = colors.container,
        contentColor = colors.content,
        shape = MaterialTheme.shapes.medium,
        modifier = modifier.fillMaxWidth(),
    ) {
        // The action goes under the text, so that larger text never squeezes them side by side.
        Column(Modifier.padding(start = 16.dp, top = 16.dp, end = 8.dp, bottom = 4.dp)) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(end = 8.dp),
            ) {
                Icon(painterResource(icon), contentDescription = null, modifier = Modifier.size(24.dp))
                Text(text, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
            }
            TextButton(
                onClick = onAction,
                colors = ButtonDefaults.textButtonColors(contentColor = colors.content),
                modifier = Modifier.align(Alignment.End),
            ) {
                Text(actionLabel)
            }
        }
    }
}
