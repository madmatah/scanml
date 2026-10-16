package fr.scanmylib.settings

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import fr.scanmylib.model.ScanSource
import fr.scanmylib.model.ScannerMode
import fr.scanmylib.model.ServerConfig
import java.io.IOException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

data class AppSettings(
    /** The paired server, null until pairing. */
    val server: ServerConfig?,
    /** Upload only on unmetered networks (Wi-Fi). */
    val wifiOnly: Boolean,
    /** Keep the scans on the phone after their upload. */
    val keepLocalCopies: Boolean,
    /** How much Google's document scanner retouches the pages. */
    val scannerMode: ScannerMode,
    /**
     * The camera the "Scan" action opens: Google's scanner or the app's camera, never the photo
     * picker, which has its own action ("Import").
     */
    val defaultCamera: ScanSource,
    /** Google's scanner failed to start on this phone, and has not started since. */
    val googleScannerUnavailable: Boolean,
)

/**
 * App settings, stored with DataStore in the app's private storage (excluded from backups, see
 * `data_extraction_rules.xml`, since it holds the server token).
 */
class SettingsRepository(private val dataStore: DataStore<Preferences>) {

    val settings: Flow<AppSettings> = dataStore.data
        .catch { e -> if (e is IOException) emit(emptyPreferences()) else throw e }
        .map { preferences ->
            AppSettings(
                server = serverOf(preferences),
                wifiOnly = preferences[WIFI_ONLY] ?: false,
                keepLocalCopies = preferences[KEEP_LOCAL_COPIES] ?: false,
                scannerMode = storedEnum(preferences[SCANNER_MODE], ScannerMode.DEFAULT),
                // Before "Import" had its own action, this was the source of the last run: a stored
                // photo picker leaves the default camera.
                defaultCamera = storedEnum(preferences[SCAN_SOURCE], ScanSource.DEFAULT)
                    .takeIf { it.isCamera } ?: ScanSource.DEFAULT,
                googleScannerUnavailable = preferences[GOOGLE_SCANNER_UNAVAILABLE] ?: false,
            )
        }
        .distinctUntilChanged()

    suspend fun current(): AppSettings = settings.first()

    /**
     * Stores the pairing with [server]. Returns true when the cached library belongs to another
     * server (the phone was paired with a different one before).
     */
    suspend fun pair(server: ServerConfig): Boolean {
        val url = server.baseUrl.toString()
        var libraryFromOtherServer = false
        dataStore.edit {
            libraryFromOtherServer = it[LIBRARY_SERVER_URL].let { previous -> previous != null && previous != url }
            it[SERVER_URL] = url
            it[TOKEN] = server.token
            it[LIBRARY_SERVER_URL] = url
        }
        return libraryFromOtherServer
    }

    suspend fun unpair() {
        dataStore.edit {
            it.remove(SERVER_URL)
            it.remove(TOKEN)
        }
    }

    suspend fun setWifiOnly(enabled: Boolean) {
        dataStore.edit { it[WIFI_ONLY] = enabled }
    }

    suspend fun setKeepLocalCopies(enabled: Boolean) {
        dataStore.edit { it[KEEP_LOCAL_COPIES] = enabled }
    }

    suspend fun setScannerMode(mode: ScannerMode) {
        dataStore.edit { it[SCANNER_MODE] = mode.name }
    }

    /** Choosing Google's scanner also gives it another try, if it failed to start before. */
    suspend fun setDefaultCamera(camera: ScanSource) {
        require(camera.isCamera) { "not a camera: $camera" }
        dataStore.edit {
            it[SCAN_SOURCE] = camera.name
            if (camera == ScanSource.GOOGLE_SCANNER) it[GOOGLE_SCANNER_UNAVAILABLE] = false
        }
    }

    suspend fun setGoogleScannerUnavailable(unavailable: Boolean) {
        dataStore.edit { it[GOOGLE_SCANNER_UNAVAILABLE] = unavailable }
    }

    private fun serverOf(preferences: Preferences): ServerConfig? {
        val url = preferences[SERVER_URL]?.toHttpUrlOrNull() ?: return null
        val token = preferences[TOKEN] ?: return null
        return ServerConfig(url, token)
    }

    private companion object {
        val SERVER_URL = stringPreferencesKey("server_url")
        val TOKEN = stringPreferencesKey("token")
        val WIFI_ONLY = booleanPreferencesKey("wifi_only")
        val KEEP_LOCAL_COPIES = booleanPreferencesKey("keep_local_copies")
        val SCANNER_MODE = stringPreferencesKey("scanner_mode")
        /** The default camera (named after the source of the last run, which it replaced). */
        val SCAN_SOURCE = stringPreferencesKey("scan_source")
        val GOOGLE_SCANNER_UNAVAILABLE = booleanPreferencesKey("google_scanner_unavailable")

        /** Server whose documents are cached; kept when unpairing, to detect a change of server. */
        val LIBRARY_SERVER_URL = stringPreferencesKey("library_server_url")
    }
}

/**
 * The constant of [E] stored under its name, or [default] when there is none or the name is
 * unknown (renamed since, or written by a newer version of the app).
 */
internal inline fun <reified E : Enum<E>> storedEnum(name: String?, default: E): E =
    enumValues<E>().firstOrNull { it.name == name } ?: default
