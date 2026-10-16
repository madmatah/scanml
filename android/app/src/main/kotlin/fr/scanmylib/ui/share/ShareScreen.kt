@file:OptIn(ExperimentalMaterial3Api::class)

package fr.scanmylib.ui.share

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import fr.scanmylib.R
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.ui.components.iconRes
import fr.scanmylib.ui.components.labelRes
import fr.scanmylib.ui.library.NewDocumentDialog

/**
 * "Add to…": photos shared from another app, [photoCount] of them, wait for the user to choose
 * the document they join ([onChoose]), or a new one. Closing ([onClose]) imports nothing.
 */
@Composable
fun ShareScreen(
    photoCount: Int,
    onChoose: (documentId: String) -> Unit,
    onClose: () -> Unit,
    viewModel: ShareViewModel = viewModel(factory = ShareViewModel.Factory),
) {
    val documents by viewModel.documents.collectAsStateWithLifecycle()
    val currentOnChoose by rememberUpdatedState(onChoose)
    LaunchedEffect(viewModel) {
        viewModel.documentsToOpen.collect { currentOnChoose(it) }
    }
    var creatingDocument by rememberSaveable { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.share_title)) },
                navigationIcon = {
                    IconButton(onClick = onClose) {
                        Icon(painterResource(R.drawable.ic_close), contentDescription = stringResource(R.string.close))
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            contentPadding = PaddingValues(bottom = 16.dp),
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            item(key = "count") {
                Text(
                    if (photoCount > 0) {
                        pluralStringResource(R.plurals.share_photos, photoCount, photoCount)
                    } else {
                        stringResource(R.string.share_nothing)
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                )
            }
            if (photoCount > 0) {
                item(key = "new") {
                    ListItem(
                        headlineContent = { Text(stringResource(R.string.new_document_title)) },
                        leadingContent = { Icon(painterResource(R.drawable.ic_add), contentDescription = null) },
                        modifier = Modifier.clickable(role = Role.Button) { creatingDocument = true },
                    )
                    HorizontalDivider()
                }
                items(documents.orEmpty(), key = { it.id }) { document ->
                    DocumentRow(document, onClick = { onChoose(document.id) })
                }
            }
        }
    }

    if (creatingDocument) {
        NewDocumentDialog(
            onDismiss = { creatingDocument = false },
            onCreate = {
                creatingDocument = false
                viewModel.createDocument(it)
            },
        )
    }
}

@Composable
private fun DocumentRow(document: DocumentEntity, onClick: () -> Unit) {
    val kind = stringResource(document.kind.labelRes())
    ListItem(
        headlineContent = { Text(document.title, maxLines = 2, overflow = TextOverflow.Ellipsis) },
        supportingContent = { Text(document.author.ifEmpty { kind }, maxLines = 1, overflow = TextOverflow.Ellipsis) },
        leadingContent = { Icon(painterResource(document.kind.iconRes()), contentDescription = null) },
        modifier = Modifier.clickable(
            role = Role.Button,
            onClickLabel = stringResource(R.string.share_add_here),
            onClick = onClick,
        ),
    )
}
