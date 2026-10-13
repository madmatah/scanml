package fr.scanmylib.diagnostics

import android.content.Context
import android.os.Build
import com.google.android.gms.common.GoogleApiAvailabilityLight
import java.io.File
import java.time.OffsetDateTime

/**
 * Keeps the report of the last crash so that the next launch can show it.
 *
 * The app deliberately ships no crash-reporting service (nothing leaves the phone except the
 * scans sent to the user's own PC), so this is how a crash can be diagnosed: the user copies
 * the report from the dialog shown on the next launch.
 */
object CrashReporter {

    private const val FILE_NAME = "last-crash.txt"

    /** Records uncaught exceptions, then lets the previous handler end the process as usual. */
    fun install(context: Context) {
        val appContext = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching { reportFile(appContext).writeText(report(appContext, thread, error)) }
            previous?.uncaughtException(thread, error)
        }
    }

    /** The report of the last crash, or null if the app has not crashed since it was last read. */
    fun lastCrash(context: Context): String? = reportFile(context).takeIf(File::isFile)?.readText()

    fun clear(context: Context) {
        reportFile(context).delete()
    }

    private fun reportFile(context: Context) = File(context.filesDir, FILE_NAME)

    private fun report(context: Context, thread: Thread, error: Throwable): String = buildString {
        val app = runCatching { context.packageManager.getPackageInfo(context.packageName, 0) }.getOrNull()
        val playServices = runCatching { GoogleApiAvailabilityLight.getInstance().getApkVersion(context) }.getOrNull()
        appendLine("ScanMyLib ${app?.versionName}")
        appendLine("Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), ${Build.MANUFACTURER} ${Build.MODEL}")
        appendLine("Google Play services: ${playServices ?: "unknown"}")
        appendLine("Date: ${OffsetDateTime.now()}")
        appendLine("Thread: ${thread.name}")
        appendLine()
        append(error.stackTraceToString())
    }
}
