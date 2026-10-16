package fr.scanmylib.ui

import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.compose.dropUnlessResumed
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import fr.scanmylib.AppContainer
import fr.scanmylib.ScanMyLibApplication
import fr.scanmylib.ui.capture.CaptureScreen
import fr.scanmylib.ui.document.DocumentScreen
import fr.scanmylib.ui.library.LibraryScreen
import fr.scanmylib.ui.pairing.PairingScreen
import fr.scanmylib.ui.settings.SettingsScreen
import fr.scanmylib.ui.share.ShareScreen
import kotlinx.serialization.Serializable

@Serializable
data object PairingRoute

@Serializable
data object LibraryRoute

/** A document; [importShared]: the photos shared with the app join its run once it opens. */
@Serializable
data class DocumentRoute(val documentId: String, val importShared: Boolean = false)

/** "Add to…": choosing the document that receives photos shared from another app. */
@Serializable
data object ShareRoute

/** The camera screen, taking photos for a document. */
@Serializable
data class CaptureRoute(val documentId: String)

@Serializable
data object SettingsRoute

/**
 * The app's screens. When the app was opened to receive photos shared from another app, [share]
 * holds them (empty if none can be read), and the screens lead to the document that receives them
 * instead of the library; leaving the last screen ([onExit]) returns to the app that shared them.
 */
@Composable
fun ScanMyLibNavHost(navController: NavHostController, paired: Boolean, share: List<Uri>?, onExit: () -> Unit) {
    // After pairing (or unpairing) the previous screens are meaningless: start a new back stack.
    fun startOver(route: Any) = navController.navigate(route) {
        popUpTo(navController.graph.id) { inclusive = true }
    }
    val home: Any = if (share != null) ShareRoute else LibraryRoute

    NavHost(navController, startDestination = if (paired) home else PairingRoute) {
        composable<PairingRoute> {
            PairingScreen(
                onPaired = { startOver(home) },
                onBack = navController.previousBackStackEntry?.let { { navController.navigateUp() } },
            )
        }
        composable<LibraryRoute> {
            LibraryScreen(
                onOpenDocument = { navController.navigate(DocumentRoute(it)) },
                onOpenSettings = { navController.navigate(SettingsRoute) },
            )
        }
        composable<ShareRoute> { entry ->
            ShareScreen(
                photoCount = share.orEmpty().size,
                // The document takes the place of the choice: Back from it returns to the sharing app.
                // Once only: a second tap would import the photos twice.
                onChoose = { id ->
                    if (entry.lifecycle.currentState == Lifecycle.State.RESUMED) {
                        navController.navigate(DocumentRoute(id, importShared = true)) {
                            popUpTo<ShareRoute> { inclusive = true }
                        }
                    }
                },
                onClose = onExit,
            )
        }
        composable<DocumentRoute> { entry ->
            val route = entry.toRoute<DocumentRoute>()
            DocumentScreen(
                // Alone on the back stack (shared photos), navigateUp would open the app's start screen
                // in a new task: Back returns to the app that shared them instead.
                onBack = { if (navController.previousBackStackEntry != null) navController.navigateUp() else onExit() },
                onOpenCamera = { navController.navigate(CaptureRoute(route.documentId)) { launchSingleTop = true } },
                sharedPhotos = if (route.importShared) share.orEmpty() else emptyList(),
            )
        }
        composable<CaptureRoute> {
            // Once only, even if "Done" is tapped twice: the document screen must stay.
            CaptureScreen(onClose = dropUnlessResumed { navController.navigateUp() })
        }
        composable<SettingsRoute> {
            SettingsScreen(
                onBack = { navController.navigateUp() },
                onChangeServer = { navController.navigate(PairingRoute) },
                onUnpaired = { startOver(PairingRoute) },
            )
        }
    }
}

/** The app container, for the `viewModelFactory` initializers of the screens. */
val CreationExtras.container: AppContainer
    get() = (checkNotNull(this[APPLICATION_KEY]) as ScanMyLibApplication).container
