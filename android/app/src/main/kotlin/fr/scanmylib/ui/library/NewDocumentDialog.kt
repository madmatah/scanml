package fr.scanmylib.ui.library

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.ui.components.labelRes

@Composable
fun NewDocumentDialog(onDismiss: () -> Unit, onCreate: (NewDocument) -> Unit) {
    var title by rememberSaveable { mutableStateOf("") }
    var author by rememberSaveable { mutableStateOf("") }
    var kind by rememberSaveable { mutableStateOf(DocumentKind.BOOK) }
    // Books default to unwarping (curved pages near the binding), other kinds do not,
    // until the user flips the switch themselves.
    var unwarp by rememberSaveable { mutableStateOf(true) }
    var unwarpTouched by rememberSaveable { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.new_document_title)) },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp),
                modifier = Modifier.verticalScroll(rememberScrollState()),
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
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = author,
                    onValueChange = { author = NewDocument.fieldText(it) },
                    label = { Text(stringResource(R.string.new_document_author)) },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Words),
                    modifier = Modifier.fillMaxWidth(),
                )
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    DocumentKind.entries.forEachIndexed { index, option ->
                        SegmentedButton(
                            selected = kind == option,
                            onClick = {
                                kind = option
                                if (!unwarpTouched) unwarp = option == DocumentKind.BOOK
                            },
                            shape = SegmentedButtonDefaults.itemShape(index, DocumentKind.entries.size),
                        ) {
                            Text(stringResource(option.labelRes()))
                        }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(stringResource(R.string.new_document_unwarp))
                        Text(
                            stringResource(R.string.new_document_unwarp_help),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Switch(
                        checked = unwarp,
                        onCheckedChange = {
                            unwarp = it
                            unwarpTouched = true
                        },
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onCreate(NewDocument(title.trim(), author.trim(), kind, unwarp)) },
                enabled = title.isNotBlank(),
            ) {
                Text(stringResource(R.string.new_document_create))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) }
        },
    )
}
