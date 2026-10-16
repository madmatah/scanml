@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.library

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.scanmylib.R
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.ui.components.iconRes

/**
 * "New document", a full-screen form: the title (focused), the author, the kind, and whether
 * curved pages are flattened. Created, the document opens with its camera ("Create and scan") or
 * the photo picker ("Create and import"); [forShare]: the photos shared with the app join it
 * ("Create and add the photos"). Works with the PC off: the PC gets the document with its first
 * upload.
 */
@Composable
fun NewDocumentScreen(
    forShare: Boolean,
    onCreated: (documentId: String, then: AfterCreate) -> Unit,
    onCancel: () -> Unit,
    viewModel: NewDocumentViewModel = viewModel(factory = NewDocumentViewModel.Factory),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val currentOnCreated by rememberUpdatedState(onCreated)
    LaunchedEffect(viewModel) {
        viewModel.created.collect { (id, then) -> currentOnCreated(id, then) }
    }
    var title by rememberSaveable { mutableStateOf("") }
    var author by rememberSaveable { mutableStateOf("") }
    var kind by rememberSaveable { mutableStateOf(DocumentKind.BOOK) }
    var unwarp by rememberSaveable { mutableStateOf(true) }
    var unwarpTouched by rememberSaveable { mutableStateOf(false) }
    val titleFocus = remember { FocusRequester() }
    LaunchedEffect(titleFocus) { titleFocus.requestFocus() }
    val create = { then: AfterCreate ->
        viewModel.create(NewDocument(title.trim(), author.trim(), kind, unwarp), then)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.new_document_title)) },
                navigationIcon = {
                    IconButton(onClick = onCancel) {
                        Icon(painterResource(R.drawable.ic_close), contentDescription = stringResource(R.string.cancel))
                    }
                },
            )
        },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding(),
        ) {
            Column(
                verticalArrangement = Arrangement.spacedBy(16.dp),
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 8.dp),
            ) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = NewDocument.fieldText(it) },
                    label = { Text(stringResource(R.string.new_document_name)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Sentences,
                        imeAction = ImeAction.Next,
                    ),
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(titleFocus),
                )
                OutlinedTextField(
                    value = author,
                    onValueChange = { author = NewDocument.fieldText(it) },
                    label = { Text(stringResource(R.string.new_document_author)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Words,
                        imeAction = ImeAction.Done,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    stringResource(R.string.new_document_kind),
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.semantics { heading() },
                )
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    DocumentKind.entries.forEachIndexed { index, option ->
                        SegmentedButton(
                            selected = kind == option,
                            onClick = {
                                kind = option
                                unwarp = unwarpForKind(option, unwarp, unwarpTouched)
                            },
                            shape = SegmentedButtonDefaults.itemShape(index, DocumentKind.entries.size),
                            icon = {
                                SegmentedButtonDefaults.Icon(active = kind == option) {
                                    Icon(
                                        painterResource(option.iconRes()),
                                        contentDescription = null,
                                        modifier = Modifier.size(SegmentedButtonDefaults.IconSize),
                                    )
                                }
                            },
                            modifier = Modifier.heightIn(min = 48.dp),
                        ) {
                            Text(stringResource(option.choiceRes()))
                        }
                    }
                }
                // For both kinds: the kind only sets its default.
                ListItem(
                    headlineContent = { Text(stringResource(R.string.new_document_unwarp)) },
                    supportingContent = { Text(stringResource(R.string.new_document_unwarp_help)) },
                    trailingContent = { Switch(checked = unwarp, onCheckedChange = null) },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                    modifier = Modifier.toggleable(value = unwarp, role = Role.Switch) {
                        unwarp = it
                        unwarpTouched = true
                    },
                )
            }
            Column(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(16.dp),
            ) {
                state.failure?.let { failure ->
                    Text(
                        stringResource(
                            if (failure == CreateFailure.STORAGE_FULL) R.string.message_storage_full else R.string.new_document_failed,
                        ),
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                val enabled = title.isNotBlank() && !state.creating
                if (forShare) {
                    CreateButton(R.string.new_document_create_add_shared, R.drawable.ic_add, enabled, filled = true) {
                        create(AfterCreate.ADD_SHARED)
                    }
                } else {
                    CreateButton(R.string.new_document_create_scan, R.drawable.ic_document_scanner, enabled, filled = true) {
                        create(AfterCreate.SCAN)
                    }
                    CreateButton(R.string.new_document_create_import, R.drawable.ic_photo_library, enabled, filled = false) {
                        create(AfterCreate.IMPORT)
                    }
                }
                if (state.creating) {
                    Row(horizontalArrangement = Arrangement.Center, modifier = Modifier.fillMaxWidth()) {
                        CircularProgressIndicator(Modifier.size(24.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun CreateButton(label: Int, icon: Int, enabled: Boolean, filled: Boolean, onClick: () -> Unit) {
    val content: @Composable () -> Unit = {
        Icon(painterResource(icon), contentDescription = null)
        Spacer(Modifier.width(8.dp))
        Text(stringResource(label))
    }
    val modifier = Modifier
        .fillMaxWidth()
        .heightIn(min = 56.dp)
    if (filled) {
        Button(onClick = onClick, enabled = enabled, modifier = modifier) { content() }
    } else {
        FilledTonalButton(onClick = onClick, enabled = enabled, modifier = modifier) { content() }
    }
}

/** The kind as offered in the form: "Book | Other". */
private fun DocumentKind.choiceRes(): Int = when (this) {
    DocumentKind.BOOK -> R.string.kind_book
    DocumentKind.DOCUMENT -> R.string.new_document_kind_other
}
