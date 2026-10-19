package fr.scanmylib.update

import java.io.File
import java.io.FilterInputStream
import java.io.IOException
import java.io.InputStream
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import javax.net.SocketFactory
import kotlin.concurrent.thread
import kotlin.properties.Delegates
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.Call
import okhttp3.EventListener
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.BeforeClass
import org.junit.ClassRule
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class ApkDownloadTest {
    @RunWith(Enclosed::class)
    class TheDownloadApkFunction {
        class WhenThePcSendsTheApkAnnounced {
            @Test
            fun `should report the digest and the size of what it received`() {
                assertEquals(ApkDownload(computeSha256(apkContent), apkContent.size.toLong()), download)
            }

            @Test
            fun `should report the bytes received, up to the whole APK`() {
                assertEquals(apkContent.size.toLong(), progressBytes.last())
            }

            @Test
            fun `should write the APK to the file`() {
                assertEquals(apkContent.toList(), fileContent)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private val apkContent = ByteArray(3000) { (it % 251).toByte() }

                private lateinit var download: ApkDownload
                private lateinit var progressBytes: List<Long>
                private lateinit var fileContent: List<Byte>

                @BeforeClass
                @JvmStatic
                fun downloadTheApk() = runTest {
                    MockWebServer().use { server ->
                        server.enqueue(MockResponse.Builder().body(Buffer().write(apkContent)).build())
                        server.start()
                        val file = File(folder.root, "updates/scanmylib.apk")
                        val reportedBytes = mutableListOf<Long>()
                        val update = UPDATE.copy(size = apkContent.size.toLong(), url = server.url(DOWNLOAD_PATH))
                        download = downloadApk(OkHttpClient(), update, file) { reportedBytes += it }
                        progressBytes = reportedBytes.toList()
                        fileContent = file.readBytes().toList()
                    }
                }
            }
        }

        class WhenThePcSendsMoreThanAnnounced {
            @Test
            fun `should stop at the first read past the announced size, far from the end of the body`() {
                assertTrue("received $receivedBytes", receivedBytes in 3001..3000 + 64 * 1024)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private var receivedBytes: Long by Delegates.notNull()

                @BeforeClass
                @JvmStatic
                fun downloadTheApk() = runTest {
                    MockWebServer().use { server ->
                        server.enqueue(MockResponse.Builder().body(Buffer().write(ByteArray(1024 * 1024))).build())
                        server.start()
                        val file = File(folder.root, "updates/scanmylib.apk")
                        val update = UPDATE.copy(size = 3000, url = server.url(DOWNLOAD_PATH))
                        receivedBytes = downloadApk(OkHttpClient(), update, file) {}.size
                    }
                }
            }
        }

        class WhenThePcAnswersWithAnError {
            @get:Rule
            val folder = TemporaryFolder()

            private val server = MockWebServer()
            private lateinit var url: HttpUrl
            private lateinit var downloadTheApk: suspend () -> ApkDownload

            @Before
            fun keepTheDownload() {
                server.enqueue(MockResponse.Builder().code(404).build())
                server.start()
                url = server.url(DOWNLOAD_PATH)
                val file = File(folder.root, "updates/scanmylib.apk")
                downloadTheApk = { downloadApk(OkHttpClient(), UPDATE.copy(url = url), file) {} }
            }

            @After
            fun stopThePc() {
                server.close()
            }

            @Test
            fun `should fail, saying the PC's answer`() = runTest {
                val failure = runCatching { downloadTheApk() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertEquals("HTTP 404 for $url", failure?.message)
            }
        }

        class WhenThePcRedirects {
            @get:Rule
            val folder = TemporaryFolder()

            private val server = MockWebServer()
            private lateinit var url: HttpUrl
            private lateinit var downloadTheApk: suspend () -> ApkDownload

            @Before
            fun keepTheDownload() {
                redirectTheDownload(server)
                url = server.url(DOWNLOAD_PATH)
                val file = File(folder.root, "updates/scanmylib.apk")
                downloadTheApk = { downloadApk(OkHttpClient(), UPDATE.copy(url = url), file) {} }
            }

            @After
            fun stopThePc() {
                server.close()
            }

            @Test
            fun `should fail, since the APK comes from the paired PC only`() = runTest {
                val failure = runCatching { downloadTheApk() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertEquals("HTTP 302 for $url", failure?.message)
            }
        }

        class WhenThePcRedirectsAndTheDownloadIsOver {
            @Test
            fun `should not follow the redirect`() {
                assertEquals(1, requestCount)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private var requestCount: Int by Delegates.notNull()

                @BeforeClass
                @JvmStatic
                fun downloadTheApk() = runTest {
                    MockWebServer().use { server ->
                        redirectTheDownload(server)
                        val file = File(folder.root, "updates/scanmylib.apk")
                        val update = UPDATE.copy(url = server.url(DOWNLOAD_PATH))
                        runCatching { downloadApk(OkHttpClient(), update, file) {} }
                        requestCount = server.requestCount
                    }
                }
            }
        }

        class WhenTheDownloadIsCanceledDuringAStalledRead {
            @Test
            fun `should end as canceled, not as a failure`() {
                assertTrue("${ending.failure}", ending.failure is CancellationException)
            }

            @Test
            fun `should be canceled in the read that waits for the rest, not before the download started`() {
                assertEquals(1L, receivedBytes)
            }

            @Test
            fun `should end the stalled read by canceling its call at once, not by waiting for the read's timeout`() {
                assertEquals(true, stalledRead.wasCallCanceledWhenItEnded)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private var receivedBytes: Long by Delegates.notNull()
                private lateinit var ending: DownloadEnding
                private lateinit var stalledRead: StalledRead

                @BeforeClass
                @JvmStatic
                fun cancelTheDownloadDuringAStalledRead() = runTest {
                    ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { listener ->
                        val pc = serveTheFirstByteThenStall(listener)
                        val calls = CallRecorder()
                        val sockets = StallWatchingSockets(calls::isCanceled)
                        val http = OkHttpClient.Builder().socketFactory(sockets).eventListener(calls).build()
                        val url = "http://127.0.0.1:${listener.localPort}$DOWNLOAD_PATH".toHttpUrl()
                        val file = File(folder.root, "updates/stalled.apk")
                        var receivedBytesSoFar = 0L
                        var thrown: Throwable? = null
                        val download = launch(Dispatchers.Default) {
                            try {
                                downloadApk(http, UPDATE.copy(size = 100, url = url), file) {
                                    receivedBytesSoFar = it
                                    sockets.hasFirstByte = true
                                }
                            } catch (e: Throwable) {
                                thrown = e
                                throw e
                            }
                        }
                        sockets.readingTheRest.await()
                        download.cancelAndJoin()
                        pc.join()
                        receivedBytes = receivedBytesSoFar
                        ending = DownloadEnding(thrown)
                        stalledRead = StalledRead(sockets.wasCallCanceledWhenTheReadEnded)
                    }
                }
            }
        }
    }
}

private const val DOWNLOAD_PATH = "/download/scanmylib.apk"
private val UPDATE = AvailableUpdate("0.8.0", 800, "ab".repeat(32), 1234, "http://192.168.1.10:8770/".toHttpUrl())

/** What a download threw, if anything, held in a non-null value so that a test fails when no hook ran. */
private data class DownloadEnding(val failure: Throwable?)

/** Whether the call was canceled when the stalled read ended, null if it never ended, held as [DownloadEnding] is. */
private data class StalledRead(val wasCallCanceledWhenItEnded: Boolean?)

private class CallRecorder : EventListener() {
    @Volatile private var call: Call? = null

    fun isCanceled(): Boolean = call?.isCanceled() == true

    override fun callStart(call: Call) {
        this.call = call
    }
}

/**
 * The IOException that ends the stalled read cannot tell a cancel from a read timeout, which also
 * ends it on a call that nothing canceled, whether OkHttp's socket timeout or Okio's watchdog ends it.
 */
private class StallWatchingSockets(private val isCallCanceled: () -> Boolean) : SocketFactory() {
    @Volatile var hasFirstByte = false

    @Volatile var wasCallCanceledWhenTheReadEnded: Boolean? = null

    val readingTheRest = CompletableDeferred<Unit>()

    override fun createSocket(): Socket = object : Socket() {
        override fun getInputStream(): InputStream {
            val input = super.getInputStream()
            return object : FilterInputStream(input) {
                override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
                    if (!hasFirstByte) return super.read(buffer, offset, length)
                    readingTheRest.complete(Unit)
                    try {
                        return super.read(buffer, offset, length)
                    } catch (e: IOException) {
                        wasCallCanceledWhenTheReadEnded = isCallCanceled()
                        throw e
                    }
                }
            }
        }
    }

    override fun createSocket(host: String, port: Int): Socket = throw UnsupportedOperationException(OKHTTP_CONNECTS)

    override fun createSocket(host: String, port: Int, localHost: InetAddress, localPort: Int): Socket =
        throw UnsupportedOperationException(OKHTTP_CONNECTS)

    override fun createSocket(host: InetAddress, port: Int): Socket =
        throw UnsupportedOperationException(OKHTTP_CONNECTS)

    override fun createSocket(address: InetAddress, port: Int, localAddress: InetAddress, localPort: Int): Socket =
        throw UnsupportedOperationException(OKHTTP_CONNECTS)

    private companion object {
        const val OKHTTP_CONNECTS = "OkHttp creates an unconnected socket, then connects it"
    }
}

private fun serveTheFirstByteThenStall(listener: ServerSocket): Thread = thread(isDaemon = true) {
    listener.accept().use { socket ->
        val headersAndFirstByte = "HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nA"
        socket.getOutputStream().write(headersAndFirstByte.toByteArray())
        socket.getOutputStream().flush()
        runCatching { socket.getInputStream().readBytes() }
    }
}

private fun redirectTheDownload(server: MockWebServer) {
    server.enqueue(MockResponse.Builder().code(302).addHeader("Location", "/download/other.apk").build())
    server.enqueue(MockResponse.Builder().body(Buffer().write(ByteArray(1234))).build())
    server.start()
}

private fun computeSha256(bytes: ByteArray) =
    MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
