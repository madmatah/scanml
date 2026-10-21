package fr.scanmylib.ui.components

import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import fr.scanmylib.R

// The text beside it names the screen.
@Composable
fun BrandMark(modifier: Modifier = Modifier) {
    Icon(
        painterResource(R.drawable.brand_mark),
        contentDescription = null,
        tint = MaterialTheme.colorScheme.primary,
        modifier = modifier,
    )
}
