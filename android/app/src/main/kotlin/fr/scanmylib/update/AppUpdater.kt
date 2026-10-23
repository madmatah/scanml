package fr.scanmylib.update

import android.content.Intent
import android.content.pm.PackageInstaller
import android.util.Log
import fr.scanmylib.api.ApiException
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.library.isStorageFull
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import java.io.File
import java.io.IOException
import java.time.Clock
import java.time.Duration
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient

/** Where the app stands with its updates. */
sealed interface UpdateState {
    /** Not checked yet, or no PC to ask. */
    data object Unknown : UpdateState

    data object Checking : UpdateState

    /** The PC offers no newer APK. */
    data object UpToDate : UpdateState

    /** The PC could not be asked: no banner, the library says when the PC is unreachable. */
    data object CheckFailed : UpdateState

    data class Available(override val update: AvailableUpdate) : WithUpdate

    /** Android must allow ScanMyLib to install apps first, once (its system page). */
    data class NeedsPermission(override val update: AvailableUpdate) : WithUpdate

    data class Downloading(override val update: AvailableUpdate, val received: Long) : WithUpdate {
        val progress: Float get() = (received.toFloat() / update.size).coerceIn(0f, 1f)
    }

    /**
     * Handed to Android's installer, in its session [sessionId], which asks the user to confirm;
     * [confirmation] is Android's prompt, to show again if the user left it without answering.
     */
    data class Installing(override val update: AvailableUpdate, val sessionId: Int, val confirmation: Intent? = null) :
        WithUpdate

    /** [detail]: Android's message, when it gave one, for "Details". */
    data class Failed(override val update: AvailableUpdate, val failure: UpdateFailure, val detail: String? = null) :
        WithUpdate

    /** A state about an update the PC offers. */
    sealed interface WithUpdate : UpdateState {
        val update: AvailableUpdate
    }
}

/**
 * Checks the paired PC for a newer APK of this app, then downloads it into [downloads], checks it
 * and hands it to Android's [installer]. One instance for the app: a download goes on whatever
 * screen is shown. The first time, Android needs the user to allow ScanMyLib to install apps,
 * on a system page; [onReturn] resumes once they did.
 */
class AppUpdater(
    private val installer: AppInstaller,
    private val downloads: File,
    private val settings: SettingsRepository,
    private val api: (ServerConfig) -> ScanMyLibApi,
    private val http: OkHttpClient,
    private val scope: CoroutineScope,
    private val clock: Clock,
) {
    private val mutableState = MutableStateFlow<UpdateState>(UpdateState.Unknown)
    private var job: Job? = null

    /** When the PC was last asked; null: at the next [checkIfDue]. */
    @Volatile
    private var lastCheck: Instant? = null

    /** The current check, or download and install; one canceled or replaced since no longer changes the state. */
    private val attempts = CurrentAttempt()

    /**
     * An attempt on the offer in the state failed: the next install asks the PC first, even if
     * the Retry was canceled while asking or went through Android's permission page.
     */
    @Volatile
    private var askFirst = false

    val state: StateFlow<UpdateState> = mutableState.asStateFlow()

    /** One file per attempt: a canceled one, still winding down, never touches the next one's. */
    private fun downloadedApk(attempt: Int) = File(downloads, "scanmylib-$attempt.apk")

    /** Asks the PC unless it was asked recently: when the library shows or is refreshed. */
    fun checkIfDue() {
        // Not while the install waits for Android's permission, maybe on its page: it goes on once back.
        if (mutableState.value is UpdateState.NeedsPermission) return
        val last = lastCheck
        if (last == null || Duration.between(last, clock.instant()) >= CHECK_INTERVAL) check()
    }

    /**
     * The PC answers the library again: asks it now if the last check could not reach it, rather
     * than up to an hour later.
     */
    fun onPcBack() {
        if (mutableState.value is UpdateState.CheckFailed) check()
    }

    /** Asks the PC now (Settings), unless an update is being downloaded or installed. */
    fun check() {
        val current = mutableState.value
        if (current is UpdateState.Checking ||
            current is UpdateState.Downloading ||
            current is UpdateState.Installing
        ) {
            return
        }
        val id = attempts.next { mutableState.value = UpdateState.Checking }
        job = scope.launch { askPc(id)?.let { setFor(id, it) } }
    }

    /**
     * Downloads, checks and installs the update offered, asking for Android's permission first.
     * After a failure, it asks the PC first, while the banner shows the download: after a file
     * that was not the one announced, for one, the same offer would fail the same way.
     */
    fun install() {
        val current = mutableState.value as? UpdateState.WithUpdate ?: return
        if (current is UpdateState.Downloading || current is UpdateState.Installing) return
        val update = current.update
        if (!installer.canInstall()) {
            mutableState.value = UpdateState.NeedsPermission(update)
            return
        }
        val retry = askFirst
        val id = attempts.next { mutableState.value = UpdateState.Downloading(update, 0) }
        job = scope.launch {
            val offered = if (retry) offeredAgain(id, update) else update
            if (offered != null) downloadAndInstall(id, offered)
        }
    }

    /**
     * Back in the app: maybe from the system page that allows installing, then the install goes
     * on; or from Android's prompt, left without an answer (the banner offers it again), or
     * answered while the app was away (its session is gone: the update is offered again).
     */
    fun onReturn() {
        when (val current = mutableState.value) {
            is UpdateState.NeedsPermission -> if (installer.canInstall()) install()

            is UpdateState.Installing -> scope.launch {
                if (!withContext(Dispatchers.IO) { installer.hasSession(current.sessionId) }) {
                    mutableState.compareAndSet(current, UpdateState.Available(current.update))
                }
            }

            else -> Unit
        }
    }

    /** Stops a download, or gives up an install waiting for the user: the update is still offered. */
    fun cancel() {
        val current = mutableState.value as? UpdateState.WithUpdate ?: return
        if (current is UpdateState.Downloading || current is UpdateState.Installing) {
            endAttempt(UpdateState.Available(current.update))
        }
    }

    /**
     * Forgets the PC's offer and the last check, and stops what is under way: the app was paired
     * with another PC, or none. The library then asks the new one at once.
     */
    fun reset() {
        endAttempt(UpdateState.Unknown)
        lastCheck = null
        askFirst = false
    }

    /** Ends the current attempt and sets [state]; gives up the install it left waiting for the user, if any. */
    private fun endAttempt(state: UpdateState) {
        var ended: UpdateState? = null
        attempts.next {
            ended = mutableState.value
            mutableState.value = state
        }
        job?.cancel()
        val installing = ended as? UpdateState.Installing ?: return
        scope.launch(Dispatchers.IO) { installer.abandon(installing.sessionId) }
    }

    /** Sets [state] unless the attempt [id] was canceled or replaced since. */
    private fun setFor(id: Int, state: UpdateState) {
        attempts.ifCurrent(id) { mutableState.value = state }
    }

    /**
     * Asks the PC which update it offers, for the attempt [id]: [UpdateState.Available],
     * [UpdateState.UpToDate], [UpdateState.CheckFailed], or [UpdateState.Unknown] without a PC;
     * null if the attempt ended first.
     */
    private suspend fun askPc(id: Int): UpdateState? {
        val server = settings.current().server ?: return UpdateState.Unknown
        // Not before: once paired, the library asks at once.
        if (!attempts.ifCurrent(id) { lastCheck = clock.instant() }) return null
        val health = try {
            api(server).health()
        } catch (e: ApiException) {
            Log.i(TAG, "update check failed: ${e.message}")
            return UpdateState.CheckFailed
        }
        val update = offeredUpdate(server.baseUrl, health.apk, installer.packageName, installer.versionCode)
            ?: return UpdateState.UpToDate
        // A fresh offer: no failure behind it.
        if (!attempts.ifCurrent(id) { askFirst = false }) return null
        return UpdateState.Available(update)
    }

    /**
     * What the PC offers now, for the attempt [id] that retries [update]; null, with the state
     * set, when it offers nothing any more or cannot be asked.
     */
    private suspend fun offeredAgain(id: Int, update: AvailableUpdate): AvailableUpdate? {
        val answer = askPc(id) ?: return null
        if (answer is UpdateState.Available) {
            setFor(id, UpdateState.Downloading(answer.update, 0))
            return answer.update
        }
        // Unreachable: the banner stays, and says so.
        val unreachable = answer == UpdateState.CheckFailed
        setFor(id, if (unreachable) UpdateState.Failed(update, UpdateFailure.DOWNLOAD) else answer)
        return null
    }

    private suspend fun downloadAndInstall(id: Int, update: AvailableUpdate) {
        val file = downloadedApk(id)
        try {
            val downloaded = try {
                downloadApk(http, update, file) { received -> setFor(id, UpdateState.Downloading(update, received)) }
            } catch (e: IOException) {
                Log.w(TAG, "update not downloaded", e)
                fail(id, update, if (e.isStorageFull()) UpdateFailure.STORAGE_FULL else UpdateFailure.DOWNLOAD)
                return
            }
            val problem = withContext(Dispatchers.IO) {
                checkDownloadedApk(
                    update,
                    downloaded.sha256,
                    downloaded.size,
                    installer.archiveFacts(file),
                    installer.packageName,
                    installer.versionCode,
                    installer.signers(),
                )
            }
            if (problem != null) {
                fail(id, update, problem)
                return
            }
            withContext(Dispatchers.IO) { commit(id, update, file) }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // The installer's session: IOException, SecurityException...
            Log.w(TAG, "update not installed", e)
            fail(id, update, if (e.isStorageFull()) UpdateFailure.STORAGE_FULL else UpdateFailure.INSTALL, e.message)
        } finally {
            // The installer keeps its own copy.
            withContext(NonCancellable + Dispatchers.IO) { file.delete() }
        }
    }

    private fun fail(id: Int, update: AvailableUpdate, failure: UpdateFailure, detail: String? = null) {
        attempts.ifCurrent(id) {
            askFirst = true
            mutableState.value = UpdateState.Failed(update, failure, detail)
        }
    }

    /**
     * Hands [file], [update]'s APK, to Android's installer, which reports to
     * [UpdateInstallReceiver], unless the attempt [id] was canceled meanwhile. A session that is
     * not committed is abandoned: its copy of the APK does not stay behind.
     */
    private fun commit(id: Int, update: AvailableUpdate, file: File) {
        val sessionId = installer.createSession(file)
        try {
            // Set first, so that the installer's report finds the session it is about. A cancel
            // that comes before commits nothing; one that comes after sees the install and
            // abandons its session. Committed after, not as part of that step: Android may check
            // the whole APK before it returns, and a cancel would wait for it on the main thread.
            val current = attempts.ifCurrent(id) { mutableState.value = UpdateState.Installing(update, sessionId) }
            if (!current) throw CancellationException("update canceled before its install")
            installer.commit(sessionId)
        } catch (e: Exception) {
            installer.abandon(sessionId)
            throw e
        }
    }

    /**
     * Android's installer reported [status] ([PackageInstaller.EXTRA_STATUS]) for its session
     * [sessionId], with its [message] and, when it needs the user, its prompt ([confirmation]).
     * Returns whether that session is the current install: the prompt of another one, canceled,
     * is not shown.
     */
    fun onInstallResult(sessionId: Int, status: Int, message: String?, confirmation: Intent?): Boolean {
        val current = mutableState.value as? UpdateState.Installing ?: return false
        if (current.sessionId != sessionId) return false
        val result = installResult(current, status, message, confirmation)
        if (result is UpdateState.Failed) {
            Log.w(TAG, "update not installed, status $status: $message")
            askFirst = true
        }
        mutableState.value = result
        return true
    }

    private companion object {
        const val TAG = "AppUpdater"

        /** The PC is asked again when the library shows or is refreshed, at most this often. */
        val CHECK_INTERVAL: Duration = Duration.ofHours(1)
    }
}

/**
 * What [installing] becomes when Android's installer reports [status] for its session, with its
 * [message] (the failure's detail) and, when it needs the user, its prompt ([confirmation]).
 */
internal fun installResult(
    installing: UpdateState.Installing,
    status: Int,
    message: String?,
    confirmation: Intent?,
): UpdateState {
    val update = installing.update
    return when (status) {
        PackageInstaller.STATUS_PENDING_USER_ACTION -> installing.copy(confirmation = confirmation)

        // The new version replaces this process: nothing left to show.
        PackageInstaller.STATUS_SUCCESS -> UpdateState.UpToDate

        // The user said no on the system's prompt: the update is still offered.
        PackageInstaller.STATUS_FAILURE_ABORTED -> UpdateState.Available(update)

        PackageInstaller.STATUS_FAILURE_STORAGE -> UpdateState.Failed(update, UpdateFailure.STORAGE_FULL, message)

        // Including a conflict, rarely another key since the app compares them first (another
        // app's permission or provider...), and an incompatible APK (ABI, Android version).
        else -> UpdateState.Failed(update, UpdateFailure.INSTALL, message)
    }
}
