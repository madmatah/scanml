@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.settings

import android.text.format.Formatter
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.scanmylib.BuildConfig
import fr.scanmylib.R
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.ui.components.BackButton
import fr.scanmylib.ui.components.connectionCheckMessage

@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onChangeServer: () -> Unit,
    onUnpaired: () -> Unit,
    viewModel: SettingsViewModel = viewModel(factory = SettingsViewModel.Factory),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val currentOnUnpaired by rememberUpdatedState(onUnpaired)
    LaunchedEffect(viewModel) {
        viewModel.unpaired.collect { currentOnUnpaired() }
    }
    val snackbarHostState = remember { SnackbarHostState() }
    val resources = LocalResources.current
    LaunchedEffect(viewModel) {
        viewModel.settingNotSaved.collect {
            snackbarHostState.showSnackbar(resources.getString(R.string.message_setting_not_saved))
        }
    }
    var confirmingUnpair by rememberSaveable { mutableStateOf(false) }
    val settings = state.settings
    val server = settings?.server

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.settings_title)) },
                navigationIcon = { BackButton(onBack) },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState()),
        ) {
            SectionHeader(R.string.settings_section_pc)
            ListItem(
                headlineContent = { Text(server?.displayUrl ?: stringResource(R.string.settings_not_paired)) },
                supportingContent = state.lastCheck?.let { check -> { Text(connectionCheckMessage(check)) } },
            )
            if (state.testing) {
                LinearProgressIndicator(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
                OutlinedButton(onClick = viewModel::testConnection, enabled = server != null && !state.testing) {
                    Text(stringResource(R.string.settings_test_connection))
                }
                OutlinedButton(onClick = onChangeServer) {
                    Text(stringResource(R.string.settings_change_server))
                }
            }
            if (server != null) {
                TextButton(onClick = { confirmingUnpair = true }, modifier = Modifier.padding(horizontal = 8.dp)) {
                    Icon(painterResource(R.drawable.ic_link_off), contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text(stringResource(R.string.settings_unpair))
                }
            }

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            SectionHeader(R.string.settings_section_upload)
            SwitchItem(
                title = R.string.settings_wifi_only,
                description = R.string.settings_wifi_only_help,
                checked = settings?.wifiOnly ?: false,
                onCheckedChange = viewModel::setWifiOnly,
            )
            SwitchItem(
                title = R.string.settings_keep_copies,
                description = R.string.settings_keep_copies_help,
                checked = settings?.keepLocalCopies ?: false,
                onCheckedChange = viewModel::setKeepLocalCopies,
            )
            val copies = state.keptCopies
            if (copies.count > 0) {
                val size = Formatter.formatShortFileSize(LocalContext.current, copies.bytes)
                ListItem(
                    headlineContent = {
                        Text(pluralStringResource(R.plurals.settings_kept_copies, copies.count, copies.count, size))
                    },
                    trailingContent = {
                        TextButton(onClick = viewModel::deleteKeptCopies) { Text(stringResource(R.string.delete)) }
                    },
                )
            }

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            SectionHeader(R.string.settings_scanner_mode)
            Text(
                stringResource(R.string.settings_scanner_help),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
            Column(Modifier.selectableGroup()) {
                ScannerMode.entries.forEach { mode ->
                    RadioItem(
                        title = mode.labelRes(),
                        description = mode.descriptionRes(),
                        selected = settings?.scannerMode == mode,
                        onSelect = { viewModel.setScannerMode(mode) },
                    )
                }
            }

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            SectionHeader(R.string.settings_section_about)
            ListItem(
                headlineContent = { Text(stringResource(R.string.settings_version, BuildConfig.VERSION_NAME)) },
                supportingContent = { Text(stringResource(R.string.settings_about)) },
            )
        }
    }

    if (confirmingUnpair) {
        AlertDialog(
            onDismissRequest = { confirmingUnpair = false },
            title = { Text(stringResource(R.string.settings_unpair_title)) },
            text = { Text(stringResource(R.string.settings_unpair_message)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmingUnpair = false
                        viewModel.unpair()
                    },
                ) {
                    Text(stringResource(R.string.settings_unpair_confirm))
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmingUnpair = false }) { Text(stringResource(R.string.cancel)) }
            },
        )
    }
}

@Composable
private fun SectionHeader(@StringRes title: Int) {
    Text(
        stringResource(title),
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(start = 16.dp, top = 16.dp, end = 16.dp, bottom = 4.dp),
    )
}

/** One choice of a setting, selected by tapping anywhere on its row. */
@Composable
private fun RadioItem(
    @StringRes title: Int,
    @StringRes description: Int,
    selected: Boolean,
    onSelect: () -> Unit,
) {
    ListItem(
        headlineContent = { Text(stringResource(title)) },
        supportingContent = { Text(stringResource(description)) },
        leadingContent = { RadioButton(selected = selected, onClick = null) },
        modifier = Modifier.selectable(selected = selected, role = Role.RadioButton, onClick = onSelect),
    )
}

@StringRes
private fun ScannerMode.labelRes(): Int = when (this) {
    ScannerMode.CROP_ONLY -> R.string.settings_scanner_mode_crop
    ScannerMode.FILTERS -> R.string.settings_scanner_mode_filters
    ScannerMode.FULL -> R.string.settings_scanner_mode_full
}

@StringRes
private fun ScannerMode.descriptionRes(): Int = when (this) {
    ScannerMode.CROP_ONLY -> R.string.settings_scanner_mode_crop_help
    ScannerMode.FILTERS -> R.string.settings_scanner_mode_filters_help
    ScannerMode.FULL -> R.string.settings_scanner_mode_full_help
}

/** A setting toggled by tapping anywhere on its row. */
@Composable
private fun SwitchItem(
    @StringRes title: Int,
    @StringRes description: Int,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    ListItem(
        headlineContent = { Text(stringResource(title)) },
        supportingContent = { Text(stringResource(description)) },
        trailingContent = { Switch(checked = checked, onCheckedChange = null) },
        modifier = Modifier.toggleable(value = checked, role = Role.Switch, onValueChange = onCheckedChange),
    )
}
