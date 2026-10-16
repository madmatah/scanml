package fr.scanmylib.update

import fr.scanmylib.api.PublishedApk
import java.io.File
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.security.MessageDigest
import kotlin.concurrent.thread
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okio.Buffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class UpdateChecksTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val app = "fr.scanmylib.dev"
    private val pc = "http://192.168.1.10:8770/".toHttpUrl()
    private val sha256 = "ab".repeat(32)
    private val apk = PublishedApk(app, "0.8.0", 800, sha256, 1234, "/download/scanmylib.apk")

    @Test
    fun `a newer APK of this app is offered, downloaded from the paired PC`() {
        val update = offeredUpdate(pc, apk, app, installedVersionCode = 700)
        assertEquals(AvailableUpdate("0.8.0", 800, sha256, 1234, "http://192.168.1.10:8770/download/scanmylib.apk".toHttpUrl()), update)
    }

    @Test
    fun `nothing is offered for the same version, another app, or an odd path`() {
        assertNull(offeredUpdate(pc, null, app, 700))
        assertNull(offeredUpdate(pc, apk, app, 800))
        assertNull(offeredUpdate(pc, apk, app, 900))
        // The production app and the development app each check their own.
        assertNull(offeredUpdate(pc, apk, "fr.scanmylib", 700))
        assertNull(offeredUpdate(pc, apk.copy(path = "//example.invalid/scanmylib.apk"), app, 700))
        assertNull(offeredUpdate(pc, apk.copy(path = "/download/../api/documents"), app, 700))
        assertNull(offeredUpdate(pc, apk.copy(size = 0), app, 700))
    }

    @Test
    fun `nothing is offered with a version or a size the server would not announce`() {
        assertNotNull(offeredUpdate(pc, apk.copy(version = "123.45.67"), app, 700))
        for (version in listOf("0.8", "0.8.0.1", "0.8.0-beta", "1234.0.0", "0.100.0", "0.8.0\n", "ScanMyLib 0.8.0", "")) {
            assertNull(version, offeredUpdate(pc, apk.copy(version = version), app, 700))
        }
        assertNotNull(offeredUpdate(pc, apk.copy(size = MAX_APK_SIZE), app, 700))
        assertNull(offeredUpdate(pc, apk.copy(size = MAX_APK_SIZE + 1), app, 700))
        assertNull(offeredUpdate(pc, apk.copy(size = -1), app, 700))
    }

    private val update = AvailableUpdate("0.8.0", 800, sha256, 1234, pc)
    private val signers = setOf("cd".repeat(32))
    private val facts = ApkFacts(app, 800, signers)

    private fun check(sha: String = sha256, size: Long = 1234, apk: ApkFacts? = facts, installedSigners: Set<String>? = signers) =
        checkDownloadedApk(update, sha, size, apk, app, installedVersionCode = 700, installedSigners = installedSigners)

    @Test
    fun `the downloaded APK is installed only when it is the one announced, for this app, newer, same signer`() {
        assertNull(check())
        assertNull(check(sha = sha256.uppercase()))
        assertEquals(UpdateFailure.NOT_AS_ANNOUNCED, check(size = 1235))
        assertEquals(UpdateFailure.NOT_AS_ANNOUNCED, check(sha = "00".repeat(32)))
        assertEquals(UpdateFailure.UNREADABLE, check(apk = null))
        assertEquals(UpdateFailure.OTHER_APP, check(apk = facts.copy(packageName = "fr.scanmylib")))
        assertEquals(UpdateFailure.NOT_NEWER, check(apk = facts.copy(versionCode = 700)))
        // Newer, but not the version announced.
        assertEquals(UpdateFailure.NOT_AS_ANNOUNCED, check(apk = facts.copy(versionCode = 900)))
        assertEquals(UpdateFailure.OTHER_SIGNER, check(apk = facts.copy(signers = setOf("ef".repeat(32)))))
        // Signers Android does not report are left to its own check.
        assertNull(check(apk = facts.copy(signers = null)))
        assertNull(check(installedSigners = null))
    }

    @Test
    fun `the download reports its digest and size, and stops past the announced size`() = runTest {
        MockWebServer().use { server ->
            val content = ByteArray(3000) { (it % 251).toByte() }
            server.enqueue(MockResponse.Builder().body(Buffer().write(content)).build())
            server.enqueue(MockResponse.Builder().body(Buffer().write(ByteArray(1024 * 1024))).build())
            server.enqueue(MockResponse.Builder().code(404).build())
            server.start()
            val url = server.url("/download/scanmylib.apk")
            val file = File(folder.root, "updates/scanmylib.apk")
            val progress = mutableListOf<Long>()

            val whole = downloadApk(OkHttpClient(), update.copy(size = 3000, url = url), file) { progress += it }
            assertEquals(Downloaded(sha256Of(content), 3000), whole)
            assertEquals(3000L, progress.last())
            assertEquals(content.toList(), file.readBytes().toList())

            // Stops at the first read past the announced size, far from the end of the body.
            val tooLong = downloadApk(OkHttpClient(), update.copy(size = 3000, url = url), file) {}
            assertTrue("received ${tooLong.size}", tooLong.size in 3001..3000 + 64 * 1024)

            val failure = runCatching { downloadApk(OkHttpClient(), update.copy(url = url), file) {} }.exceptionOrNull()
            assertEquals(true, failure is IOException)
        }
    }

    @Test
    fun `a redirect is not followed`() = runTest {
        MockWebServer().use { server ->
            server.enqueue(MockResponse.Builder().code(302).addHeader("Location", "/download/other.apk").build())
            server.enqueue(MockResponse.Builder().body(Buffer().write(ByteArray(1234))).build())
            server.start()
            val url = server.url("/download/scanmylib.apk")
            val file = File(folder.root, "updates/scanmylib.apk")

            val failure = runCatching { downloadApk(OkHttpClient(), update.copy(url = url), file) {} }.exceptionOrNull()
            assertTrue("$failure", failure is IOException)
            assertEquals(1, server.requestCount)
        }
    }

    @Test
    fun `a canceled download stops at once, even in the middle of a stalled read`() = runBlocking {
        // A PC that sends the headers and one byte of the APK, then nothing until the phone hangs up.
        ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { listener ->
            val pc = thread(isDaemon = true) {
                listener.accept().use { socket ->
                    socket.getOutputStream().write("HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nA".toByteArray())
                    socket.getOutputStream().flush()
                    runCatching { socket.getInputStream().readBytes() }
                }
            }
            val file = File(folder.root, "updates/stalled.apk")
            val url = "http://127.0.0.1:${listener.localPort}/download/scanmylib.apk".toHttpUrl()
            val http = OkHttpClient()
            val firstByte = CompletableDeferred<Unit>()
            var received = 0L
            var failure: Throwable? = null
            val download = launch(Dispatchers.Default) {
                try {
                    downloadApk(http, update.copy(size = 100, url = url), file) {
                        received = it
                        firstByte.complete(Unit)
                    }
                } catch (e: Throwable) {
                    failure = e
                    throw e
                }
            }
            withTimeout(10_000) { firstByte.await() }
            // Leaves the download the time to wait in its next read.
            delay(200)
            val started = System.nanoTime()
            download.cancelAndJoin()
            val elapsed = System.nanoTime() - started
            assertTrue("canceled in ${elapsed / 1_000_000} ms", elapsed < 2_000_000_000)
            // Canceled during the read that waits for the rest, not before the download started.
            assertEquals(1L, received)
            assertTrue("$failure", failure is CancellationException)
            pc.join(2_000)
        }
    }

    private fun sha256Of(bytes: ByteArray) =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
}
