package fr.scanmylib

import android.content.Context
import android.content.pm.PackageManager
import android.os.storage.StorageManager
import android.util.Log
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.preferencesDataStoreFile
import androidx.work.WorkManager
import coil3.ImageLoader
import coil3.disk.DiskCache
import coil3.disk.directory
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import fr.scanmylib.api.ScanMyLibApi
import fr.scanmylib.db.ScanMyLibDatabase
import fr.scanmylib.library.LibraryRepository
import fr.scanmylib.library.ScanFileStore
import fr.scanmylib.library.ScanImporter
import fr.scanmylib.library.StagingArea
import fr.scanmylib.library.recoverInterruptedSend
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.pairing.PairingManager
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.sync.PageUploader
import fr.scanmylib.sync.SyncScheduler
import fr.scanmylib.update.AndroidInstaller
import fr.scanmylib.update.AppUpdater
import java.io.File
import java.io.IOException
import java.time.Clock
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import okhttp3.OkHttpClient

/** The app's long-lived objects, created on first use (manual dependency injection). */
class AppContainer(private val context: Context) {

    val clock: Clock = Clock.systemDefaultZone()

    /** For work that must outlive the screen that started it. */
    val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val httpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .build()
    }

    val settings by lazy {
        SettingsRepository(PreferenceDataStoreFactory.create { context.preferencesDataStoreFile("settings") })
    }

    private val database by lazy { ScanMyLibDatabase.create(context) }

    private val scanFiles by lazy { ScanFileStore(File(context.filesDir, "scans")) }

    /**
     * Bytes the app can still write on the storage that holds its files, the runs included, the
     * caches the system would clear counted in; [Long.MAX_VALUE] if the system cannot tell. A
     * binder call: not on the main thread.
     */
    fun freeStorage(): Long = try {
        val storage = context.getSystemService(StorageManager::class.java)
        storage.getAllocatableBytes(storage.getUuidForPath(context.filesDir))
    } catch (e: IOException) {
        Log.w("AppContainer", "free storage unknown", e)
        Long.MAX_VALUE
    }

    /** Whether the phone has a camera, for the app's own camera screen. */
    val hasCamera: Boolean by lazy { context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) }

    /** Pages captured, scanned or imported, until the user sends them (same storage as [scanFiles]). */
    val staging by lazy {
        StagingArea(File(context.filesDir, "staging")) { journal, runDirectory ->
            recoverInterruptedSend(journal, runDirectory, scanFiles) { pageId ->
                database.pendingPageDao().get(pageId) != null
            }
        }
    }

    val syncScheduler by lazy { SyncScheduler(WorkManager.getInstance(context), settings, database) }

    val library by lazy { LibraryRepository(database, ::api, scanFiles, staging, syncScheduler, clock) }

    val scanImporter by lazy {
        ScanImporter(context, database.pendingPageDao(), scanFiles, staging, syncScheduler, clock)
    }

    val pairing by lazy { PairingManager(settings, library, syncScheduler, updates) }

    val uploader by lazy { PageUploader(settings, ::api, database, scanFiles, clock) }

    /** Loads thumbnails over the shared HTTP client, cached on disk to show documents offline. */
    val imageLoader: ImageLoader by lazy {
        ImageLoader.Builder(context)
            .components { add(OkHttpNetworkFetcherFactory(callFactory = { httpClient })) }
            .diskCache {
                DiskCache.Builder()
                    .directory(context.cacheDir.resolve("thumbnails"))
                    .maxSizeBytes(THUMBNAIL_CACHE_BYTES)
                    .build()
            }
            .build()
    }

    fun api(server: ServerConfig): ScanMyLibApi = ScanMyLibApi(httpClient, server)

    /** The app's updates, offered by the paired PC. */
    val updates by lazy {
        val downloads = File(context.cacheDir, "updates")
        AppUpdater(AndroidInstaller(context), downloads, settings, ::api, httpClient, applicationScope, clock)
    }

    private companion object {
        const val THUMBNAIL_CACHE_BYTES = 128L * 1024 * 1024
    }
}
