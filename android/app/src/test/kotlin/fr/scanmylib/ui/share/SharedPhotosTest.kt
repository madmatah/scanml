package fr.scanmylib.ui.share

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SharedPhotosTest {

    private val app = "fr.scanmylib.dev"

    @Test
    fun `photos shared by another app's provider are read`() {
        assertTrue(isReadableShare("content", "media", app))
        assertTrue(isReadableShare("content", "com.example.gallery.provider", app))
        // Another app whose name starts like this one's.
        assertTrue(isReadableShare("content", "fr.scanmylib.devices", app))
    }

    @Test
    fun `files and this app's own providers are never read`() {
        assertFalse(isReadableShare("file", null, app))
        assertFalse(isReadableShare("file", "", app))
        assertFalse(isReadableShare("content", app, app))
        assertFalse(isReadableShare("content", "$app.androidx-startup", app))
        assertFalse(isReadableShare("content", null, app))
        assertFalse(isReadableShare("http", "example.invalid", app))
        assertFalse(isReadableShare(null, "media", app))
        // The content resolver drops a user part: "0@" would reach this app's own provider.
        assertFalse(isReadableShare("content", "0@$app.androidx-startup", app))
        assertFalse(isReadableShare("content", "0@media", app))
        assertFalse(isReadableShare("content", "media:1", app))
    }
}
