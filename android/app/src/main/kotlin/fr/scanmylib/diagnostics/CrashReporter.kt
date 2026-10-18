package fr.scanmylib.diagnostics

import android.content.Context
import android.os.Build
import com.google.android.gms.common.GoogleApiAvailabilityLight
import java.io.File
import java.time.OffsetDateTime

/**
 * The report of the last crash, in [directory]: shown at the next launch, then kept, until the
 * user deletes it, for "About" to show again.
 */
class CrashReports(private val directory: File) {

    private val report get() = File(directory, FILE_NAME)

    /** Present once the report was shown at a launch. */
    private val seen get() = File(directory, SEEN_NAME)

    /** Keeps [text] as the last report, to show at the next launch. */
    fun write(text: String) {
        report.writeText(text)
        seen.delete()
    }

    /** The last report, or null if there is none. */
    fun read(): String? = report.takeIf(File::isFile)?.readText()

    /** The last report if it was not shown at a launch yet. */
    fun unseen(): String? = if (seen.exists()) null else read()

    /** The report was shown: the next launches do not show it again (if this can be written). */
    fun markSeen() {
        if (report.isFile) runCatching { seen.createNewFile() }
    }

    fun delete() {
        report.delete()
        seen.delete()
    }

    private companion object {
        const val FILE_NAME = "last-crash.txt"
        const val SEEN_NAME = "last-crash.seen"
    }
}

/**
 * Keeps the report of the last crash so that the next launch can show it.
 *
 * The app deliberately ships no crash-reporting service (nothing leaves the phone except the
 * scans sent to the user's own PC), so this is how a crash can be diagnosed: the user shares or
 * copies the report from the dialog shown on the next launch, or later from "About".
 */
object CrashReporter {

    /** Records uncaught exceptions, then lets the previous handler end the process as usual. */
    fun install(context: Context) {
        val appContext = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching { reports(appContext).write(report(appContext, thread, error)) }
            previous?.uncaughtException(thread, error)
        }
    }

    fun reports(context: Context) = CrashReports(context.filesDir)

    private fun report(context: Context, thread: Thread, error: Throwable): String = buildString {
        val app = runCatching { context.packageManager.getPackageInfo(context.packageName, 0) }.getOrNull()
        val playServices = runCatching { GoogleApiAvailabilityLight.getInstance().getApkVersion(context) }.getOrNull()
        appendLine("ScanMyLib ${app?.versionName}")
        appendLine(
            "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}), ${Build.MANUFACTURER} ${Build.MODEL}",
        )
        appendLine("Google Play services: ${playServices ?: "unknown"}")
        appendLine("Date: ${OffsetDateTime.now()}")
        appendLine("Thread: ${thread.name}")
        appendLine()
        append(error.stackTraceToString())
    }
}
