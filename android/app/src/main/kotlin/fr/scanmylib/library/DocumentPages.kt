package fr.scanmylib.library

import fr.scanmylib.api.pageThumbUrl
import fr.scanmylib.db.PendingPageEntity
import fr.scanmylib.db.ServerPageEntity
import fr.scanmylib.db.UploadState

/**
 * The pages of a document as shown on its screen.
 *
 * @property local scans made on this phone that the server does not list yet: waiting,
 *   uploading, refused, or just uploaded.
 * @property server pages known by the server, in the server's order.
 */
data class DocumentPages(val local: List<PendingPageEntity>, val server: List<ServerPageEntity>) {
    val isEmpty: Boolean get() = local.isEmpty() && server.isEmpty()

    companion object {
        val EMPTY = DocumentPages(emptyList(), emptyList())

        /** Merges both sources; a page listed by the server is shown once, with the server's state. */
        fun merge(local: List<PendingPageEntity>, server: List<ServerPageEntity>): DocumentPages {
            val serverIds = server.mapTo(HashSet()) { it.id }
            return DocumentPages(local = local.filter { it.id !in serverIds }, server = server)
        }
    }
}

/**
 * The PC's thumbnail of a local page whose image is no longer on the phone: once uploaded, the
 * image is deleted (unless local copies are kept), and the page stays local until the server lists
 * it. Null while the phone has the image.
 */
fun PendingPageEntity.serverThumbUrl(): String? =
    if (state == UploadState.UPLOADED && fileName == null) pageThumbUrl(id) else null
