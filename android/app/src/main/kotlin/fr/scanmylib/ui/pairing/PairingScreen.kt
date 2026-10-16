@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.pairing

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.scanmylib.R
import fr.scanmylib.pairing.AddressError
import fr.scanmylib.pairing.ConnectionCheck
import fr.scanmylib.pairing.PairingError
import fr.scanmylib.ui.components.BackButton
import fr.scanmylib.ui.components.MessageCard
import fr.scanmylib.ui.components.connectionCheckMessage

@Composable
fun PairingScreen(
    onPaired: () -> Unit,
    onBack: (() -> Unit)?,
    viewModel: PairingViewModel = viewModel(factory = PairingViewModel.Factory),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val currentOnPaired by rememberUpdatedState(onPaired)
    LaunchedEffect(state.paired) {
        if (state.paired) currentOnPaired()
    }
    val scanQrCode = rememberQrCodeScanner(
        onScanned = viewModel::onQrCodeScanned,
        onUnavailable = viewModel::onScannerUnavailable,
    )

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.pairing_title)) },
                navigationIcon = { onBack?.let { BackButton(it) } },
            )
        },
    ) { padding ->
        Column(
            verticalArrangement = Arrangement.spacedBy(16.dp),
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .consumeWindowInsets(padding)
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 16.dp),
        ) {
            Text(stringResource(R.string.pairing_intro), style = MaterialTheme.typography.bodyLarge)
            Button(onClick = scanQrCode, enabled = !state.checking, modifier = Modifier.fillMaxWidth()) {
                Icon(painterResource(R.drawable.ic_qr_code_scanner), contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.pairing_scan_qr_code))
            }
            Text(
                stringResource(R.string.pairing_manual_intro),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedTextField(
                value = state.url,
                onValueChange = viewModel::onUrlChange,
                label = { Text(stringResource(R.string.pairing_url_label)) },
                placeholder = { Text(stringResource(R.string.pairing_url_placeholder)) },
                isError = state.urlError != null,
                supportingText = state.urlError?.let { error -> { Text(stringResource(error.messageRes())) } },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            TokenField(
                token = state.token,
                onTokenChange = viewModel::onTokenChange,
                invalid = state.tokenInvalid,
                onDone = viewModel::submit,
            )
            Button(onClick = viewModel::submit, enabled = !state.checking, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.pairing_connect))
            }
            if (state.checking) {
                LinearProgressIndicator(Modifier.fillMaxWidth())
                Text(stringResource(R.string.pairing_checking), style = MaterialTheme.typography.bodyMedium)
            }
            state.problem?.let { MessageCard(problemMessage(it), R.drawable.ic_error, isError = true) }
        }
    }
}

@Composable
private fun TokenField(token: String, onTokenChange: (String) -> Unit, invalid: Boolean, onDone: () -> Unit) {
    var visible by rememberSaveable { mutableStateOf(false) }
    OutlinedTextField(
        value = token,
        onValueChange = onTokenChange,
        label = { Text(stringResource(R.string.pairing_token_label)) },
        isError = invalid,
        supportingText = if (invalid) {
            { Text(stringResource(R.string.pairing_token_invalid)) }
        } else {
            null
        },
        singleLine = true,
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(
            keyboardType = KeyboardType.Password,
            autoCorrectEnabled = false,
            imeAction = ImeAction.Done,
        ),
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        trailingIcon = {
            IconButton(onClick = { visible = !visible }) {
                Icon(
                    painterResource(if (visible) R.drawable.ic_visibility_off else R.drawable.ic_visibility),
                    contentDescription = stringResource(
                        if (visible) R.string.pairing_hide_token else R.string.pairing_show_token,
                    ),
                )
            }
        },
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun problemMessage(problem: PairingProblem): String = when (problem) {
    is PairingProblem.InvalidQrCode -> stringResource(
        when (problem.error) {
            PairingError.NOT_A_PAIRING_CODE -> R.string.pairing_error_not_a_pairing_code
            PairingError.INVALID_URL -> R.string.pairing_error_qr_invalid_url
            PairingError.INVALID_TOKEN -> R.string.pairing_error_qr_invalid_token
        },
    )
    // A first pairing, too: "no longer recognizes this phone" would be wrong here.
    is PairingProblem.Connection -> if (problem.check == ConnectionCheck.TokenRefused) {
        stringResource(R.string.pairing_error_token_refused)
    } else {
        connectionCheckMessage(problem.check)
    }
    is PairingProblem.ScannerUnavailable ->
        stringResource(R.string.pairing_error_scanner_unavailable) + "\n\n" + problem.detail
}

@StringRes
private fun AddressError.messageRes(): Int = when (this) {
    AddressError.EMPTY -> R.string.pairing_url_empty
    AddressError.MALFORMED -> R.string.pairing_url_malformed
    AddressError.UNSUPPORTED_SCHEME -> R.string.pairing_url_unsupported_scheme
    AddressError.NOT_A_ROOT_URL -> R.string.pairing_url_not_root
}
