@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.settings

import android.content.pm.PackageManager
import android.text.format.Formatter
import androidx.annotation.StringRes
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
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
import fr.scanmylib.diagnostics.CrashReportDialog
import fr.scanmylib.diagnostics.CrashReporter
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.model.ThemeMode
import fr.scanmylib.ui.components.BackButton
import fr.scanmylib.ui.components.ChoiceRow
import fr.scanmylib.ui.components.ScreenTitle
import fr.scanmylib.ui.components.SectionHeader
import fr.scanmylib.ui.components.SettingSwitchRow
import fr.scanmylib.ui.components.UpdateBanner
import fr.scanmylib.ui.components.connectionCheckMessage
import fr.scanmylib.ui.components.descriptionRes
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.theme.canUseWallpaperColors
import fr.scanmylib.update.UpdateState

@Composable
fun SettingsScreen(
    onBack: () -> Unit,
    onChangeServer: () -> Unit,
    onUnpaired: () -> Unit,
    viewModel: SettingsViewModel = viewModel(factory = SettingsViewModel.Factory),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val update by viewModel.updateState.collectAsStateWithLifecycle()
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
    SettingsContent(
        state = state,
        update = update,
        snackbarHostState = snackbarHostState,
        onBack = onBack,
        onChangeServer = onChangeServer,
        onTestConnection = viewModel::testConnection,
        onUnpair = viewModel::unpair,
        onWifiOnly = viewModel::setWifiOnly,
        onKeepLocalCopies = viewModel::setKeepLocalCopies,
        onDeleteKeptCopies = viewModel::deleteKeptCopies,
        onDefaultCamera = viewModel::setDefaultCamera,
        onScannerMode = viewModel::setScannerMode,
        onThemeMode = viewModel::setThemeMode,
        onUsesWallpaperColors = viewModel::setUsesWallpaperColors,
        onCheckForUpdate = viewModel::checkForUpdate,
        onInstallUpdate = viewModel::installUpdate,
        onCancelUpdate = viewModel::cancelUpdate,
    )
}

/** Apart from the view model, so that a test draws the settings from invented state. */
@Composable
internal fun SettingsContent(
    state: SettingsUiState,
    update: UpdateState,
    snackbarHostState: SnackbarHostState,
    onBack: () -> Unit,
    onChangeServer: () -> Unit,
    onTestConnection: () -> Unit,
    onUnpair: () -> Unit,
    onWifiOnly: (Boolean) -> Unit,
    onKeepLocalCopies: (Boolean) -> Unit,
    onDeleteKeptCopies: () -> Unit,
    onDefaultCamera: (ScanSource) -> Unit,
    onScannerMode: (ScannerMode) -> Unit,
    onThemeMode: (ThemeMode) -> Unit,
    onUsesWallpaperColors: (Boolean) -> Unit,
    onCheckForUpdate: () -> Unit,
    onInstallUpdate: () -> Unit,
    onCancelUpdate: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var confirmingUnpair by rememberSaveable { mutableStateOf(false) }
    var isChoosingTheme by rememberSaveable { mutableStateOf(false) }
    val settings = state.settings
    val server = settings?.server

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = { ScreenTitle(stringResource(R.string.settings_title)) },
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
            SettingsSectionHeader(R.string.settings_section_pc)
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
                OutlinedButton(onClick = onTestConnection, enabled = server != null && !state.testing) {
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

            SettingsSectionHeader(R.string.settings_section_upload)
            SettingSwitchRow(
                label = stringResource(R.string.settings_wifi_only),
                description = stringResource(R.string.settings_wifi_only_help),
                checked = settings?.wifiOnly ?: false,
                onCheckedChange = onWifiOnly,
            )
            SettingSwitchRow(
                label = stringResource(R.string.settings_keep_copies),
                description = stringResource(R.string.settings_keep_copies_help),
                checked = settings?.keepLocalCopies ?: false,
                onCheckedChange = onKeepLocalCopies,
            )
            val copies = state.keptCopies
            if (copies.count > 0) {
                val size = Formatter.formatShortFileSize(LocalContext.current, copies.bytes)
                ListItem(
                    headlineContent = {
                        Text(pluralStringResource(R.plurals.settings_kept_copies, copies.count, copies.count, size))
                    },
                    trailingContent = {
                        TextButton(onClick = onDeleteKeptCopies) { Text(stringResource(R.string.delete)) }
                    },
                )
            }

            SettingsSectionHeader(R.string.settings_default_camera)
            val context = LocalContext.current
            val hasCamera =
                remember(context) { context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) }
            Column(Modifier.selectableGroup()) {
                ScanSource.CAMERAS.forEach { camera ->
                    val enabled = camera != ScanSource.CAMERA || hasCamera
                    ChoiceRow(
                        label = stringResource(camera.labelRes()),
                        description = stringResource(
                            if (enabled) camera.descriptionRes() else R.string.camera_none_on_phone,
                        ),
                        selected = settings?.defaultCamera == camera,
                        enabled = enabled,
                        onSelect = { onDefaultCamera(camera) },
                    )
                }
            }

            SettingsSectionHeader(R.string.settings_scanner_mode)
            Text(
                stringResource(R.string.settings_scanner_help),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
            Column(Modifier.selectableGroup()) {
                ScannerMode.entries.forEach { mode ->
                    ChoiceRow(
                        label = stringResource(mode.labelRes()),
                        description = stringResource(mode.descriptionRes()),
                        selected = settings?.scannerMode == mode,
                        onSelect = { onScannerMode(mode) },
                    )
                }
            }

            SettingsSectionHeader(R.string.settings_section_appearance)
            ListItem(
                headlineContent = { Text(stringResource(R.string.settings_theme)) },
                supportingContent = { Text(stringResource((settings?.themeMode ?: ThemeMode.DEFAULT).labelRes())) },
                modifier = Modifier.clickable(role = Role.Button) { isChoosingTheme = true },
            )
            if (canUseWallpaperColors) {
                SettingSwitchRow(
                    label = stringResource(R.string.settings_wallpaper_colors),
                    description = stringResource(R.string.settings_wallpaper_colors_help),
                    checked = settings?.usesWallpaperColors ?: false,
                    onCheckedChange = onUsesWallpaperColors,
                )
            }

            SettingsSectionHeader(R.string.settings_section_about)
            ListItem(
                headlineContent = { Text(stringResource(R.string.settings_version, BuildConfig.VERSION_NAME)) },
                supportingContent = { Text(stringResource(R.string.settings_about)) },
            )
            // Tapping it asks the PC now.
            ListItem(
                headlineContent = { Text(stringResource(R.string.settings_update_check)) },
                supportingContent = {
                    Text(
                        stringResource(
                            when (update) {
                                UpdateState.Checking -> R.string.settings_update_checking
                                UpdateState.UpToDate -> R.string.settings_update_up_to_date
                                UpdateState.CheckFailed -> R.string.settings_update_unreachable
                                is UpdateState.WithUpdate -> R.string.settings_update_offered
                                UpdateState.Unknown -> R.string.settings_update_not_checked
                            },
                        ),
                    )
                },
                modifier = Modifier.clickable(
                    enabled = server != null,
                    role = Role.Button,
                    onClick = onCheckForUpdate,
                ),
            )
            UpdateBanner(
                update,
                onInstall = onInstallUpdate,
                onCancel = onCancelUpdate,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
            val crashReports = remember(context) { CrashReporter.reports(context) }
            var crashReport by remember { mutableStateOf(crashReports.read()) }
            var showingCrashReport by rememberSaveable { mutableStateOf(false) }
            crashReport?.let { report ->
                ListItem(
                    headlineContent = { Text(stringResource(R.string.settings_last_crash)) },
                    supportingContent = { Text(stringResource(R.string.settings_last_crash_help)) },
                    modifier = Modifier.clickable(role = Role.Button) { showingCrashReport = true },
                )
                if (showingCrashReport) {
                    CrashReportDialog(
                        report,
                        onClose = { showingCrashReport = false },
                        onDelete = {
                            crashReports.delete()
                            crashReport = null
                            showingCrashReport = false
                        },
                    )
                }
            }
        }
    }

    if (isChoosingTheme) {
        ThemeDialog(
            selected = settings?.themeMode ?: ThemeMode.DEFAULT,
            onSelect = { mode ->
                isChoosingTheme = false
                onThemeMode(mode)
            },
            onClose = { isChoosingTheme = false },
        )
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
                        onUnpair()
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
private fun SettingsSectionHeader(@StringRes title: Int, modifier: Modifier = Modifier) {
    SectionHeader(
        stringResource(title),
        color = MaterialTheme.colorScheme.primary,
        modifier = modifier.padding(horizontal = 16.dp),
    )
}

@Composable
private fun ThemeDialog(
    selected: ThemeMode,
    onSelect: (ThemeMode) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    AlertDialog(
        onDismissRequest = onClose,
        modifier = modifier,
        title = { Text(stringResource(R.string.settings_theme)) },
        text = {
            Column(Modifier.selectableGroup()) {
                ThemeMode.entries.forEach { mode ->
                    ChoiceRow(
                        label = stringResource(mode.labelRes()),
                        selected = mode == selected,
                        onSelect = { onSelect(mode) },
                        // The dialog has margins of its own.
                        contentPadding = PaddingValues(),
                    )
                }
            }
        },
        confirmButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.cancel)) } },
    )
}

@StringRes
private fun ThemeMode.labelRes(): Int = when (this) {
    ThemeMode.SAME_AS_PHONE -> R.string.theme_mode_same_as_phone
    ThemeMode.LIGHT -> R.string.theme_mode_light
    ThemeMode.DARK -> R.string.theme_mode_dark
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
