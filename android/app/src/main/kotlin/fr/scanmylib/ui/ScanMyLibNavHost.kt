package fr.scanmylib.ui

import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider.AndroidViewModelFactory.Companion.APPLICATION_KEY
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.compose.dropUnlessResumed
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import fr.scanmylib.AppContainer
import fr.scanmylib.ScanMyLibApplication
import fr.scanmylib.model.ScanSource
import fr.scanmylib.settings.storedEnum
import fr.scanmylib.ui.capture.CaptureScreen
import fr.scanmylib.ui.document.DocumentScreen
import fr.scanmylib.ui.library.AfterCreate
import fr.scanmylib.ui.library.LibraryScreen
import fr.scanmylib.ui.library.NewDocumentScreen
import fr.scanmylib.ui.pairing.PairingScreen
import fr.scanmylib.ui.settings.SettingsScreen
import fr.scanmylib.ui.share.ShareScreen
import kotlinx.serialization.Serializable

@Serializable
data object PairingRoute

@Serializable
data object LibraryRoute

/**
 * A document. Once it opens: [importShared], the photos shared with the app join its run;
 * [scanOnOpen], its default camera opens (the library card's scan button, "Create and scan");
 * [importOnOpen], the photo picker opens ("Create and import").
 */
@Serializable
data class DocumentRoute(
    val documentId: String,
    val importShared: Boolean = false,
    val scanOnOpen: Boolean = false,
    val importOnOpen: Boolean = false,
)

/** "New document"; [forShare]: the photos shared with the app join it. */
@Serializable
data class NewDocumentRoute(val forShare: Boolean = false)

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
        composable<LibraryRoute> { entry ->
            // Once only: a second tap would open the document twice, and its camera with it.
            fun resumed() = entry.lifecycle.currentState == Lifecycle.State.RESUMED
            LibraryScreen(
                onOpenDocument = { if (resumed()) navController.navigate(DocumentRoute(it)) },
                onScanDocument = { if (resumed()) navController.navigate(DocumentRoute(it, scanOnOpen = true)) },
                onNewDocument = { if (resumed()) navController.navigate(NewDocumentRoute()) },
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
                onNewDocument = {
                    if (entry.lifecycle.currentState == Lifecycle.State.RESUMED) {
                        navController.navigate(NewDocumentRoute(forShare = true))
                    }
                },
                onClose = onExit,
            )
        }
        composable<NewDocumentRoute> { entry ->
            val forShare = entry.toRoute<NewDocumentRoute>().forShare
            NewDocumentScreen(
                forShare = forShare,
                // The document takes the place of the form, and of "Add to…" for shared photos.
                onCreated = { id, then ->
                    val route = DocumentRoute(
                        id,
                        importShared = then == AfterCreate.ADD_SHARED,
                        scanOnOpen = then == AfterCreate.SCAN,
                        importOnOpen = then == AfterCreate.IMPORT,
                    )
                    navController.navigate(route) {
                        if (forShare) popUpTo<ShareRoute> { inclusive = true } else popUpTo<NewDocumentRoute> { inclusive = true }
                    }
                },
                onCancel = { navController.navigateUp() },
            )
        }
        composable<DocumentRoute> { entry ->
            val route = entry.toRoute<DocumentRoute>()
            // The source the camera screen asked for when the camera could not open.
            val switchTo by entry.savedStateHandle.getStateFlow<String?>(KEY_SWITCH_SOURCE, null)
                .collectAsStateWithLifecycle()
            DocumentScreen(
                // Alone on the back stack (shared photos), navigateUp would open the app's start screen
                // in a new task: Back returns to the app that shared them instead.
                onBack = { if (navController.previousBackStackEntry != null) navController.navigateUp() else onExit() },
                onOpenCamera = { navController.navigate(CaptureRoute(route.documentId)) { launchSingleTop = true } },
                sharedPhotos = if (route.importShared) share.orEmpty() else emptyList(),
                scanOnOpen = route.scanOnOpen,
                importOnOpen = route.importOnOpen,
                switchToSource = switchTo?.let { storedEnum(it, ScanSource.DEFAULT) },
                onSwitchHandled = { entry.savedStateHandle[KEY_SWITCH_SOURCE] = null },
            )
        }
        composable<CaptureRoute> { entry ->
            CaptureScreen(
                // Once only, even if "Done" is tapped twice: the document screen must stay.
                onClose = dropUnlessResumed { navController.navigateUp() },
                onSwitchSource = { source ->
                    if (entry.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                        navController.previousBackStackEntry?.savedStateHandle?.set(KEY_SWITCH_SOURCE, source.name)
                        navController.navigateUp()
                    }
                },
            )
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

/** The navigation result of the camera screen: the source to open instead, by name. */
private const val KEY_SWITCH_SOURCE = "capture_switch_source"

/** The app container, for the `viewModelFactory` initializers of the screens. */
val CreationExtras.container: AppContainer
    get() = (checkNotNull(this[APPLICATION_KEY]) as ScanMyLibApplication).container
