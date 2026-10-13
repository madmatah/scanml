package fr.scanmylib.api

import fr.scanmylib.model.DocumentKind
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

// JSON models of the ScanMyLib API (docs/API.md), limited to the fields the app uses.

/**
 * JSON settings of the API client: fields added by newer servers are ignored, and unknown enum
 * values fall back to the property's default instead of failing the whole response.
 */
val ApiJson = Json {
    ignoreUnknownKeys = true
    coerceInputValues = true
}

/** Version of the API this app implements, compared with [Health.api]. */
const val SUPPORTED_API_VERSION = 1

/** `GET /api/health` */
@Serializable
data class Health(
    val name: String,
    val api: Int = 0,
)

/** `GET /api/status` */
@Serializable
data class ServerStatus(
    val version: String = "",
    val ocr: OcrStatus = OcrStatus(),
    val queue: QueueCounts = QueueCounts(),
)

@Serializable
data class OcrStatus(
    /** Engine state: `idle`, `starting`, `ready`, `stopping`, `error` or `unreachable`. */
    val state: String = "unreachable",
    @SerialName("last_error") val lastError: String? = null,
)

/** Pages waiting for OCR on the PC. */
@Serializable
data class QueueCounts(
    val queued: Int = 0,
    val processing: Int = 0,
)

/** `GET /api/documents` */
@Serializable
data class DocumentList(val documents: List<Document>)

@Serializable
data class Document(
    val id: String,
    val title: String,
    val author: String = "",
    val kind: DocumentKind = DocumentKind.DOCUMENT,
    val unwarp: Boolean = false,
    @SerialName("updated_at") val updatedAt: String? = null,
    val stats: DocumentStats = DocumentStats(),
    val coverage: Coverage = Coverage(),
    @SerialName("cover_thumb_url") val coverThumbUrl: String? = null,
    /** Folder of the document on the PC, for display only. */
    val folder: String = "",
)

@Serializable
data class DocumentStats(
    val pages: Int = 0,
    val done: Int = 0,
    val queued: Int = 0,
    val processing: Int = 0,
    val error: Int = 0,
    val excluded: Int = 0,
    val duplicates: Int = 0,
)

@Serializable
data class Coverage(
    /** Covered page numbers, e.g. "1–12, 45–60". */
    val label: String = "",
    /** Missing page ranges between the lowest and highest page, e.g. `[[13, 44]]`. */
    val gaps: List<List<Int>> = emptyList(),
    val unnumbered: Int = 0,
)

/** `GET /api/documents/{id}`: the document and its pages, in the server's display order. */
data class DocumentDetail(val document: Document, val pages: List<Page>)

/** The `pages` member of a [DocumentDetail] response. */
@Serializable
internal data class PageList(val pages: List<Page>)

/** Body of `PUT /api/documents/{id}`. */
@Serializable
data class DocumentUpsert(
    val title: String,
    val author: String,
    val kind: DocumentKind,
    val unwarp: Boolean,
)

@Serializable
data class Page(
    val id: String,
    @SerialName("document_id") val documentId: String,
    val status: PageStatus = PageStatus.UNKNOWN,
    val error: String? = null,
    /** Display label: "42", "xii", "42–43" for a spread, null if the page has no number. */
    @SerialName("page_label") val pageLabel: String? = null,
    @SerialName("number_source") val numberSource: NumberSource? = null,
    val excluded: Boolean = false,
    /** Id of the page that supersedes this one, when it is a duplicate. */
    @SerialName("duplicate_of") val duplicateOf: String? = null,
    @SerialName("thumb_url") val thumbUrl: String? = null,
)

/** OCR state of a page on the server. */
@Serializable
enum class PageStatus {
    @SerialName("queued")
    QUEUED,

    @SerialName("processing")
    PROCESSING,

    @SerialName("done")
    DONE,

    @SerialName("error")
    ERROR,

    /** A state introduced by a newer server. */
    @SerialName("unknown")
    UNKNOWN,
}

/** Where the effective page number comes from. */
@Serializable
enum class NumberSource {
    @SerialName("manual")
    MANUAL,

    @SerialName("detected")
    DETECTED,

    @SerialName("hint")
    HINT,

    @SerialName("inferred")
    INFERRED,
}
