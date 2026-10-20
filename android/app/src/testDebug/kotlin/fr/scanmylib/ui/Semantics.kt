package fr.scanmylib.ui

import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import androidx.compose.ui.test.isHeading

internal fun hasRole(role: Role): SemanticsMatcher = SemanticsMatcher.expectValue(SemanticsProperties.Role, role)

internal fun readFirstText(node: SemanticsNode): String? =
    node.config.getOrNull(SemanticsProperties.Text)?.firstOrNull()?.text

internal fun readHeadingsFromTheTop(screen: SemanticsNodeInteractionsProvider): List<String?> =
    screen.onAllNodes(isHeading()).fetchSemanticsNodes().sortedBy { it.positionInRoot.y }.map(::readFirstText)
