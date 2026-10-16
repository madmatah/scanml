package fr.scanmylib.update

import fr.scanmylib.api.PublishedApk
import okhttp3.HttpUrl

/** An update the PC offers: its published APK, for this app, newer than the installed one. */
data class AvailableUpdate(
    val version: String,
    val versionCode: Long,
    val sha256: String,
    val size: Long,
    /** On the paired PC, never at an address the PC's answer could name. */
    val url: HttpUrl,
)

/** Why an update was not installed. */
enum class UpdateFailure {
    /** The PC could not be reached, or stopped sending the APK. */
    DOWNLOAD,

    /** No room for the APK on the phone. */
    STORAGE_FULL,

    /** The file received is not the one the PC announced (size, SHA-256 or versionCode). */
    NOT_AS_ANNOUNCED,

    /** Android cannot read the file as an APK. */
    UNREADABLE,

    /** The APK is another app's. */
    OTHER_APP,

    /** The APK is not newer than the installed app. */
    NOT_NEWER,

    /** The APK is signed with another key: Android would refuse it as an update. */
    OTHER_SIGNER,

    /** Android's installer refused it. */
    INSTALL,
}

/** What a downloaded APK says of itself: its package, its versionCode, its signers (SHA-256). */
data class ApkFacts(val packageName: String, val versionCode: Long, val signers: Set<String>?)

private val DOWNLOAD_PATH = Regex("""/download/[A-Za-z0-9._-]{1,64}\.apk""")

/** The versions the PC may announce, shown as is; mirrors `_VERSION_NAME` in server/scanmylib/published_apk.py. */
private val VERSION_NAME = Regex("""[0-9]{1,3}\.[0-9]{1,2}\.[0-9]{1,2}""")

/** The largest APK the app downloads: far above its own size, well below a full phone. */
internal const val MAX_APK_SIZE = 512L * 1024 * 1024

/**
 * The update [apk] offers to the app [installedId] at [installedVersionCode], downloaded from
 * [server]; null when there is none: no APK, another app's (the development app and the
 * production one each check their own), not newer, or an unexpected version, size or download
 * path.
 */
fun offeredUpdate(server: HttpUrl, apk: PublishedApk?, installedId: String, installedVersionCode: Long): AvailableUpdate? {
    if (apk == null || apk.applicationId != installedId || apk.versionCode <= installedVersionCode) return null
    if (!VERSION_NAME.matches(apk.version) || apk.size !in 1..MAX_APK_SIZE) return null
    if (!DOWNLOAD_PATH.matches(apk.path)) return null
    val url = server.newBuilder().addPathSegments(apk.path.removePrefix("/")).build()
    return AvailableUpdate(apk.version, apk.versionCode, apk.sha256.lowercase(), apk.size, url)
}

/**
 * Whether the APK downloaded for [update], of [size] bytes and [sha256], may be handed to
 * Android's installer for the app [installedId] at [installedVersionCode], signed by
 * [installedSigners]; null if it may. It must be the file announced, down to its versionCode.
 * Android checks the signature again; checking it first gives a clear message instead of the
 * installer's. Signers that are unknown (null, before Android 9) are not compared.
 */
fun checkDownloadedApk(
    update: AvailableUpdate,
    sha256: String,
    size: Long,
    apk: ApkFacts?,
    installedId: String,
    installedVersionCode: Long,
    installedSigners: Set<String>?,
): UpdateFailure? = when {
    size != update.size || !sha256.equals(update.sha256, ignoreCase = true) -> UpdateFailure.NOT_AS_ANNOUNCED
    apk == null -> UpdateFailure.UNREADABLE
    apk.packageName != installedId -> UpdateFailure.OTHER_APP
    apk.versionCode <= installedVersionCode -> UpdateFailure.NOT_NEWER
    apk.versionCode != update.versionCode -> UpdateFailure.NOT_AS_ANNOUNCED
    installedSigners != null && apk.signers != null && apk.signers != installedSigners -> UpdateFailure.OTHER_SIGNER
    else -> null
}
