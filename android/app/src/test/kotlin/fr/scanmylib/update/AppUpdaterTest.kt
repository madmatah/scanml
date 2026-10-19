package fr.scanmylib.update

import android.content.Intent
import android.content.pm.PackageInstaller
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import java.io.Closeable
import java.io.File
import java.security.MessageDigest
import java.time.Clock
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.atomic.AtomicInteger
import kotlin.properties.Delegates
import kotlinx.coroutines.CoroutineScope
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
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.BeforeClass
import org.junit.ClassRule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class AppUpdaterTest {
    @RunWith(Enclosed::class)
    class TheInstallResultFunction {
        class WhenAndroidAsksTheUserToConfirm {
            private lateinit var prompt: Intent
            private lateinit var waiting: UpdateState

            @Before
            fun reportThePrompt() {
                prompt = Intent()
                waiting = installResult(INSTALLING, PackageInstaller.STATUS_PENDING_USER_ACTION, null, prompt)
            }

            @Test
            fun `should keep the install's session`() {
                assertEquals(INSTALLING.sessionId, (waiting as? UpdateState.Installing)?.sessionId)
            }

            @Test
            fun `should keep Android's prompt, to show it again`() {
                assertSame(prompt, (waiting as? UpdateState.Installing)?.confirmation)
            }
        }

        @RunWith(Parameterized::class)
        class WhenAndroidEndsTheInstall(
            private val answer: String,
            private val status: Int,
            private val message: String?,
            private val expected: UpdateState,
        ) {
            private lateinit var stateOnceEnded: UpdateState

            @Before
            fun reportTheAnswer() {
                stateOnceEnded = installResult(INSTALLING, status, message, null)
            }

            @Test
            fun `should end the install as Android's answer says`() {
                assertEquals(answer, expected, stateOnceEnded)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun answers(): List<Array<Any?>> = listOf(
                    arrayOf("installed: up to date", PackageInstaller.STATUS_SUCCESS, null, UpdateState.UpToDate),
                    arrayOf(
                        "the user said no: the update is still offered",
                        PackageInstaller.STATUS_FAILURE_ABORTED,
                        "aborted",
                        UpdateState.Available(UPDATE),
                    ),
                    arrayOf(
                        "no room on the phone: the storage is full, with Android's message",
                        PackageInstaller.STATUS_FAILURE_STORAGE,
                        "not enough space",
                        UpdateState.Failed(UPDATE, UpdateFailure.STORAGE_FULL, "not enough space"),
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenAndroidRefusesTheInstall(
            private val refusal: String,
            private val status: Int,
            private val message: String?,
        ) {
            private lateinit var stateOnceRefused: UpdateState

            @Before
            fun reportTheRefusal() {
                stateOnceRefused = installResult(INSTALLING, status, message, null)
            }

            @Test
            fun `should keep Android's message for the details`() {
                assertEquals(refusal, UpdateState.Failed(UPDATE, UpdateFailure.INSTALL, message), stateOnceRefused)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun refusals(): List<Array<Any?>> = listOf(
                    arrayOf(
                        "a conflict, rarely another key since the app compares the certificates before",
                        PackageInstaller.STATUS_FAILURE_CONFLICT,
                        "INSTALL_FAILED_CONFLICTING_PROVIDER: another app declares the provider",
                    ),
                    arrayOf(
                        "an APK incompatible with the phone",
                        PackageInstaller.STATUS_FAILURE_INCOMPATIBLE,
                        "INSTALL_FAILED_OLDER_SDK",
                    ),
                    arrayOf("a failure without a message", PackageInstaller.STATUS_FAILURE, null),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheInstallMethod {
        class WhenRetriedAfterAFileNotAsAnnounced {
            @Test
            fun `should fail first, the file not being the one announced`() {
                assertEquals(UpdateState.Failed(firstOffer, UpdateFailure.NOT_AS_ANNOUNCED), stateAfterTheDownload)
            }

            @Test
            fun `should keep the banner while the PC is asked again`() {
                assertEquals(UpdateState.Downloading(firstOffer, 0), stateWhileThePcIsAsked)
            }

            @Test
            fun `should install at once what the PC offers now`() {
                assertEquals(UpdateState.Installing(newOffer, sessionId = 1), stateOnceSettled)
            }

            @Test
            fun `should commit that install`() {
                assertEquals(listOf(1), committed)
            }

            @Test
            fun `should ask the PC again before the download`() {
                assertEquals(2, healthCheckCount)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private lateinit var firstOffer: AvailableUpdate
                private lateinit var newOffer: AvailableUpdate
                private lateinit var stateAfterTheDownload: UpdateState
                private lateinit var stateWhileThePcIsAsked: UpdateState
                private lateinit var stateOnceSettled: UpdateState
                private lateinit var committed: List<Int>
                private var healthCheckCount: Int by Delegates.notNull()

                @BeforeClass
                @JvmStatic
                fun retryTheInstall() = runTest {
                    UpdaterBench(folder.root).use { bench ->
                        val updater = bench.updater(this)
                        failOnAnotherBuildPublishedAfterTheCheck(bench, updater)
                        firstOffer = bench.makeOfferFor(APK)
                        stateAfterTheDownload = updater.state.value
                        bench.pc.announcedApk = bench.pc.servedApk
                        updater.install()
                        stateWhileThePcIsAsked = updater.state.value
                        bench.awaitBackgroundWork()
                        stateOnceSettled = updater.state.value
                        newOffer = bench.makeOfferFor(bench.pc.servedApk)
                        committed = bench.installer.committed.toList()
                        healthCheckCount = bench.pc.healthChecks.value
                    }
                }
            }
        }

        class WhenARetryWasCanceledWhileThePcWasAsked {
            @Test
            fun `should fail first, the file not being the one announced`() {
                assertEquals(UpdateState.Failed(firstOffer, UpdateFailure.NOT_AS_ANNOUNCED), stateAfterTheDownload)
            }

            @Test
            fun `should offer the stale update again once the retry is canceled`() {
                assertEquals(UpdateState.Available(firstOffer), stateOnceCanceled)
            }

            @Test
            fun `should ask the PC first on the next install, rather than download the stale offer`() {
                assertEquals(UpdateState.Installing(newOffer, sessionId = 1), stateOnceInstalled)
            }

            @Test
            fun `should ask the PC once more on the next install`() {
                assertEquals(3, healthCheckCount)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private lateinit var firstOffer: AvailableUpdate
                private lateinit var newOffer: AvailableUpdate
                private lateinit var stateAfterTheDownload: UpdateState
                private lateinit var stateOnceCanceled: UpdateState
                private lateinit var stateOnceInstalled: UpdateState
                private var healthCheckCount: Int by Delegates.notNull()

                @BeforeClass
                @JvmStatic
                fun cancelTheRetryThenInstall() = runTest {
                    UpdaterBench(folder.root).use { bench ->
                        val updater = bench.updater(this)
                        failOnAnotherBuildPublishedAfterTheCheck(bench, updater)
                        firstOffer = bench.makeOfferFor(APK)
                        stateAfterTheDownload = updater.state.value
                        retryThenCancelWhileThePcIsAsked(bench, updater)
                        stateOnceCanceled = updater.state.value
                        bench.pc.heldAnswer = null
                        updater.install()
                        bench.awaitBackgroundWork()
                        stateOnceInstalled = updater.state.value
                        newOffer = bench.makeOfferFor(bench.pc.servedApk)
                        healthCheckCount = bench.pc.healthChecks.value
                    }
                }
            }
        }

        class WhenARetryCannotReachThePc {
            @Test
            fun `should keep the banner, and say the download failed`() {
                assertEquals(UpdateState.Failed(offer, UpdateFailure.DOWNLOAD), stateWhenUnreachable)
            }

            @Test
            fun `should show nothing once the PC offers nothing any more`() {
                assertEquals(UpdateState.UpToDate, stateWhenNothingIsOffered)
            }

            @Test
            fun `should install nothing`() {
                assertEquals(emptyList<Int>(), committed)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private lateinit var offer: AvailableUpdate
                private lateinit var stateWhenUnreachable: UpdateState
                private lateinit var stateWhenNothingIsOffered: UpdateState
                private lateinit var committed: List<Int>

                @BeforeClass
                @JvmStatic
                fun retryWithoutThePc() = runTest {
                    UpdaterBench(folder.root).use { bench ->
                        val updater = bench.updater(this)
                        failOnAnotherBuildPublishedAfterTheCheck(bench, updater)
                        offer = bench.makeOfferFor(APK)
                        bench.pc.isDown = true
                        updater.install()
                        bench.awaitBackgroundWork()
                        stateWhenUnreachable = updater.state.value
                        bench.pc.isDown = false
                        bench.pc.announcedApk = null
                        updater.install()
                        bench.awaitBackgroundWork()
                        stateWhenNothingIsOffered = updater.state.value
                        committed = bench.installer.committed.toList()
                    }
                }
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheCancelMethod {
        class WhenTheApkIsCopiedIntoTheInstallersSession {
            @Test
            fun `should offer the update again`() {
                assertEquals(UpdateState.Available(offer), state)
            }

            @Test
            fun `should commit nothing`() {
                assertEquals(emptyList<Int>(), committed)
            }

            @Test
            fun `should abandon the session`() {
                assertEquals(listOf(1), abandoned)
            }

            @Test
            fun `should leave no file behind`() {
                assertEquals(emptyList<String>(), downloadedFiles)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private lateinit var offer: AvailableUpdate
                private lateinit var state: UpdateState
                private lateinit var committed: List<Int>
                private lateinit var abandoned: List<Int>
                private lateinit var downloadedFiles: List<String>

                @BeforeClass
                @JvmStatic
                fun cancelDuringTheCopy() = runTest {
                    UpdaterBench(folder.root).use { bench ->
                        val updater = bench.updater(this)
                        updater.check()
                        bench.awaitBackgroundWork()
                        bench.installer.onCopy = { updater.cancel() }
                        updater.install()
                        bench.awaitBackgroundWork()
                        offer = bench.makeOfferFor(APK)
                        state = updater.state.value
                        committed = bench.installer.committed.toList()
                        abandoned = bench.installer.abandoned.toList()
                        downloadedFiles = bench.downloads.list().orEmpty().toList()
                    }
                }
            }
        }

        class WhenTheInstallHasBegunBeforeAndroidHasTheApk {
            @Test
            fun `should offer the update again, with no failure shown`() {
                assertEquals(UpdateState.Available(offer), state)
            }

            @Test
            fun `should commit nothing`() {
                assertEquals(emptyList<Int>(), committed)
            }

            @Test
            fun `should abandon its session, whose commit Android then refuses`() {
                assertTrue("$abandoned", 1 in abandoned)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private lateinit var offer: AvailableUpdate
                private lateinit var state: UpdateState
                private lateinit var committed: List<Int>
                private lateinit var abandoned: List<Int>

                @BeforeClass
                @JvmStatic
                fun cancelBeforeTheCommit() = runTest {
                    UpdaterBench(folder.root).use { bench ->
                        val updater = bench.updater(this)
                        updater.check()
                        bench.awaitBackgroundWork()
                        bench.installer.onCommit = {
                            updater.cancel()
                            bench.installer.abandonRecorded.await()
                        }
                        updater.install()
                        bench.awaitBackgroundWork()
                        offer = bench.makeOfferFor(APK)
                        state = updater.state.value
                        committed = bench.installer.committed.toList()
                        abandoned = bench.installer.abandoned.toList()
                    }
                }
            }
        }
    }

    class WhenAnInstallIsUnderWayThenCanceled {
        @Test
        fun `should hand the APK to Android`() {
            assertEquals(UpdateState.Installing(offer, sessionId = 1), stateOnceHandedOver)
        }

        @Test
        fun `should ignore a report about another session`() {
            assertFalse(isOtherSessionTaken)
        }

        @Test
        fun `should keep the install as it was after a report about another session`() {
            assertEquals(UpdateState.Installing(offer, sessionId = 1), stateAfterTheOtherSession)
        }

        @Test
        fun `should take a report about the current install`() {
            assertTrue(isCurrentSessionTaken)
        }

        @Test
        fun `should keep Android's prompt for the current install, to show it again`() {
            assertSame(prompt, shownPrompt.intent)
        }

        @Test
        fun `should offer the update again once the install is canceled`() {
            assertEquals(UpdateState.Available(offer), stateOnceCanceled)
        }

        @Test
        fun `should abandon the session of the canceled install`() {
            assertEquals(listOf(1), abandoned)
        }

        @Test
        fun `should ignore a report about the canceled install`() {
            assertFalse(isCanceledSessionTaken)
        }

        @Test
        fun `should not show the prompt of the canceled install`() {
            assertEquals(UpdateState.Available(offer), stateAfterTheCanceledSession)
        }

        companion object {
            @ClassRule
            @JvmField
            val folder = TemporaryFolder()

            private lateinit var offer: AvailableUpdate
            private lateinit var prompt: Intent
            private lateinit var stateOnceHandedOver: UpdateState
            private var isOtherSessionTaken: Boolean by Delegates.notNull()
            private lateinit var stateAfterTheOtherSession: UpdateState
            private var isCurrentSessionTaken: Boolean by Delegates.notNull()
            private lateinit var shownPrompt: Prompt
            private lateinit var stateOnceCanceled: UpdateState
            private lateinit var abandoned: List<Int>
            private var isCanceledSessionTaken: Boolean by Delegates.notNull()
            private lateinit var stateAfterTheCanceledSession: UpdateState

            @BeforeClass
            @JvmStatic
            fun reportOnTheInstall() = runTest {
                UpdaterBench(folder.root).use { bench ->
                    val updater = bench.updater(this)
                    updater.check()
                    bench.awaitBackgroundWork()
                    updater.install()
                    bench.awaitBackgroundWork()
                    offer = bench.makeOfferFor(APK)
                    stateOnceHandedOver = updater.state.value
                    val pending = PackageInstaller.STATUS_PENDING_USER_ACTION
                    isOtherSessionTaken = updater.onInstallResult(2, pending, null, Intent())
                    stateAfterTheOtherSession = updater.state.value
                    prompt = Intent()
                    isCurrentSessionTaken = updater.onInstallResult(1, pending, null, prompt)
                    shownPrompt = Prompt((updater.state.value as? UpdateState.Installing)?.confirmation)
                    updater.cancel()
                    bench.awaitBackgroundWork()
                    stateOnceCanceled = updater.state.value
                    abandoned = bench.installer.abandoned.toList()
                    isCanceledSessionTaken = updater.onInstallResult(1, pending, null, Intent())
                    stateAfterTheCanceledSession = updater.state.value
                }
            }
        }
    }

    class WhenTheAppIsPairedAgainDuringACheck {
        @Test
        fun `should offer the update the PC announces`() {
            assertEquals(UpdateState.Available(offer), stateAfterTheCheck)
        }

        @Test
        fun `should not ask the PC again a moment after it answered`() {
            assertEquals(UpdateState.Available(offer), stateAMomentLater)
        }

        @Test
        fun `should drop the check under way`() {
            assertEquals(UpdateState.Unknown, stateOnceReset)
        }

        @Test
        fun `should ask the PC at once when the library next shows`() {
            assertEquals(UpdateState.Checking, stateWhenDue)
        }

        @Test
        fun `should offer what the PC offers then`() {
            assertEquals(UpdateState.Available(offer), stateOnceAsked)
        }

        @Test
        fun `should ask the PC once more`() {
            assertEquals(3, healthCheckCount)
        }

        companion object {
            @ClassRule
            @JvmField
            val folder = TemporaryFolder()

            private lateinit var offer: AvailableUpdate
            private lateinit var stateAfterTheCheck: UpdateState
            private lateinit var stateAMomentLater: UpdateState
            private lateinit var stateOnceReset: UpdateState
            private lateinit var stateWhenDue: UpdateState
            private lateinit var stateOnceAsked: UpdateState
            private var healthCheckCount: Int by Delegates.notNull()

            @BeforeClass
            @JvmStatic
            fun pairAgainDuringACheck() = runTest {
                UpdaterBench(folder.root).use { bench ->
                    val updater = bench.updater(this)
                    updater.check()
                    bench.awaitBackgroundWork()
                    offer = bench.makeOfferFor(APK)
                    stateAfterTheCheck = updater.state.value
                    updater.checkIfDue()
                    stateAMomentLater = updater.state.value
                    val answer = CountDownLatch(1)
                    bench.pc.heldAnswer = answer
                    updater.check()
                    bench.pc.healthChecks.first { it == 2 }
                    updater.reset()
                    answer.countDown()
                    bench.awaitBackgroundWork()
                    stateOnceReset = updater.state.value
                    bench.pc.heldAnswer = null
                    updater.checkIfDue()
                    stateWhenDue = updater.state.value
                    bench.awaitBackgroundWork()
                    stateOnceAsked = updater.state.value
                    healthCheckCount = bench.pc.healthChecks.value
                }
            }
        }
    }

    class WhenTheInstallWaitsForAndroidsPermission {
        @Test
        fun `should wait for Android's permission to install apps`() {
            assertEquals(UpdateState.NeedsPermission(offer), stateWithoutPermission)
        }

        @Test
        fun `should not replace the install, even when a check is due, since the user may be on Android's page`() {
            assertEquals(UpdateState.NeedsPermission(offer), stateWhenDue)
        }

        @Test
        fun `should keep waiting back in the app without the permission`() {
            assertEquals(UpdateState.NeedsPermission(offer), stateBackWithoutPermission)
        }

        @Test
        fun `should go on with the install back in the app with the permission`() {
            assertEquals(UpdateState.Installing(offer, sessionId = 1), stateBackWithPermission)
        }

        @Test
        fun `should not ask the PC again`() {
            assertEquals(1, healthCheckCount)
        }

        companion object {
            @ClassRule
            @JvmField
            val folder = TemporaryFolder()

            private lateinit var offer: AvailableUpdate
            private lateinit var stateWithoutPermission: UpdateState
            private lateinit var stateWhenDue: UpdateState
            private lateinit var stateBackWithoutPermission: UpdateState
            private lateinit var stateBackWithPermission: UpdateState
            private var healthCheckCount: Int by Delegates.notNull()

            @BeforeClass
            @JvmStatic
            fun waitForThePermission() = runTest {
                UpdaterBench(folder.root).use { bench ->
                    val updater = bench.updater(this)
                    bench.installer.isAllowed = false
                    updater.check()
                    bench.awaitBackgroundWork()
                    updater.install()
                    offer = bench.makeOfferFor(APK)
                    stateWithoutPermission = updater.state.value
                    bench.clock.now += Duration.ofHours(2)
                    updater.checkIfDue()
                    stateWhenDue = updater.state.value
                    updater.onReturn()
                    stateBackWithoutPermission = updater.state.value
                    bench.installer.isAllowed = true
                    updater.onReturn()
                    bench.awaitBackgroundWork()
                    stateBackWithPermission = updater.state.value
                    healthCheckCount = bench.pc.healthChecks.value
                }
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOnReturnMethod {
        class WhenAndroidsPromptIsLeftWithoutAnAnswer {
            @Test
            fun `should keep waiting for the answer`() {
                assertEquals(UpdateState.Installing(offer, sessionId = 1), stateWithoutAnAnswer)
            }

            @Test
            fun `should offer the update again once its session is gone, answered while the app was away`() {
                assertEquals(UpdateState.Available(offer), stateOnceAnswered)
            }

            companion object {
                @ClassRule
                @JvmField
                val folder = TemporaryFolder()

                private lateinit var offer: AvailableUpdate
                private lateinit var stateWithoutAnAnswer: UpdateState
                private lateinit var stateOnceAnswered: UpdateState

                @BeforeClass
                @JvmStatic
                fun comeBackToTheApp() = runTest {
                    UpdaterBench(folder.root).use { bench ->
                        val updater = bench.updater(this)
                        updater.check()
                        bench.awaitBackgroundWork()
                        updater.install()
                        bench.awaitBackgroundWork()
                        offer = bench.makeOfferFor(APK)
                        updater.onReturn()
                        bench.awaitBackgroundWork()
                        stateWithoutAnAnswer = updater.state.value
                        bench.installer.sessions -= 1
                        updater.onReturn()
                        bench.awaitBackgroundWork()
                        stateOnceAnswered = updater.state.value
                    }
                }
            }
        }
    }

    class WhenTheLastCheckCouldNotReachThePc {
        @Test
        fun `should show that the check failed`() {
            assertEquals(UpdateState.CheckFailed, stateAfterTheCheck)
        }

        @Test
        fun `should not check again before an hour has passed`() {
            assertEquals(UpdateState.CheckFailed, stateWhenNotDue)
        }

        @Test
        fun `should check again at once when the PC answers the library again`() {
            assertEquals(UpdateState.Checking, stateWhenThePcIsBack)
        }

        @Test
        fun `should offer the update the PC announces`() {
            assertEquals(UpdateState.Available(offer), stateOnceAsked)
        }

        @Test
        fun `should not check again after a check that succeeded`() {
            assertEquals(UpdateState.Available(offer), stateWhenThePcIsBackAgain)
            assertEquals(2, healthCheckCount)
        }

        companion object {
            @ClassRule
            @JvmField
            val folder = TemporaryFolder()

            private lateinit var offer: AvailableUpdate
            private lateinit var stateAfterTheCheck: UpdateState
            private lateinit var stateWhenNotDue: UpdateState
            private lateinit var stateWhenThePcIsBack: UpdateState
            private lateinit var stateOnceAsked: UpdateState
            private lateinit var stateWhenThePcIsBackAgain: UpdateState
            private var healthCheckCount: Int by Delegates.notNull()

            @BeforeClass
            @JvmStatic
            fun bringThePcBack() = runTest {
                UpdaterBench(folder.root).use { bench ->
                    val updater = bench.updater(this)
                    bench.pc.isDown = true
                    updater.check()
                    bench.awaitBackgroundWork()
                    stateAfterTheCheck = updater.state.value
                    bench.pc.isDown = false
                    updater.checkIfDue()
                    stateWhenNotDue = updater.state.value
                    updater.onPcBack()
                    stateWhenThePcIsBack = updater.state.value
                    bench.awaitBackgroundWork()
                    offer = bench.makeOfferFor(APK)
                    stateOnceAsked = updater.state.value
                    updater.onPcBack()
                    stateWhenThePcIsBackAgain = updater.state.value
                    healthCheckCount = bench.pc.healthChecks.value
                }
            }
        }
    }
}

private const val APP = "fr.scanmylib.dev"
private const val TOKEN = "q9Xz-Lm_3vT0"
private val APK = ByteArray(3000) { (it % 251).toByte() }
private val SIGNERS = setOf("cd".repeat(32))
private val UPDATE = AvailableUpdate(
    "0.8.0",
    800,
    "ab".repeat(32),
    1234,
    "http://192.168.1.10:8770/download/scanmylib.apk".toHttpUrl(),
)
private val INSTALLING = UpdateState.Installing(UPDATE, sessionId = 7)

/** Android's prompt, which may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class Prompt(val intent: Intent?)

private class UpdaterBench(private val folder: File) : Closeable {
    val pc = Pc()
    val installer = FakeInstaller()
    val clock = MovingClock(Instant.parse("2026-10-17T08:00:00Z"))
    val downloads = File(folder, "updates")
    private val server = MockWebServer().apply {
        dispatcher = pc
        start()
    }
    private val background = SupervisorJob()

    suspend fun updater(test: TestScope): AppUpdater {
        val dataStore = PreferenceDataStoreFactory.create(scope = test.backgroundScope) {
            File(folder, "settings.preferences_pb")
        }
        val settings = SettingsRepository(dataStore)
        settings.pair(ServerConfig(server.url("/"), TOKEN))
        val http = OkHttpClient()
        val scope = CoroutineScope(StandardTestDispatcher(test.testScheduler) + background)
        return AppUpdater(installer, downloads, settings, { ScanMyLibApi(http, it) }, http, scope, clock)
    }

    suspend fun awaitBackgroundWork() {
        while (true) {
            val running = background.children.filter { !it.isCompleted }.toList()
            if (running.isEmpty()) return
            running.joinAll()
        }
    }

    fun makeOfferFor(apk: ByteArray) =
        AvailableUpdate("0.8.0", 800, computeSha256(apk), apk.size.toLong(), server.url("/download/scanmylib.apk"))

    override fun close() {
        background.cancel()
        server.close()
    }
}

private class Pc : Dispatcher() {
    @Volatile var announcedApk: ByteArray? = APK

    @Volatile var servedApk: ByteArray = APK

    @Volatile var isDown = false

    @Volatile var heldAnswer: CountDownLatch? = null

    val healthChecks = MutableStateFlow(0)

    override fun dispatch(request: RecordedRequest): MockResponse = when (request.url.encodedPath) {
        "/api/health" -> {
            healthChecks.update { it + 1 }
            heldAnswer?.await()
            if (isDown) MockResponse.Builder().code(503).build() else MockResponse.Builder().body(health()).build()
        }

        "/download/scanmylib.apk" -> MockResponse.Builder().body(Buffer().write(servedApk)).build()

        else -> MockResponse.Builder().code(404).build()
    }

    private fun health(): String {
        val apk = announcedApk ?: return """{"name": "ScanMyLib", "api": 1, "apk": null}"""
        return """
            {"name": "ScanMyLib", "api": 1, "apk": {"application_id": "$APP", "version": "0.8.0",
             "version_code": 800, "sha256": "${computeSha256(apk)}", "size": ${apk.size},
             "path": "/download/scanmylib.apk"}}
        """
    }
}

/** Committing an abandoned session throws, as Android does. */
private class FakeInstaller : AppInstaller {
    override val packageName = APP

    override val versionCode = 700L

    @Volatile var isAllowed = true

    @Volatile var onCopy: () -> Unit = {}

    @Volatile var onCommit: () -> Unit = {}

    private val lastSession = AtomicInteger()
    val sessions: MutableSet<Int> = ConcurrentHashMap.newKeySet()
    val committed: MutableList<Int> = CopyOnWriteArrayList()
    val abandoned: MutableList<Int> = CopyOnWriteArrayList()

    /** Opened once the session is gone, so that a commit that awaits it finds the session abandoned. */
    val abandonRecorded = CountDownLatch(1)

    override fun signers() = SIGNERS

    override fun canInstall() = isAllowed

    override fun archiveFacts(file: File) = ApkFacts(APP, 800, SIGNERS)

    override fun createSession(file: File): Int {
        val sessionId = lastSession.incrementAndGet()
        sessions += sessionId
        onCopy()
        return sessionId
    }

    override fun commit(sessionId: Int) {
        onCommit()
        if (sessionId !in sessions) throw SecurityException("session $sessionId was abandoned")
        committed += sessionId
    }

    override fun abandon(sessionId: Int) {
        sessions -= sessionId
        abandoned += sessionId
        abandonRecorded.countDown()
    }

    override fun hasSession(sessionId: Int) = sessionId in sessions
}

private class MovingClock(@Volatile var now: Instant) : Clock() {
    override fun instant(): Instant = now

    override fun getZone(): ZoneId = ZoneOffset.UTC

    override fun withZone(zone: ZoneId): Clock = this
}

private suspend fun failOnAnotherBuildPublishedAfterTheCheck(bench: UpdaterBench, updater: AppUpdater) {
    bench.pc.servedApk = ByteArray(APK.size) { 7 }
    updater.check()
    bench.awaitBackgroundWork()
    updater.install()
    bench.awaitBackgroundWork()
}

private suspend fun retryThenCancelWhileThePcIsAsked(bench: UpdaterBench, updater: AppUpdater) {
    bench.pc.announcedApk = bench.pc.servedApk
    val answer = CountDownLatch(1)
    bench.pc.heldAnswer = answer
    updater.install()
    bench.pc.healthChecks.first { it == 2 }
    updater.cancel()
    answer.countDown()
    bench.awaitBackgroundWork()
}

private fun computeSha256(bytes: ByteArray) =
    MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
