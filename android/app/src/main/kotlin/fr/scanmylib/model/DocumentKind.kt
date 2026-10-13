package fr.scanmylib.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Kind of a document, as named by the API. */
@Serializable
enum class DocumentKind {
    @SerialName("book")
    BOOK,

    @SerialName("document")
    DOCUMENT,
}
