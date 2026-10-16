package fr.scanmylib.ui.library

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import fr.scanmylib.model.DocumentKind
import fr.scanmylib.ui.container
import fr.scanmylib.ui.document.isStorageFull
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

/** What opens once the new document is created. */
enum class AfterCreate {
    /** Its default camera. */
    SCAN,

    /** The photo picker. */
    IMPORT,

    /** Nothing more: the photos shared with the app join it. */
    ADD_SHARED,
}

data class NewDocumentState(
    /** The document is being created: the buttons wait. */
    val creating: Boolean = false,
    /** The last attempt failed, because the storage is full or for another reason. */
    val failure: CreateFailure? = null,
)

enum class CreateFailure { STORAGE_FULL, OTHER }

/**
 * The "new document" form. The document is created on the phone, so that it works with the PC
 * off; the PC gets it with its first upload.
 */
class NewDocumentViewModel(private val createDocument: suspend (NewDocument) -> String) : ViewModel() {

    private val mutableState = MutableStateFlow(NewDocumentState())
    private val createdChannel = Channel<Pair<String, AfterCreate>>(Channel.BUFFERED)

    val state: StateFlow<NewDocumentState> = mutableState.asStateFlow()

    /** The id of each document created, with what opens next. */
    val created: Flow<Pair<String, AfterCreate>> = createdChannel.receiveAsFlow()

    /** Creates [document], then emits [created]; on failure, the form stays as it was, to try again. */
    fun create(document: NewDocument, then: AfterCreate) {
        if (mutableState.value.creating) return
        mutableState.value = NewDocumentState(creating = true)
        viewModelScope.launch {
            val id = try {
                createDocument(document)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // The database: full, closed...
                Log.e(TAG, "document not created", e)
                mutableState.value = NewDocumentState(
                    failure = if (e.isStorageFull()) CreateFailure.STORAGE_FULL else CreateFailure.OTHER,
                )
                return@launch
            }
            // Still creating: the screen leaves for the document.
            createdChannel.send(id to then)
        }
    }

    companion object {
        private const val TAG = "NewDocument"

        val Factory = viewModelFactory {
            initializer {
                val library = this.container.library
                NewDocumentViewModel { library.createDocument(it.title, it.author, it.kind, it.unwarp) }
            }
        }
    }
}

/**
 * Whether curved pages are flattened once the kind becomes [kind]: on for a book, off for anything
 * else, until the user sets it themselves ([touched]); then their [current] choice stays.
 */
fun unwarpForKind(kind: DocumentKind, current: Boolean, touched: Boolean): Boolean =
    if (touched) current else kind == DocumentKind.BOOK
