package fr.scanmylib

import android.content.Context
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
import java.io.File
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

    val pairing by lazy { PairingManager(settings, library, syncScheduler) }

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

    private companion object {
        const val THUMBNAIL_CACHE_BYTES = 128L * 1024 * 1024
    }
}
