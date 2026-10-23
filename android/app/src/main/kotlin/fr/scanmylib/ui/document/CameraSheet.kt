@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.document

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.model.ScanSource
import fr.scanmylib.ui.components.descriptionRes
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.theme.DISABLED_ALPHA
import kotlinx.coroutines.launch

/**
 * "Scan with…": the cameras "Scan" can open, for this run only, or from now on with "Use as
 * default". The app's camera is disabled on a phone without one. Google's scanner stays
 * available after it failed to start, with a word about it: choosing it tries again.
 */
@Composable
fun CameraSheet(
    scan: ScanUiState,
    onChoose: (camera: ScanSource, makeDefault: Boolean) -> Unit,
    onDismiss: () -> Unit,
) {
    var makeDefault by rememberSaveable { mutableStateOf(false) }
    val sheetState = rememberModalBottomSheetState()
    val scope = rememberCoroutineScope()
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(Modifier.padding(bottom = 16.dp)) {
            Text(
                stringResource(R.string.camera_sheet_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier
                    .padding(horizontal = 24.dp, vertical = 8.dp)
                    .semantics { heading() },
            )
            ScanSource.CAMERAS.forEach { camera ->
                val enabled = camera != ScanSource.CAMERA || scan.hasCamera
                val note = when {
                    !enabled -> R.string.camera_none_on_phone

                    camera == ScanSource.GOOGLE_SCANNER && scan.googleScannerUnavailable ->
                        R.string.camera_did_not_start

                    else -> null
                }
                ListItem(
                    headlineContent = { Text(stringResource(camera.labelRes())) },
                    supportingContent = { Text(stringResource(note ?: camera.descriptionRes())) },
                    leadingContent = { Icon(painterResource(camera.iconRes()), contentDescription = null) },
                    trailingContent = if (camera == scan.defaultCamera) {
                        {
                            Text(
                                stringResource(R.string.camera_default),
                                style = MaterialTheme.typography.labelLarge,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    } else {
                        null
                    },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    modifier = Modifier
                        .alpha(if (enabled) 1f else DISABLED_ALPHA)
                        .clickable(enabled = enabled, role = Role.Button) {
                            // The camera opens once the sheet has slid away.
                            scope.launch { sheetState.hide() }.invokeOnCompletion { onChoose(camera, makeDefault) }
                        },
                )
            }
            HorizontalDivider(Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
            ListItem(
                headlineContent = { Text(stringResource(R.string.camera_use_as_default)) },
                supportingContent = { Text(stringResource(R.string.camera_use_as_default_help)) },
                leadingContent = { Checkbox(checked = makeDefault, onCheckedChange = null) },
                colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                modifier = Modifier.toggleable(value = makeDefault, role = Role.Checkbox) { makeDefault = it },
            )
        }
    }
}
