package fr.scanmylib.ui.components

import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import fr.scanmylib.R
import fr.scanmylib.ui.theme.ScanMyLibTheme
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class BannerTest {
    @RunWith(Enclosed::class)
    class TheAttentionBannerFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsActionIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var actions: MutableList<Unit>

            @Before
            fun tapTheAction() {
                actions = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        AttentionBanner(MESSAGE, R.drawable.ic_cloud_off, ACTION, onAction = { actions += Unit })
                    }
                }
                compose.onNodeWithText(ACTION).performClick()
            }

            @Test
            fun `should take its one action`() {
                assertEquals(1, actions.size)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheErrorBannerFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsActionIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var actions: MutableList<Unit>

            @Before
            fun tapTheAction() {
                actions = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme { ErrorBanner(MESSAGE, R.drawable.ic_error, ACTION, onAction = { actions += Unit }) }
                }
                compose.onNodeWithText(ACTION).performClick()
            }

            @Test
            fun `should take its one action`() {
                assertEquals(1, actions.size)
            }
        }
    }
}

private const val MESSAGE = "PC unreachable: the pages will be sent as soon as it is back."
private const val ACTION = "Retry"
