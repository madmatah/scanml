package fr.scanmylib.ui.document

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MessageImportanceTest {

    @Test
    fun `messages about pages left out or lost show longer`() {
        assertTrue(DocumentMessage.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 2).important)
        assertTrue(DocumentMessage.AddingInterrupted.important)
        assertTrue(DocumentMessage.StorageFull.important)
        assertTrue(DocumentMessage.SendFailed.important)
    }

    @Test
    fun `routine messages go away by themselves`() {
        assertFalse(DocumentMessage.PagesQueued(4).important)
        assertFalse(DocumentMessage.Unreachable.important)
        assertFalse(DocumentMessage.PageBusy.important)
    }
}
