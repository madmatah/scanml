@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.document

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import fr.scanmylib.R
import fr.scanmylib.library.MAX_PAGE_NUMBER
import fr.scanmylib.library.PageNumberInput
import fr.scanmylib.library.PageNumbering
import fr.scanmylib.library.findNextPages
import fr.scanmylib.library.hintPages
import fr.scanmylib.library.readPageNumber
import fr.scanmylib.library.renumberPage
import fr.scanmylib.library.suggestPageNumber
import fr.scanmylib.ui.components.SettingSwitchRow
import kotlinx.coroutines.launch

/** [onDone] runs once the sheet has slid away, so that the tile behind it can take the focus back. */
@Composable
fun PageNumberSheet(
    numberings: List<PageNumbering>,
    index: Int,
    scannedPages: List<IntRange>,
    onDone: (number: Int?, nextPagesFollowOn: Boolean) -> Unit,
    onDismiss: () -> Unit,
) {
    val hints = hintPages(numberings)
    val currentNumber = hints[index].number
    // With the cursor after the number, so that typing goes on from it.
    var field by rememberSaveable(stateSaver = TextFieldValue.Saver) {
        val text = currentNumber?.toString().orEmpty()
        mutableStateOf(TextFieldValue(text, TextRange(text.length)))
    }
    var nextPagesFollowOn by rememberSaveable {
        mutableStateOf((numberings[index] as? PageNumbering.Given)?.nextPagesFollowOn ?: true)
    }
    val input = readPageNumber(field.text)
    val number = (input as? PageNumberInput.Valid)?.number
    val isValid = input != PageNumberInput.Invalid
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    val finish = { chosenNumber: Int? ->
        scope.launch { sheetState.hide() }.invokeOnCompletion { onDone(chosenNumber, nextPagesFollowOn) }
    }
    val focusRequester = remember { FocusRequester() }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        LaunchedEffect(Unit) {
            // Once the field is laid out in the sheet's own window, so that it can take the focus.
            withFrameNanos {}
            focusRequester.requestFocus()
        }
        Column(
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(start = 24.dp, end = 24.dp, bottom = 16.dp),
        ) {
            Text(
                stringResource(R.string.number_sheet_title, index + 1),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.semantics { heading() },
            )
            OutlinedTextField(
                value = field,
                onValueChange = { typed ->
                    val digits = typed.text.filter(Char::isDigit).take(MAX_PAGE_NUMBER_DIGITS)
                    field = if (digits == typed.text) typed else TextFieldValue(digits, TextRange(digits.length))
                },
                label = { Text(stringResource(R.string.number_sheet_field)) },
                isError = !isValid,
                supportingText = {
                    Text(
                        if (isValid) {
                            stringResource(R.string.number_sheet_help)
                        } else {
                            stringResource(R.string.page_number_invalid, MAX_PAGE_NUMBER)
                        },
                    )
                },
                textStyle = MaterialTheme.typography.headlineSmall.copy(fontFeatureSettings = TABULAR_FIGURES),
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { if (isValid) finish(number) }),
                modifier = Modifier
                    .fillMaxWidth()
                    .focusRequester(focusRequester),
            )
            val suggestion = suggestPageNumber(index, hints, scannedPages)
            if (field.text.isEmpty() && suggestion != null) {
                val suggestionText = suggestion.toString()
                AssistChip(
                    onClick = { field = TextFieldValue(suggestionText, TextRange(suggestionText.length)) },
                    label = { Text(stringResource(R.string.number_sheet_suggestion, suggestion)) },
                )
            }
            SettingSwitchRow(
                label = stringResource(R.string.number_sheet_next_pages),
                checked = nextPagesFollowOn,
                onCheckedChange = { nextPagesFollowOn = it },
                description = if (isValid) describeNextPages(numberings, index, number, nextPagesFollowOn) else null,
                enabled = number != null,
                contentPadding = PaddingValues(),
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End),
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (currentNumber != null) {
                    TextButton(onClick = { finish(null) }) { Text(stringResource(R.string.number_sheet_clear)) }
                }
                Button(onClick = { finish(number) }, enabled = isValid) {
                    Text(stringResource(R.string.number_sheet_done))
                }
            }
        }
    }
}

@Composable
private fun describeNextPages(
    numberings: List<PageNumbering>,
    index: Int,
    number: Int?,
    nextPagesFollowOn: Boolean,
): String? {
    val nextPages = findNextPages(numberings, index)
    if (nextPages.isEmpty()) return null
    val hints = hintPages(renumberPage(numberings, index, number, nextPagesFollowOn))
    val numbered = nextPages.mapNotNull { page -> hints[page].number?.let { page to it } }
    val unnumbered = nextPages.filter { hints[it].number == null }
    val numberedLine = when (numbered.size) {
        0 -> null

        1 -> stringResource(R.string.number_sheet_next_pages_range_one, numbered[0].first + 1, numbered[0].second)

        else -> stringResource(
            R.string.number_sheet_next_pages_range,
            numbered.first().first + 1,
            numbered.last().first + 1,
            numbered.first().second,
            numbered.last().second,
        )
    }
    val unnumberedLine = when (unnumbered.size) {
        0 -> null
        1 -> stringResource(R.string.number_sheet_next_pages_auto_one, unnumbered[0] + 1)
        else -> stringResource(R.string.number_sheet_next_pages_auto, unnumbered.first() + 1, unnumbered.last() + 1)
    }
    return listOfNotNull(numberedLine, unnumberedLine).joinToString("\n")
}

private val MAX_PAGE_NUMBER_DIGITS = MAX_PAGE_NUMBER.toString().length
