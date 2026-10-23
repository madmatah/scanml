package fr.scanmylib.library

import android.database.sqlite.SQLiteFullException

/** Whether [this] failed because the phone's storage is full (files or database). */
internal fun Throwable.isStorageFull(): Boolean = generateSequence(this) { it.cause }.take(MAX_CAUSES).any {
    it is SQLiteFullException || it.message?.contains("ENOSPC") == true
}

private const val MAX_CAUSES = 10

/**
 * Whether [freeBytes] is too little for Google's scanner to hand its pages over: it writes each
 * page, a few megabytes, before returning them, and then the app copies them.
 */
internal fun isStorageLow(freeBytes: Long): Boolean = freeBytes < LOW_STORAGE_BYTES

private const val LOW_STORAGE_BYTES = 100L * 1024 * 1024
