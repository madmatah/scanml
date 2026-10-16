package fr.scanmylib.pairing

import fr.scanmylib.library.LibraryRepository
import fr.scanmylib.model.ServerConfig
import fr.scanmylib.settings.SettingsRepository
import fr.scanmylib.sync.SyncScheduler
import fr.scanmylib.update.AppUpdater

/** Pairs the app with a server (after [checkConnection]) or forgets it. */
class PairingManager(
    private val settings: SettingsRepository,
    private val library: LibraryRepository,
    private val syncScheduler: SyncScheduler,
    private val updates: AppUpdater,
) {
    suspend fun pair(server: ServerConfig) {
        if (settings.pair(server)) library.switchServer()
        // Uploads restart with the new server (and token), without waiting for a backoff delay.
        syncScheduler.restart()
        // The library asks this PC for updates at once: what another one offered is forgotten.
        updates.reset()
    }

    /** Forgets the server and its token; local scans stay on the phone until the next pairing. */
    suspend fun unpair() {
        syncScheduler.cancel()
        settings.unpair()
        // Nothing is downloaded any more from the PC that was paired.
        updates.reset()
    }
}
