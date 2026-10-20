package fr.scanmylib.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelected
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import fr.scanmylib.ui.hasRole
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
class SettingRowsTest {
    @RunWith(Enclosed::class)
    class TheSettingSwitchRowFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsSettingIsOff {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheRow() {
                compose.setContent {
                    ScanMyLibTheme {
                        SettingSwitchRow(LABEL, checked = false, onCheckedChange = {}, description = HELP)
                    }
                }
            }

            @Test
            fun `should name its switch by its label`() {
                compose.onNode(hasRole(Role.Switch)).assert(hasText(LABEL))
            }

            @Test
            fun `should read its switch as off`() {
                compose.onNode(hasRole(Role.Switch)).assertIsOff()
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsSettingIsOffAndItsLabelIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var changes: MutableList<Boolean>

            @Before
            fun tapTheLabel() {
                changes = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        SettingSwitchRow(LABEL, checked = false, onCheckedChange = changes::add, description = HELP)
                    }
                }
                compose.onNodeWithText(LABEL, useUnmergedTree = true).performClick()
            }

            @Test
            fun `should turn the setting on, since the whole row is the target`() {
                assertEquals(listOf(true), changes)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsRowIsDisabledAndTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var changes: MutableList<Boolean>

            @Before
            fun tapTheLabel() {
                changes = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        SettingSwitchRow(LABEL, checked = false, onCheckedChange = changes::add, enabled = false)
                    }
                }
                compose.onNodeWithText(LABEL, useUnmergedTree = true).performClick()
            }

            @Test
            fun `should leave the setting as it is`() {
                assertEquals(emptyList<Boolean>(), changes)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheChoiceRowFunction {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenItsChoiceIsSelected {
            @get:Rule
            val compose = createComposeRule()

            @Before
            fun drawTheChoices() {
                compose.setContent {
                    ScanMyLibTheme {
                        Column(Modifier.selectableGroup()) {
                            ChoiceRow(LABEL, selected = true, onSelect = {}, description = HELP)
                            ChoiceRow(OTHER_LABEL, selected = false, onSelect = {})
                        }
                    }
                }
            }

            @Test
            fun `should read as a selected radio button named by its label`() {
                compose.onNode(hasRole(Role.RadioButton) and isSelected()).assert(hasText(LABEL))
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheLabelOfAnotherChoiceIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var choices: MutableList<String>

            @Before
            fun tapTheOtherLabel() {
                choices = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        Column(Modifier.selectableGroup()) {
                            ChoiceRow(LABEL, selected = true, onSelect = { choices += LABEL })
                            ChoiceRow(OTHER_LABEL, selected = false, onSelect = { choices += OTHER_LABEL })
                        }
                    }
                }
                compose.onNodeWithText(OTHER_LABEL, useUnmergedTree = true).performClick()
            }

            @Test
            fun `should select it, since the whole row is the target`() {
                assertEquals(listOf(OTHER_LABEL), choices)
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenADisabledChoiceIsTapped {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var choices: MutableList<String>

            @Before
            fun tapTheDisabledChoice() {
                choices = mutableListOf()
                compose.setContent {
                    ScanMyLibTheme {
                        Column(Modifier.selectableGroup()) {
                            ChoiceRow(LABEL, selected = true, onSelect = { choices += LABEL })
                            ChoiceRow(
                                OTHER_LABEL,
                                selected = false,
                                onSelect = { choices += OTHER_LABEL },
                                enabled = false,
                            )
                        }
                    }
                }
                compose.onNodeWithText(OTHER_LABEL, useUnmergedTree = true).performClick()
            }

            @Test
            fun `should keep the current choice`() {
                assertEquals(emptyList<String>(), choices)
            }
        }
    }
}

private const val LABEL = "Wi-Fi only"
private const val OTHER_LABEL = "Any network"
private const val HELP = "Waits for a Wi-Fi network to upload the pages"
