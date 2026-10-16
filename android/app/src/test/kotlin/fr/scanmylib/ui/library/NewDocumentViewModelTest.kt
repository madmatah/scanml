package fr.scanmylib.ui.library

import fr.scanmylib.model.DocumentKind
import java.io.IOException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class NewDocumentViewModelTest {

    private val book = NewDocument("Example Book", "Jane Doe", DocumentKind.BOOK, unwarp = true)

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `flattening follows the kind until the user sets it`() {
        assertTrue(unwarpForKind(DocumentKind.BOOK, current = false, touched = false))
        assertFalse(unwarpForKind(DocumentKind.DOCUMENT, current = true, touched = false))
        // Set by hand: the kind no longer changes it, for both kinds.
        assertTrue(unwarpForKind(DocumentKind.DOCUMENT, current = true, touched = true))
        assertFalse(unwarpForKind(DocumentKind.BOOK, current = false, touched = true))
    }

    @Test
    fun `the created document opens with the action chosen`() = runTest {
        val received = CompletableDeferred<NewDocument>()
        val viewModel = NewDocumentViewModel {
            received.complete(it)
            "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
        }
        viewModel.create(book, AfterCreate.IMPORT)
        assertEquals("6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b" to AfterCreate.IMPORT, viewModel.created.first())
        assertEquals(book, received.await())
    }

    @Test
    fun `a full storage is said, and the form can try again`() = runTest {
        var attempts = 0
        val viewModel = NewDocumentViewModel {
            attempts++
            if (attempts == 1) throw IOException("write failed: ENOSPC (No space left on device)")
            "0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d"
        }
        viewModel.create(book, AfterCreate.SCAN)
        assertEquals(NewDocumentState(failure = CreateFailure.STORAGE_FULL), viewModel.state.value)

        viewModel.create(book, AfterCreate.SCAN)
        assertEquals("0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d" to AfterCreate.SCAN, viewModel.created.first())
        assertEquals(2, attempts)
    }
}
