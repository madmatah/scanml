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
    class TheImportantProperty {
        @RunWith(Parameterized::class)
        class WhenTheMessageIsAboutPagesLeftOutOrLost(private val case: String, private val message: DocumentMessage) {
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
                    arrayOf(
                        "photos skipped",
                        DocumentMessage.PhotosSkipped(unsupported = 1, tooLarge = 0, unreadable = 2),
                    ),
                    arrayOf("adding interrupted", DocumentMessage.AddingInterrupted),
                    arrayOf("storage full", DocumentMessage.StorageFull),
                    arrayOf("send failed", DocumentMessage.SendFailed),
                )
            }
        }

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
                    arrayOf("pages queued", DocumentMessage.PagesQueued(4)),
                    arrayOf("PC unreachable", DocumentMessage.Unreachable),
                    arrayOf("page busy", DocumentMessage.PageBusy),
                )
            }
        }
    }
}
