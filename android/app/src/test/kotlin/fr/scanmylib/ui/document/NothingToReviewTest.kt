package fr.scanmylib.ui.document

import fr.scanmylib.library.Preparation
import fr.scanmylib.library.PreparationOutcome
import fr.scanmylib.library.StagedPage
import java.io.File
import java.time.Instant
import kotlin.properties.Delegates
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class NothingToReviewTest {
    @RunWith(Enclosed::class)
    class TheHasNothingToReviewProperty {
        class WhenTheRunIsReadAndEmptyWithNothingOnItsWay {
            private var hasNothingToReview by Delegates.notNull<Boolean>()

            @Before
            fun weighTheRun() {
                hasNothingToReview = EMPTY_RUN.hasNothingToReview
            }

            @Test
            fun `should let the review close itself`() {
                assertTrue(hasNothingToReview)
            }
        }

        @RunWith(Parameterized::class)
        class WhenSomethingIsLeftToReview(private val case: String, private val scan: ScanUiState) {
            private var hasNothingToReview by Delegates.notNull<Boolean>()

            @Before
            fun weighTheRun() {
                hasNothingToReview = scan.hasNothingToReview
            }

            @Test
            fun `should keep the review open`() {
                assertFalse(case, hasNothingToReview)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun runs(): List<Array<Any>> = listOf(
                    arrayOf("the run is not read yet", EMPTY_RUN.copy(isRunRead = false)),
                    arrayOf("a page is left", EMPTY_RUN.copy(stagedPages = listOf(PAGE))),
                    arrayOf(
                        "images are on their way to the run",
                        EMPTY_RUN.copy(
                            preparation = Preparation(done = 0, total = 2, imagesToAdd = 2, isCancellable = true),
                        ),
                    ),
                    arrayOf(
                        "how the copies ended waits to be read",
                        EMPTY_RUN.copy(outcome = PreparationOutcome.ImportFailed),
                    ),
                    arrayOf("the run is being sent", EMPTY_RUN.copy(sending = true)),
                    arrayOf("the review has already ended", EMPTY_RUN.copy(reviewEnd = ReviewEnd.PagesSent(count = 2))),
                    arrayOf("the removal of the last page can still be undone", EMPTY_RUN.copy(removedPage = PAGE)),
                    arrayOf("a source of pages is open and has not returned", EMPTY_RUN.copy(isSourceOpen = true)),
                )
            }
        }
    }
}

private val EMPTY_RUN = ScanUiState(loaded = true, isRunRead = true)

private val PAGE = StagedPage(File("/staging/run/1.jpg"), seq = 1, capturedAt = Instant.EPOCH)
