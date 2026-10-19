package fr.scanmylib.ui.library

import fr.scanmylib.MainDispatcherRule
import fr.scanmylib.model.DocumentKind
import java.io.IOException
import kotlin.properties.Delegates
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class NewDocumentViewModelTest {
    @RunWith(Enclosed::class)
    class TheUnwarpForKindFunction {
        @RunWith(Parameterized::class)
        class WhenTheUserHasNotSetIt(
            private val case: String,
            private val kind: DocumentKind,
            private val current: Boolean,
            private val expected: Boolean,
        ) {
            private var unwarp by Delegates.notNull<Boolean>()

            @Before
            fun changeTheKind() {
                unwarp = unwarpForKind(kind, current, touched = false)
            }

            @Test
            fun `should flatten the pages of a book only`() {
                assertEquals(case, expected, unwarp)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun changes(): List<Array<Any>> = listOf(
                    arrayOf("to a book, while off", DocumentKind.BOOK, false, true),
                    arrayOf("to a document, while on", DocumentKind.DOCUMENT, true, false),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheUserHasSetIt(
            private val case: String,
            private val kind: DocumentKind,
            private val current: Boolean,
        ) {
            private var unwarp by Delegates.notNull<Boolean>()

            @Before
            fun changeTheKind() {
                unwarp = unwarpForKind(kind, current, touched = true)
            }

            @Test
            fun `should keep the choice of the user, whatever the kind`() {
                assertEquals(case, current, unwarp)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun changes(): List<Array<Any>> = listOf(
                    arrayOf("to a document, while on", DocumentKind.DOCUMENT, true),
                    arrayOf("to a book, while off", DocumentKind.BOOK, false),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheCreateMethod {
        class WhenTheDocumentIsCreated {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            private lateinit var created: Pair<String, AfterCreate>
            private lateinit var createdDocument: NewDocument

            @Before
            fun createTheDocument() = runTest {
                val received = CompletableDeferred<NewDocument>()
                val viewModel = NewDocumentViewModel {
                    received.complete(it)
                    FIRST_DOCUMENT_ID
                }
                viewModel.create(BOOK, AfterCreate.IMPORT)
                created = viewModel.created.first()
                createdDocument = received.await()
            }

            @Test
            fun `should open it with the action chosen`() {
                assertEquals(FIRST_DOCUMENT_ID to AfterCreate.IMPORT, created)
            }

            @Test
            fun `should create the document of the form`() {
                assertEquals(BOOK, createdDocument)
            }
        }

        class WhenTheStorageIsFull {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            private lateinit var state: NewDocumentState

            @Before
            fun createTheDocument() = runTest {
                val creations = CreationsFailingFirst()
                val viewModel = NewDocumentViewModel(creations::create)
                createTheBook(viewModel)
                state = viewModel.state.value
            }

            @Test
            fun `should say that the storage is full`() {
                assertEquals(NewDocumentState(failure = CreateFailure.STORAGE_FULL), state)
            }
        }

        class WhenTheStorageWasFullAndTheFormTriesAgain {
            @get:Rule
            val mainDispatcher = MainDispatcherRule()

            private lateinit var created: Pair<String, AfterCreate>
            private var attemptCount by Delegates.notNull<Int>()

            @Before
            fun createTheDocumentAgain() = runTest {
                val creations = CreationsFailingFirst()
                val viewModel = NewDocumentViewModel(creations::create)
                createTheBook(viewModel)
                createTheBook(viewModel)
                created = viewModel.created.first()
                attemptCount = creations.attemptCount
            }

            @Test
            fun `should open the document created on the second attempt`() {
                assertEquals(SECOND_DOCUMENT_ID to AfterCreate.SCAN, created)
            }

            @Test
            fun `should have tried twice`() {
                assertEquals(2, attemptCount)
            }
        }
    }
}

private const val FIRST_DOCUMENT_ID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
private const val SECOND_DOCUMENT_ID = "0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d"
private val BOOK = NewDocument("Example Book", "Jane Doe", DocumentKind.BOOK, unwarp = true)

private class CreationsFailingFirst {
    private val attempts = mutableListOf<NewDocument>()

    val attemptCount: Int get() = attempts.size

    suspend fun create(document: NewDocument): String {
        attempts += document
        if (attempts.size == 1) throw IOException("write failed: ENOSPC (No space left on device)")
        return SECOND_DOCUMENT_ID
    }
}

private fun createTheBook(viewModel: NewDocumentViewModel) {
    viewModel.create(BOOK, AfterCreate.SCAN)
}
