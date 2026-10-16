package fr.scanmylib.diagnostics

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class CrashReportsTest {

    @get:Rule
    val folder = TemporaryFolder()

    @Test
    fun `a report shows at the next launch, then stays until deleted`() {
        val reports = CrashReports(folder.root)
        assertNull(reports.unseen())
        reports.write("first crash")
        assertEquals("first crash", reports.unseen())

        // Closed at the launch: not shown again, still there.
        reports.markSeen()
        assertNull(reports.unseen())
        assertEquals("first crash", CrashReports(folder.root).read())

        // A new crash shows again.
        reports.write("second crash")
        assertEquals("second crash", reports.unseen())

        reports.delete()
        assertNull(reports.read())
        assertNull(reports.unseen())
    }

    @Test
    fun `nothing to mark without a report`() {
        val reports = CrashReports(folder.root)
        reports.markSeen()
        reports.write("crash")
        assertEquals("crash", reports.unseen())
    }
}
