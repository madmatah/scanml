package fr.scanmylib.ui.share

import android.content.Intent
import android.net.Uri
import androidx.core.content.IntentCompat

/** Whether [this] shares something with the app ("Share" in the gallery or another app). */
val Intent.isShare: Boolean get() = action == Intent.ACTION_SEND || action == Intent.ACTION_SEND_MULTIPLE

/**
 * The photos shared by [this] intent, in their order, that the app may read: see [isReadableShare].
 * Their format is checked when they are imported, as for the photo picker.
 */
fun Intent.sharedPhotos(ownPackage: String): List<Uri> {
    val uris = when (action) {
        Intent.ACTION_SEND -> listOfNotNull(IntentCompat.getParcelableExtra(this, Intent.EXTRA_STREAM, Uri::class.java))

        Intent.ACTION_SEND_MULTIPLE ->
            IntentCompat.getParcelableArrayListExtra(this, Intent.EXTRA_STREAM, Uri::class.java).orEmpty()

        else -> emptyList()
    }
    return uris.filter { isReadableShare(it.scheme, it.authority, ownPackage) }
}

/**
 * Whether a shared item at [scheme]://[authority] may be read: only content offered by another
 * app's provider, with the access the share grants. A `file:` path, or a provider of this app,
 * would make the app read, then send to the PC, files that the sender cannot read itself, such
 * as the app's own private files. The authority must be a plain provider name: the content
 * resolver drops a user part ("0@") before finding the provider, so "0@<this app>" would pass a
 * comparison of the whole authority.
 */
fun isReadableShare(scheme: String?, authority: String?, ownPackage: String): Boolean = scheme == "content" &&
    authority != null &&
    PROVIDER_NAME.matches(authority) &&
    authority != ownPackage &&
    !authority.startsWith("$ownPackage.")

private val PROVIDER_NAME = Regex("[A-Za-z0-9_-]+(\\.[A-Za-z0-9_-]+)*")
