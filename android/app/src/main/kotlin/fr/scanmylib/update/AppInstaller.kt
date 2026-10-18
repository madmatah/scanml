package fr.scanmylib.update

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import fr.scanmylib.BuildConfig
import java.io.File
import java.security.MessageDigest

/**
 * What [AppUpdater] needs of Android: the installed app, its access to "Install unknown apps",
 * what an APK says of itself, and the sessions of Android's installer. All but [canInstall]
 * are called off the main thread.
 */
interface AppInstaller {
    /** The installed app's application id. */
    val packageName: String

    /** The installed app's versionCode. */
    val versionCode: Long

    /** The SHA-256 of the installed app's signing certificates; null where Android does not report them (before 9). */
    fun signers(): Set<String>?

    /** Whether Android allows the app to install apps; its system page grants it. */
    fun canInstall(): Boolean

    /** What the APK [file] says of itself; null if Android cannot read it. */
    fun archiveFacts(file: File): ApkFacts?

    /** Copies the APK [file] into a new session of Android's installer; returns its id, and leaves none on failure. */
    fun createSession(file: File): Int

    /** Commits the session [sessionId]: the installer then reports to [UpdateInstallReceiver]. */
    fun commit(sessionId: Int)

    /** Gives up the session [sessionId] and its copy of the APK, unless it is already gone. */
    fun abandon(sessionId: Int)

    /** Whether the session [sessionId] still exists: gone once the install ended, either way. */
    fun hasSession(sessionId: Int): Boolean
}

/** [AppInstaller] on the phone: [PackageManager] and its [PackageInstaller]. */
class AndroidInstaller(private val context: Context) : AppInstaller {
    private val packageManager get() = context.packageManager
    private val installer get() = packageManager.packageInstaller

    override val packageName: String get() = context.packageName

    override val versionCode: Long get() = BuildConfig.VERSION_CODE.toLong()

    override fun signers(): Set<String>? = try {
        val info = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            packageManager.getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(SIGNING_FLAGS.toLong()))
        } else {
            packageManager.getPackageInfo(packageName, SIGNING_FLAGS)
        }
        signersOf(info)
    } catch (e: PackageManager.NameNotFoundException) {
        null
    }

    override fun canInstall(): Boolean = packageManager.canRequestPackageInstalls()

    override fun archiveFacts(file: File): ApkFacts? {
        val info = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            packageManager.getPackageArchiveInfo(file.path, PackageManager.PackageInfoFlags.of(SIGNING_FLAGS.toLong()))
        } else {
            @Suppress("DEPRECATION")
            packageManager.getPackageArchiveInfo(file.path, SIGNING_FLAGS)
        } ?: return null
        return ApkFacts(info.packageName, versionCodeOf(info), signersOf(info))
    }

    override fun createSession(file: File): Int {
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(packageName)
            setSize(file.length())
        }
        val sessionId = installer.createSession(params)
        try {
            installer.openSession(sessionId).use { session ->
                file.inputStream().use { input ->
                    session.openWrite("scanmylib.apk", 0, file.length()).use { output ->
                        input.copyTo(output)
                        session.fsync(output)
                    }
                }
            }
        } catch (e: Exception) {
            abandon(sessionId)
            throw e
        }
        return sessionId
    }

    override fun commit(sessionId: Int) {
        // Mutable: the installer adds the status, and the confirmation to show the user.
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0
        val result = PendingIntent.getBroadcast(
            context,
            sessionId,
            Intent(context, UpdateInstallReceiver::class.java).setPackage(packageName),
            flags,
        )
        installer.openSession(sessionId).use { it.commit(result.intentSender) }
    }

    override fun abandon(sessionId: Int) {
        try {
            installer.abandonSession(sessionId)
        } catch (e: SecurityException) {
            // Already committed, or gone.
            Log.i(TAG, "session $sessionId not abandoned: ${e.message}")
        }
    }

    override fun hasSession(sessionId: Int): Boolean = installer.getSessionInfo(sessionId) != null

    private fun versionCodeOf(info: PackageInfo): Long = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        info.longVersionCode
    } else {
        @Suppress("DEPRECATION")
        info.versionCode.toLong()
    }

    /** The SHA-256 of the signing certificates, or null where Android does not report them (before 9). */
    private fun signersOf(info: PackageInfo): Set<String>? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return null
        val signatures = info.signingInfo?.apkContentsSigners ?: return null
        return signatures.mapTo(HashSet()) { signature ->
            MessageDigest.getInstance("SHA-256").digest(signature.toByteArray()).joinToString("") { "%02x".format(it) }
        }
    }

    private companion object {
        const val TAG = "AndroidInstaller"

        val SIGNING_FLAGS =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) PackageManager.GET_SIGNING_CERTIFICATES else 0
    }
}
