package fr.scanmylib.ui

import androidx.compose.runtime.Composable
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
import kotlinx.serialization.Serializable

@Serializable
data object PairingRoute

@Serializable
data object LibraryRoute

@Serializable
data class DocumentRoute(val documentId: String)

/** The camera screen, taking photos for a document. */
@Serializable
data class CaptureRoute(val documentId: String)

@Serializable
data object SettingsRoute

@Composable
fun ScanMyLibNavHost(navController: NavHostController, paired: Boolean) {
    // After pairing (or unpairing) the previous screens are meaningless: start a new back stack.
    fun startOver(route: Any) = navController.navigate(route) {
        popUpTo(navController.graph.id) { inclusive = true }
    }

    NavHost(navController, startDestination = if (paired) LibraryRoute else PairingRoute) {
        composable<PairingRoute> {
            PairingScreen(
                onPaired = { startOver(LibraryRoute) },
                onBack = navController.previousBackStackEntry?.let { { navController.navigateUp() } },
            )
        }
        composable<LibraryRoute> {
            LibraryScreen(
                onOpenDocument = { navController.navigate(DocumentRoute(it)) },
                onOpenSettings = { navController.navigate(SettingsRoute) },
            )
        }
        composable<DocumentRoute> { entry ->
            val documentId = entry.toRoute<DocumentRoute>().documentId
            DocumentScreen(
                onBack = { navController.navigateUp() },
                onOpenCamera = { navController.navigate(CaptureRoute(documentId)) { launchSingleTop = true } },
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
