package fr.scanmylib

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import coil3.ImageLoader
import coil3.PlatformContext
import coil3.SingletonImageLoader
import fr.scanmylib.diagnostics.CrashReporter
import kotlinx.coroutines.launch

class ScanMyLibApplication :
    Application(),
    SingletonImageLoader.Factory {

    /**
     * Created on first use rather than in [onCreate]: WorkManager, initialized by a content provider
     * before [onCreate], may resume an interrupted upload on a background thread, and
     * [fr.scanmylib.sync.UploadWorker] can then ask for the container before [onCreate] has run.
     */
    val container: AppContainer by lazy { AppContainer(this) }

    override fun onCreate() {
        super.onCreate()
        CrashReporter.install(this)
        // Coming back to the app is a good time to retry: the phone may be home, the PC switched on.
        ProcessLifecycleOwner.get().lifecycle.addObserver(
            object : DefaultLifecycleObserver {
                override fun onStart(owner: LifecycleOwner) {
                    container.applicationScope.launch { container.syncScheduler.requestSyncIfPending() }
                }
            },
        )
    }

    override fun newImageLoader(context: PlatformContext): ImageLoader = container.imageLoader
}
