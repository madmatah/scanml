package fr.scanmylib.ui

import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.SemanticsNode
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import androidx.compose.ui.test.isHeading
import androidx.compose.ui.test.onNodeWithText

internal fun hasRole(role: Role): SemanticsMatcher = SemanticsMatcher.expectValue(SemanticsProperties.Role, role)

internal fun readFirstText(node: SemanticsNode): String? =
    node.config.getOrNull(SemanticsProperties.Text)?.firstOrNull()?.text

internal fun readHeadingsFromTheTop(screen: SemanticsNodeInteractionsProvider): List<String?> =
    screen.onAllNodes(isHeading()).fetchSemanticsNodes().sortedBy { it.positionInRoot.y }.map(::readFirstText)

internal fun isPoliteLiveRegion(): SemanticsMatcher =
    SemanticsMatcher.expectValue(SemanticsProperties.LiveRegion, LiveRegionMode.Polite)

internal fun isShownWholeInItsWindow(screen: SemanticsNodeInteractionsProvider, text: String): Boolean {
    val node = screen.onNodeWithText(text).fetchSemanticsNode()
    val root = generateSequence(node) { it.parent }.last().boundsInRoot
    val bounds = node.boundsInRoot
    return bounds.height > 0 && root.contains(bounds.topLeft) && bounds.bottom <= root.bottom &&
        bounds.right <= root.right
}
