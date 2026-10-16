package fr.scanmylib.update

import android.content.Intent
import android.content.pm.PackageInstaller
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import java.io.File
import java.security.MessageDigest
import java.time.Clock
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.Collections
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runTest
import mockwebserver3.Dispatcher
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import mockwebserver3.RecordedRequest
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

@OptIn(ExperimentalCoroutinesApi::class)
class AppUpdaterTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val update =
        AvailableUpdate("0.8.0", 800, "ab".repeat(32), 1234, "http://192.168.1.10:8770/download/scanmylib.apk".toHttpUrl())
    private val installing = UpdateState.Installing(update, sessionId = 7)

    @Test
    fun `Android's prompt is kept, to show again`() {
        val prompt = Intent()
        val waiting = installResult(installing, PackageInstaller.STATUS_PENDING_USER_ACTION, null, prompt)
        assertEquals(installing.sessionId, (waiting as UpdateState.Installing).sessionId)
        assertSame(prompt, waiting.confirmation)
    }

    @Test
    fun `the installer's answer ends the install`() {
        assertEquals(UpdateState.UpToDate, installResult(installing, PackageInstaller.STATUS_SUCCESS, null, null))
        // The user said no: the update is still offered.
        assertEquals(
            UpdateState.Available(update),
            installResult(installing, PackageInstaller.STATUS_FAILURE_ABORTED, "aborted", null),
        )
        assertEquals(
            UpdateState.Failed(update, UpdateFailure.STORAGE_FULL, "not enough space"),
            installResult(installing, PackageInstaller.STATUS_FAILURE_STORAGE, "not enough space", null),
        )
    }

    @Test
    fun `a refused install keeps Android's message for the details, a conflict included`() {
        // A conflict is rarely another key: the app compares the certificates before.
        val conflict = "INSTALL_FAILED_CONFLICTING_PROVIDER: another app declares the provider"
        assertEquals(
            UpdateState.Failed(update, UpdateFailure.INSTALL, conflict),
            installResult(installing, PackageInstaller.STATUS_FAILURE_CONFLICT, conflict, null),
        )
        assertEquals(
            UpdateState.Failed(update, UpdateFailure.INSTALL, "INSTALL_FAILED_OLDER_SDK"),
            installResult(installing, PackageInstaller.STATUS_FAILURE_INCOMPATIBLE, "INSTALL_FAILED_OLDER_SDK", null),
        )
        assertEquals(
            UpdateState.Failed(update, UpdateFailure.INSTALL, null),
            installResult(installing, PackageInstaller.STATUS_FAILURE, null, null),
        )
    }

    @Test
    fun `an attempt that ended no longer acts`() {
        val attempts = CurrentAttempt()
        val first = attempts.next()
        assertTrue(attempts.ifCurrent(first) {})
        val second = attempts.next()
        var ran = false
        assertFalse(attempts.ifCurrent(first) { ran = true })
        assertFalse(ran)
        assertTrue(attempts.ifCurrent(second) { ran = true })
        assertTrue(ran)
    }

    @Test
    fun `an attempt never ends halfway through one of its steps`() {
        val attempts = CurrentAttempt()
        val id = attempts.next()
        val events = Collections.synchronizedList(mutableListOf<String>())
        val stepStarted = CountDownLatch(1)
        val stepMayEnd = CountDownLatch(1)
        val step = thread {
            attempts.ifCurrent(id) {
                stepStarted.countDown()
                stepMayEnd.await()
                events += "step"
            }
        }
        stepStarted.await()
        // A cancel, while the step runs: it waits for the step to end.
        val cancel = thread { attempts.next { events += "canceled" } }
        while (cancel.isAlive && cancel.state != Thread.State.BLOCKED) Thread.yield()
        stepMayEnd.countDown()
        step.join()
        cancel.join()
        assertEquals(listOf("step", "canceled"), events)
    }

    // The updater itself, with a PC on this machine and a fake Android.

    private val pc = Pc()
    private val server = MockWebServer()
    private val installer = FakeInstaller()
    private val clock = MovingClock(Instant.parse("2026-10-17T08:00:00Z"))

    /** What the updater runs in the background: checks, downloads, installs. */
    private val background = SupervisorJob()

    @Before
    fun setUp() {
        server.dispatcher = pc
        server.start()
    }

    @After
    fun tearDown() {
        background.cancel()
        server.close()
    }

    /** The updater of an app paired with [server], on the test's dispatcher. */
    private suspend fun TestScope.updater(): AppUpdater {
        val dataStore = PreferenceDataStoreFactory.create(scope = backgroundScope) {
            File(folder.root, "settings.preferences_pb")
        }
        val settings = SettingsRepository(dataStore)
        settings.pair(ServerConfig(server.url("/"), TOKEN))
        val http = OkHttpClient()
        val scope = CoroutineScope(StandardTestDispatcher(testScheduler) + background)
        val downloads = File(folder.root, "updates")
        return AppUpdater(installer, downloads, settings, { ScanMyLibApi(http, it) }, http, scope, clock)
    }

    /** Waits for what the updater runs in the background. */
    private suspend fun settle() {
        while (true) {
            val running = background.children.filter { !it.isCompleted }.toList()
            if (running.isEmpty()) return
            running.joinAll()
        }
    }

    /** The update the PC offers for [apk], published as its download. */
    private fun offerOf(apk: ByteArray) =
        AvailableUpdate("0.8.0", 800, sha256Of(apk), apk.size.toLong(), server.url("/download/scanmylib.apk"))

    @Test
    fun `after a file not as announced, Retry asks the PC again and installs what it offers, at once`() = runTest {
        val updater = updater()
        // The PC published another build after it answered.
        pc.served = ByteArray(APK.size) { 7 }
        updater.check()
        settle()
        updater.install()
        settle()
        val first = offerOf(APK)
        assertEquals(UpdateState.Failed(first, UpdateFailure.NOT_AS_ANNOUNCED), updater.state.value)

        pc.announced = pc.served
        updater.install()
        // The banner stays while the PC is asked.
        assertEquals(UpdateState.Downloading(first, 0), updater.state.value)
        settle()
        assertEquals(UpdateState.Installing(offerOf(pc.served), sessionId = 1), updater.state.value)
        assertEquals(listOf(1), installer.committed)
        assertEquals(2, pc.healthChecks.value)
    }

    @Test
    fun `a Retry canceled while the PC is asked still asks it first the next time`() = runTest {
        val updater = updater()
        pc.served = ByteArray(APK.size) { 7 }
        updater.check()
        settle()
        updater.install()
        settle()
        val first = offerOf(APK)
        assertEquals(UpdateState.Failed(first, UpdateFailure.NOT_AS_ANNOUNCED), updater.state.value)

        // Retry, then Cancel while the PC is slow to answer: the stale offer is back on the banner.
        pc.announced = pc.served
        val answer = CountDownLatch(1)
        pc.held = answer
        updater.install()
        pc.healthChecks.first { it == 2 }
        updater.cancel()
        answer.countDown()
        settle()
        assertEquals(UpdateState.Available(first), updater.state.value)

        // Install asks the PC again rather than download the stale offer.
        pc.held = null
        updater.install()
        settle()
        assertEquals(UpdateState.Installing(offerOf(pc.served), sessionId = 1), updater.state.value)
        assertEquals(3, pc.healthChecks.value)
    }

    @Test
    fun `a Retry that cannot reach the PC keeps the banner and says so`() = runTest {
        val updater = updater()
        pc.served = ByteArray(APK.size) { 7 }
        updater.check()
        settle()
        updater.install()
        settle()
        val offer = offerOf(APK)

        pc.down = true
        updater.install()
        settle()
        assertEquals(UpdateState.Failed(offer, UpdateFailure.DOWNLOAD), updater.state.value)

        // The PC offers nothing any more: nothing left to show.
        pc.down = false
        pc.announced = null
        updater.install()
        settle()
        assertEquals(UpdateState.UpToDate, updater.state.value)
        assertEquals(emptyList<Int>(), installer.committed)
    }

    @Test
    fun `a cancel before the APK is handed over commits nothing and leaves nothing behind`() = runTest {
        val updater = updater()
        updater.check()
        settle()
        // The user taps Cancel while the APK is copied into the installer's session.
        installer.onCopy = { updater.cancel() }
        updater.install()
        settle()
        assertEquals(UpdateState.Available(offerOf(APK)), updater.state.value)
        assertEquals(emptyList<Int>(), installer.committed)
        assertEquals(listOf(1), installer.abandoned)
        assertEquals(emptyList<String>(), File(folder.root, "updates").list().orEmpty().toList())
    }

    @Test
    fun `a cancel just before the APK is handed over abandons its session, and no failure shows`() = runTest {
        val updater = updater()
        updater.check()
        settle()
        // The user taps Cancel once the install has begun, before Android has the APK: the
        // session is abandoned before the commit, which Android then refuses.
        installer.onCommit = { sessionId ->
            updater.cancel()
            while (sessionId !in installer.abandoned) Thread.sleep(1)
        }
        updater.install()
        settle()
        assertEquals(UpdateState.Available(offerOf(APK)), updater.state.value)
        assertEquals(emptyList<Int>(), installer.committed)
        assertTrue(1 in installer.abandoned)
    }

    @Test
    fun `Android's report on an install that is no longer current is ignored, its prompt not shown`() = runTest {
        val updater = updater()
        updater.check()
        settle()
        updater.install()
        settle()
        val offer = offerOf(APK)
        assertEquals(UpdateState.Installing(offer, sessionId = 1), updater.state.value)

        assertFalse(updater.onInstallResult(2, PackageInstaller.STATUS_PENDING_USER_ACTION, null, Intent()))
        assertEquals(UpdateState.Installing(offer, sessionId = 1), updater.state.value)
        val prompt = Intent()
        assertTrue(updater.onInstallResult(1, PackageInstaller.STATUS_PENDING_USER_ACTION, null, prompt))
        assertSame(prompt, (updater.state.value as UpdateState.Installing).confirmation)

        updater.cancel()
        settle()
        assertEquals(UpdateState.Available(offer), updater.state.value)
        assertEquals(listOf(1), installer.abandoned)
        assertFalse(updater.onInstallResult(1, PackageInstaller.STATUS_PENDING_USER_ACTION, null, Intent()))
        assertEquals(UpdateState.Available(offer), updater.state.value)
    }

    @Test
    fun `pairing again drops the check under way and asks the PC at once`() = runTest {
        val updater = updater()
        updater.check()
        settle()
        val offer = offerOf(APK)
        assertEquals(UpdateState.Available(offer), updater.state.value)
        // Asked a moment ago: not again.
        updater.checkIfDue()
        assertEquals(UpdateState.Available(offer), updater.state.value)

        val answer = CountDownLatch(1)
        pc.held = answer
        updater.check()
        pc.healthChecks.first { it == 2 }
        updater.reset()
        answer.countDown()
        settle()
        assertEquals(UpdateState.Unknown, updater.state.value)

        pc.held = null
        updater.checkIfDue()
        assertEquals(UpdateState.Checking, updater.state.value)
        settle()
        assertEquals(UpdateState.Available(offer), updater.state.value)
        assertEquals(3, pc.healthChecks.value)
    }

    @Test
    fun `a check never replaces the install waiting for Android's permission`() = runTest {
        val updater = updater()
        installer.allowed = false
        updater.check()
        settle()
        updater.install()
        val offer = offerOf(APK)
        assertEquals(UpdateState.NeedsPermission(offer), updater.state.value)

        // Due, but the user may be on Android's page: the install goes on once back.
        clock.now += Duration.ofHours(2)
        updater.checkIfDue()
        assertEquals(UpdateState.NeedsPermission(offer), updater.state.value)
        updater.onReturn()
        assertEquals(UpdateState.NeedsPermission(offer), updater.state.value)

        installer.allowed = true
        updater.onReturn()
        settle()
        assertEquals(UpdateState.Installing(offer, sessionId = 1), updater.state.value)
        assertEquals(1, pc.healthChecks.value)
    }

    @Test
    fun `back in the app, an install whose session is gone is offered again`() = runTest {
        val updater = updater()
        updater.check()
        settle()
        updater.install()
        settle()
        val offer = offerOf(APK)
        // Android's prompt, left without an answer: still waiting.
        updater.onReturn()
        settle()
        assertEquals(UpdateState.Installing(offer, sessionId = 1), updater.state.value)

        // Answered while the app was away.
        installer.sessions -= 1
        updater.onReturn()
        settle()
        assertEquals(UpdateState.Available(offer), updater.state.value)
    }

    @Test
    fun `a check that could not reach the PC is made again once the PC answers`() = runTest {
        val updater = updater()
        pc.down = true
        updater.check()
        settle()
        assertEquals(UpdateState.CheckFailed, updater.state.value)

        pc.down = false
        // Not due for an hour.
        updater.checkIfDue()
        assertEquals(UpdateState.CheckFailed, updater.state.value)
        updater.onPcBack()
        assertEquals(UpdateState.Checking, updater.state.value)
        settle()
        assertEquals(UpdateState.Available(offerOf(APK)), updater.state.value)

        // Only after a check that failed.
        updater.onPcBack()
        assertEquals(UpdateState.Available(offerOf(APK)), updater.state.value)
        assertEquals(2, pc.healthChecks.value)
    }

    /**
     * The paired PC: announces [announced] in its health check (none if null), and serves
     * [served] as its download; [down] fails its health check, [held] holds its answer.
     */
    private class Pc : Dispatcher() {
        @Volatile var announced: ByteArray? = APK

        @Volatile var served: ByteArray = APK

        @Volatile var down = false

        @Volatile var held: CountDownLatch? = null

        val healthChecks = MutableStateFlow(0)

        override fun dispatch(request: RecordedRequest): MockResponse = when (request.url.encodedPath) {
            "/api/health" -> {
                healthChecks.update { it + 1 }
                held?.await()
                if (down) MockResponse.Builder().code(503).build() else MockResponse.Builder().body(health()).build()
            }
            "/download/scanmylib.apk" -> MockResponse.Builder().body(Buffer().write(served)).build()
            else -> MockResponse.Builder().code(404).build()
        }

        private fun health(): String {
            val apk = announced ?: return """{"name": "ScanMyLib", "api": 1, "apk": null}"""
            return """
                {"name": "ScanMyLib", "api": 1, "apk": {"application_id": "$APP", "version": "0.8.0",
                 "version_code": 800, "sha256": "${sha256Of(apk)}", "size": ${apk.size},
                 "path": "/download/scanmylib.apk"}}
            """
        }
    }

    /**
     * Android, as the updater sees it: the app at versionCode 700, allowed to install apps unless
     * [allowed] says otherwise, and the installer's [sessions]. [onCopy] runs as the APK is copied
     * into a session, [onCommit] as a session is committed; committing an abandoned session
     * throws, as Android does.
     */
    private class FakeInstaller : AppInstaller {
        override val packageName = APP

        override val versionCode = 700L

        @Volatile var allowed = true

        @Volatile var onCopy: () -> Unit = {}

        @Volatile var onCommit: (Int) -> Unit = {}

        private val lastSession = AtomicInteger()
        val sessions: MutableSet<Int> = ConcurrentHashMap.newKeySet()
        val committed: MutableList<Int> = CopyOnWriteArrayList()
        val abandoned: MutableList<Int> = CopyOnWriteArrayList()

        override fun signers() = SIGNERS

        override fun canInstall() = allowed

        override fun archiveFacts(file: File) = ApkFacts(APP, 800, SIGNERS)

        override fun createSession(file: File): Int {
            val sessionId = lastSession.incrementAndGet()
            sessions += sessionId
            onCopy()
            return sessionId
        }

        override fun commit(sessionId: Int) {
            onCommit(sessionId)
            if (sessionId !in sessions) throw SecurityException("session $sessionId was abandoned")
            committed += sessionId
        }

        override fun abandon(sessionId: Int) {
            abandoned += sessionId
            sessions -= sessionId
        }

        override fun hasSession(sessionId: Int) = sessionId in sessions
    }

    /** A clock the test moves forward. */
    private class MovingClock(@Volatile var now: Instant) : Clock() {
        override fun instant(): Instant = now

        override fun getZone(): ZoneId = ZoneOffset.UTC

        override fun withZone(zone: ZoneId): Clock = this
    }

    private companion object {
        const val APP = "fr.scanmylib.dev"
        const val TOKEN = "q9Xz-Lm_3vT0"
        val APK = ByteArray(3000) { (it % 251).toByte() }
        val SIGNERS = setOf("cd".repeat(32))
    }
}

private fun sha256Of(bytes: ByteArray) =
    MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
