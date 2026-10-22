package fr.scanmylib.ui.document

import kotlin.properties.Delegates
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class MessageImportanceTest {
    @RunWith(Enclosed::class)
    class TheImportantPropertyOfAScanMessage {
        @RunWith(Parameterized::class)
        class WhenTheMessageIsAboutPagesLeftOutOrLost(private val case: String, private val message: ScanMessage) {
            private var isImportant by Delegates.notNull<Boolean>()

            @Before
            fun weighTheMessage() {
                isImportant = message.important
            }

            @Test
            fun `should show longer`() {
                assertTrue(case, isImportant)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun messages(): List<Array<Any>> = listOf(
                    arrayOf("adding interrupted", ScanMessage.AddingInterrupted),
                    arrayOf("storage full", ScanMessage.StorageFull),
                    arrayOf("send failed", ScanMessage.SendFailed),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheMessageIsRoutine(private val case: String, private val message: ScanMessage) {
            private var isImportant by Delegates.notNull<Boolean>()

            @Before
            fun weighTheMessage() {
                isImportant = message.important
            }

            @Test
            fun `should go away by itself`() {
                assertFalse(case, isImportant)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun messages(): List<Array<Any>> = listOf(arrayOf("pages queued", ScanMessage.PagesQueued(4)))
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheImportantPropertyOfADocumentMessage {
        @RunWith(Parameterized::class)
        class WhenTheMessageIsRoutine(private val case: String, private val message: DocumentMessage) {
            private var isImportant by Delegates.notNull<Boolean>()

            @Before
            fun weighTheMessage() {
                isImportant = message.important
            }

            @Test
            fun `should go away by itself`() {
                assertFalse(case, isImportant)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun messages(): List<Array<Any>> = listOf(
                    arrayOf("PC unreachable", DocumentMessage.Unreachable),
                    arrayOf("page busy", DocumentMessage.PageBusy),
                )
            }
        }
    }
}
