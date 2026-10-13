package fr.scanmylib.library

import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream

/**
 * App-private directory holding scanned images until they are uploaded (or as kept local
 * copies). Images are named after their page id.
 */
class ScanFileStore(private val directory: File) {

    fun file(fileName: String): File = File(directory, fileName)

    /**
     * Stores [source] (closed afterwards) as the image of page [pageId] and returns its file name.
     * The file is synced to disk before it appears under its final name, so that a page recorded
     * in the database always has a complete image.
     */
    fun store(pageId: String, source: InputStream): String {
        directory.mkdirs()
        val fileName = fileName(pageId)
        val partial = File(directory, "$fileName.partial")
        try {
            source.use { input ->
                FileOutputStream(partial).use { output ->
                    input.copyTo(output)
                    output.fd.sync()
                }
            }
            if (partial.length() == 0L) throw IOException("empty image for page $pageId")
            if (!partial.renameTo(file(fileName))) throw IOException("cannot store $fileName")
        } finally {
            partial.delete() // nothing left to delete after a successful rename
        }
        return fileName
    }

    /**
     * Moves [source], a complete image on the same storage, into the store as the image of page
     * [pageId] and returns its file name.
     */
    fun adopt(pageId: String, source: File): String {
        directory.mkdirs()
        val fileName = fileName(pageId)
        if (!source.renameTo(file(fileName))) throw IOException("cannot move $source to the scan store")
        return fileName
    }

    fun delete(fileName: String) {
        file(fileName).delete()
    }

    /** Total size in bytes of the given files. */
    fun sizeOf(fileNames: Collection<String>): Long = fileNames.sumOf { file(it).length() }

    companion object {
        /** The name of the image of page [pageId] in the store. */
        fun fileName(pageId: String): String = "$pageId.jpg"
    }
}
