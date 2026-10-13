package fr.scanmylib.sync

import androidx.work.ExistingWorkPolicy
import androidx.work.WorkInfo.State
import fr.scanmylib.api.ApiException
import fr.scanmylib.db.UploadFailure
import java.io.IOException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UploadPolicyTest {

    @Test
    fun `starts a run right away when none is running`() {
        assertEquals(ExistingWorkPolicy.REPLACE, enqueuePolicy(emptyList()))
        assertEquals(ExistingWorkPolicy.REPLACE, enqueuePolicy(listOf(State.SUCCEEDED)))
        assertEquals(ExistingWorkPolicy.REPLACE, enqueuePolicy(listOf(State.FAILED, State.FAILED)))
        // Waiting for the network or for a backoff delay: start over without the delay.
        assertEquals(ExistingWorkPolicy.REPLACE, enqueuePolicy(listOf(State.ENQUEUED)))
    }

    @Test
    fun `queues one follow-up run behind a running one`() {
        assertEquals(ExistingWorkPolicy.APPEND_OR_REPLACE, enqueuePolicy(listOf(State.RUNNING)))
        assertNull(enqueuePolicy(listOf(State.RUNNING, State.BLOCKED)))
        assertNull(enqueuePolicy(listOf(State.RUNNING, State.ENQUEUED)))
    }

    @Test
    fun `classifies upload errors`() {
        assertEquals(UploadFailure.NETWORK, uploadFailureOf(ApiException.Unreachable(IOException("timeout"))))
        assertEquals(UploadFailure.SERVER_ERROR, uploadFailureOf(ApiException.InvalidResponse(IllegalArgumentException())))
        assertEquals(UploadFailure.UNAUTHORIZED, uploadFailureOf(ApiException.Unauthorized()))
        assertEquals(UploadFailure.DOCUMENT_MISSING, uploadFailureOf(ApiException.Http(404, "unknown document")))
        assertEquals(UploadFailure.TOO_LARGE, uploadFailureOf(ApiException.Http(413, null)))
        assertEquals(UploadFailure.UNSUPPORTED_TYPE, uploadFailureOf(ApiException.Http(415, null)))
        assertEquals(UploadFailure.REJECTED, uploadFailureOf(ApiException.Http(422, "page_id")))
        assertEquals(UploadFailure.SERVER_ERROR, uploadFailureOf(ApiException.Http(429, null)))
        assertEquals(UploadFailure.SERVER_ERROR, uploadFailureOf(ApiException.Http(503, null)))
    }

    @Test
    fun `only transient failures are retried automatically`() {
        assertTrue(UploadFailure.NETWORK.retryable)
        assertTrue(UploadFailure.SERVER_ERROR.retryable)
        assertTrue(UploadFailure.UNAUTHORIZED.retryable)
        assertFalse(UploadFailure.TOO_LARGE.retryable)
        assertFalse(UploadFailure.REJECTED.retryable)
        assertFalse(UploadFailure.FILE_MISSING.retryable)
    }
}
