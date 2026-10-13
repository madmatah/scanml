package fr.scanmylib.ui.document

import java.io.IOException
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StorageFullTest {

    @Test
    fun `a full storage is told apart from other failures`() {
        assertTrue(IOException("write failed: ENOSPC (No space left on device)").isStorageFull())
        assertTrue(IllegalStateException("could not copy", IOException("write failed: ENOSPC")).isStorageFull())
        assertFalse(IOException("read failed: EIO (I/O error)").isStorageFull())
        assertFalse(SecurityException().isStorageFull())
    }
}
