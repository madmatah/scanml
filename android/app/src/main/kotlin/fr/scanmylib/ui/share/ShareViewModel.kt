package fr.scanmylib.ui.share

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.db.DocumentEntity
import fr.scanmylib.library.LibraryRepository
import fr.scanmylib.ui.container
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

/** Choosing the document that receives photos shared from another app. */
class ShareViewModel(library: LibraryRepository) : ViewModel() {

    /** The documents, most recently changed first, as in the library; null until read. */
    val documents: StateFlow<List<DocumentEntity>?> = library.observeLibrary()
        .map { rows -> rows.map { it.document } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    companion object {
        val Factory = viewModelFactory {
            initializer { ShareViewModel(this.container.library) }
        }
    }
}
