package fr.scanmylib.sync

import fr.scanmylib.api.ApiException
import fr.scanmylib.db.UploadFailure
import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class UploadFailureTest {
    @RunWith(Enclosed::class)
    class TheUploadFailureOfFunction {
        @RunWith(Parameterized::class)
        class WhenGivenAnErrorOfTheApi(
            private val case: String,
            private val exception: ApiException,
            private val expected: UploadFailure,
        ) {
            private lateinit var failure: UploadFailure

            @Before
            fun classifyTheError() {
                failure = uploadFailureOf(exception)
            }

            @Test
            fun `should classify it for the upload queue`() {
                assertEquals(case, expected, failure)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun errors(): List<Array<Any>> = listOf(
                    arrayOf(
                        "an unreachable server: the network",
                        ApiException.Unreachable(IOException("timeout")),
                        UploadFailure.NETWORK,
                    ),
                    arrayOf(
                        "an unexpected answer: a server error",
                        ApiException.InvalidResponse(IllegalArgumentException()),
                        UploadFailure.SERVER_ERROR,
                    ),
                    arrayOf("a refused token: unauthorized", ApiException.Unauthorized(), UploadFailure.UNAUTHORIZED),
                    arrayOf(
                        "HTTP 404: the document missing",
                        ApiException.Http(404, "unknown document"),
                        UploadFailure.DOCUMENT_MISSING,
                    ),
                    arrayOf("HTTP 413: too large", ApiException.Http(413, null), UploadFailure.TOO_LARGE),
                    arrayOf(
                        "HTTP 415: an unsupported type",
                        ApiException.Http(415, null),
                        UploadFailure.UNSUPPORTED_TYPE,
                    ),
                    arrayOf("HTTP 422: rejected", ApiException.Http(422, "page_id"), UploadFailure.REJECTED),
                    arrayOf("HTTP 429: a server error", ApiException.Http(429, null), UploadFailure.SERVER_ERROR),
                    arrayOf("HTTP 503: a server error", ApiException.Http(503, null), UploadFailure.SERVER_ERROR),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheRetryableProperty {
        @RunWith(Parameterized::class)
        class WhenTheFailureIsTransient(private val failure: UploadFailure) {
            @Test
            fun `should be retried automatically`() {
                assertTrue(failure.retryable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun failures(): List<Array<Any>> =
                    UploadFailure.entries.filter { it in TRANSIENT_FAILURES }.map { arrayOf(it) }
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheFailureIsFinal(private val failure: UploadFailure) {
            @Test
            fun `should not be retried automatically`() {
                assertFalse(failure.retryable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun failures(): List<Array<Any>> =
                    UploadFailure.entries.filterNot { it in TRANSIENT_FAILURES }.map { arrayOf(it) }
            }
        }
    }
}

private val TRANSIENT_FAILURES = setOf(UploadFailure.NETWORK, UploadFailure.SERVER_ERROR, UploadFailure.UNAUTHORIZED)
