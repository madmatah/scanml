package fr.scanmylib.ui.share

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.library.LibraryRepository
import fr.scanmylib.ui.container
import fr.scanmylib.ui.library.NewDocument
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** Choosing the document that receives photos shared from another app. */
class ShareViewModel(private val library: LibraryRepository) : ViewModel() {

    private val createdDocuments = Channel<String>(Channel.BUFFERED)

    /** The documents, most recently changed first, as in the library; null until read. */
    val documents: StateFlow<List<DocumentEntity>?> = library.observeLibrary()
        .map { rows -> rows.map { it.document } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Ids of documents just created, to import the photos into. */
    val documentsToOpen: Flow<String> = createdDocuments.receiveAsFlow()

    fun createDocument(document: NewDocument) {
        viewModelScope.launch {
            val id = library.createDocument(document.title, document.author, document.kind, document.unwarp)
            createdDocuments.send(id)
        }
    }

    companion object {
        val Factory = viewModelFactory {
            initializer { ShareViewModel(this.container.library) }
        }
    }
}
