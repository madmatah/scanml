package fr.scanmylib.ui

import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.github.takahirom.roborazzi.RobolectricDeviceQualifiers
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class ScanMyLibNavHostTest {
    @RunWith(Enclosed::class)
    class TheOpenReviewFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenADocumentIsOpenFromTheLibrary {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var screensAfterBack: List<String>

            @Before
            fun openTheReviewThenGoBack() {
                val navigation = showTheScreens(compose)
                navigation.go { navigate(DocumentRoute(DOCUMENT_ID)) }
                navigation.go { openReview(DOCUMENT_ID) }
                navigation.go { navigateUp() }
                screensAfterBack = navigation.listScreens()
            }

            @Test
            fun `should return to the document on Back, never to the library`() {
                assertEquals(listOf(LIBRARY, DOCUMENT), screensAfterBack)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheCloseCameraFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenOpenedFromTheDocumentWithPhotosKept {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var screens: List<String>

            @Before
            fun closeTheCamera() {
                val navigation = showTheScreens(compose)
                navigation.go { navigate(DocumentRoute(DOCUMENT_ID)) }
                navigation.go { navigate(CaptureRoute(DOCUMENT_ID)) }
                navigation.go { closeCamera(DOCUMENT_ID, werePhotosKept = true) }
                screens = navigation.listScreens()
            }

            @Test
            fun `should put the review in its place, so that the photos are checked before they are sent`() {
                assertEquals(listOf(LIBRARY, DOCUMENT, REVIEW), screens)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenOpenedFromTheDocumentWithNoneKept {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var screens: List<String>

            @Before
            fun closeTheCamera() {
                val navigation = showTheScreens(compose)
                navigation.go { navigate(DocumentRoute(DOCUMENT_ID)) }
                navigation.go { navigate(CaptureRoute(DOCUMENT_ID)) }
                navigation.go { closeCamera(DOCUMENT_ID, werePhotosKept = false) }
                screens = navigation.listScreens()
            }

            @Test
            fun `should return to the document, since there is nothing to review`() {
                assertEquals(listOf(LIBRARY, DOCUMENT), screens)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenOpenedFromTheReview {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var screens: List<String>

            @Before
            fun closeTheCamera() {
                val navigation = showTheScreens(compose)
                navigation.go { navigate(DocumentRoute(DOCUMENT_ID)) }
                navigation.go { openReview(DOCUMENT_ID) }
                navigation.go { navigate(CaptureRoute(DOCUMENT_ID)) }
                navigation.go { closeCamera(DOCUMENT_ID, werePhotosKept = true) }
                screens = navigation.listScreens()
            }

            @Test
            fun `should return to the review, once`() {
                assertEquals(listOf(LIBRARY, DOCUMENT, REVIEW), screens)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheCloseCameraIfResumedFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheCameraIsResumed {
            @get:Rule
            val compose = createComposeRule()

            private var isClosed by Delegates.notNull<Boolean>()
            private lateinit var screens: List<String>

            @Before
            fun closeTheCamera() {
                val navigation = showTheScreens(compose)
                navigation.go { navigate(DocumentRoute(DOCUMENT_ID)) }
                navigation.go { navigate(CaptureRoute(DOCUMENT_ID)) }
                val camera = navigation.ask { requireNotNull(currentBackStackEntry) { "the camera is open" } }
                isClosed = navigation.ask { closeCameraIfResumed(camera, DOCUMENT_ID, werePhotosKept = false) }
                screens = navigation.listScreens()
            }

            @Test
            fun `should say that it closed the camera, so that the close is not tried again`() {
                assertTrue(isClosed)
            }

            @Test
            fun `should close the camera`() {
                assertEquals(listOf(LIBRARY, DOCUMENT), screens)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36], qualifiers = RobolectricDeviceQualifiers.MediumPhone)
        class WhenTheCameraIsClosedAlready {
            @get:Rule
            val compose = createComposeRule()

            private var isClosedAgain by Delegates.notNull<Boolean>()
            private lateinit var screens: List<String>

            @Before
            fun closeTheCameraTwice() {
                val navigation = showTheScreens(compose)
                navigation.go { navigate(DocumentRoute(DOCUMENT_ID)) }
                navigation.go { navigate(CaptureRoute(DOCUMENT_ID)) }
                val camera = navigation.ask { requireNotNull(currentBackStackEntry) { "the camera is open" } }
                isClosedAgain = navigation.ask {
                    closeCameraIfResumed(camera, DOCUMENT_ID, werePhotosKept = true)
                    closeCameraIfResumed(camera, DOCUMENT_ID, werePhotosKept = true)
                }
                screens = navigation.listScreens()
            }

            @Test
            fun `should say that it did not close it, since the camera is no longer in front`() {
                assertFalse(isClosedAgain)
            }

            @Test
            fun `should leave the screens as they are, so that a second tap on Done never opens the review twice`() {
                assertEquals(listOf(LIBRARY, DOCUMENT, REVIEW), screens)
            }
        }
    }
}

private const val DOCUMENT_ID = "3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c"
private const val LIBRARY = "library"
private const val DOCUMENT = "document"
private const val REVIEW = "review"
private const val CAMERA = "camera"

/** The app's routes, with screens that draw nothing: only where the navigation leads is under test. */
private class Navigation(private val compose: ComposeContentTestRule) {
    private val controllers = mutableListOf<NavHostController>()

    fun show() {
        compose.setContent {
            val navController = rememberNavController()
            controllers += navController
            NavHost(navController, startDestination = LibraryRoute) {
                composable<LibraryRoute> {}
                composable<DocumentRoute> {}
                composable<ReviewRoute> {}
                composable<CaptureRoute> {}
            }
        }
        compose.waitForIdle()
    }

    fun go(move: NavHostController.() -> Unit) {
        compose.runOnIdle { controllers.last().move() }
    }

    fun <Answer> ask(question: NavHostController.() -> Answer): Answer =
        compose.runOnIdle { controllers.last().question() }

    fun listScreens(): List<String> =
        compose.runOnIdle { controllers.last().currentBackStack.value.mapNotNull(::nameScreen) }
}

private fun showTheScreens(compose: ComposeContentTestRule): Navigation {
    val navigation = Navigation(compose)
    navigation.show()
    return navigation
}

private fun nameScreen(entry: NavBackStackEntry): String? = with(entry.destination) {
    when {
        hasRoute<LibraryRoute>() -> LIBRARY
        hasRoute<DocumentRoute>() -> DOCUMENT
        hasRoute<ReviewRoute>() -> REVIEW
        hasRoute<CaptureRoute>() -> CAMERA
        else -> null
    }
}
