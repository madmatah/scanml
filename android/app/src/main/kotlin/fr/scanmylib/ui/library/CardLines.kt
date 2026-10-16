package fr.scanmylib.ui.library

import fr.scanmylib.db.LibraryRow

/** A line of a library card: a state of the document that differs from normal. */
sealed interface CardLine {
    /** Pages on the phone, waiting for the user to send them (the draft). */
    data class ToSend(val count: Int) : CardLine

    /** Uploads the PC refused for good. */
    data class Refused(val count: Int) : CardLine

    /** The PC refused the document itself. */
    data object DocumentRefused : CardLine

    /** Pages whose text the PC could not read. */
    data class ReadFailed(val count: Int) : CardLine

    /** Pages queued for upload, or uploading. */
    data class InTransit(val count: Int) : CardLine

    /** Pages on the PC, waiting to be read or being read. */
    data class BeingRead(val count: Int) : CardLine

    /** Created on the phone: the PC gets it with its first upload. */
    data object NotOnPcYet : CardLine
}

/**
 * The lines of [row]'s card, the ones that need the user first. Normal is no line: a document
 * whose pages are all read shows none. Pages waiting on the phone are never merged with pages
 * the PC reads, nor refused uploads with text that could not be read.
 */
fun cardLines(row: LibraryRow, stagedPages: Int): List<CardLine> = buildList {
    val document = row.document
    val server = document.server
    if (stagedPages > 0) add(CardLine.ToSend(stagedPages))
    if (row.failedPages > 0) add(CardLine.Refused(row.failedPages))
    if (document.uploadError != null) add(CardLine.DocumentRefused)
    if (server != null && server.errors > 0) add(CardLine.ReadFailed(server.errors))
    if (row.pagesToUpload > 0) add(CardLine.InTransit(row.pagesToUpload))
    val reading = server?.let { it.queued + it.processing } ?: 0
    if (reading > 0) add(CardLine.BeingRead(reading))
    if (server == null && document.uploadError == null) add(CardLine.NotOnPcYet)
}
