package fr.scanmylib.diagnostics

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class CrashReportsTest {
    @RunWith(Enclosed::class)
    class TheUnseenMethod {
        class WhenNoCrashWasReported {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var launch: NextLaunch

            @Before
            fun launchTheApp() {
                launch = NextLaunch(reportToShow = CrashReports(folder.root).unseen())
            }

            @Test
            fun `should find no report to show`() {
                assertNull(launch.reportToShow)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheWriteMethod {
        class WhenTheAppCrashes {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var launch: NextLaunch

            @Before
            fun crash() {
                val reports = CrashReports(folder.root)
                writeTheFirstCrash(reports)
                launch = NextLaunch(reportToShow = reports.unseen())
            }

            @Test
            fun `should show the report at the next launch`() {
                assertEquals(FIRST_CRASH, launch.reportToShow)
            }
        }

        class WhenTheAppCrashesAgainAfterTheReportWasShown {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var launch: NextLaunch

            @Before
            fun crashAgain() {
                val reports = CrashReports(folder.root)
                writeTheFirstCrash(reports)
                showTheReport(reports)
                writeTheSecondCrash(reports)
                launch = NextLaunch(reportToShow = reports.unseen())
            }

            @Test
            fun `should show the new report at the next launch`() {
                assertEquals(SECOND_CRASH, launch.reportToShow)
            }
        }

        class WhenTheAppCrashesAfterAMarkWithoutReport {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var launch: NextLaunch

            @Before
            fun crash() {
                val reports = CrashReports(folder.root)
                showTheReport(reports)
                writeTheFirstCrash(reports)
                launch = NextLaunch(reportToShow = reports.unseen())
            }

            @Test
            fun `should show the report at the next launch, since a mark without a report hides no later crash`() {
                assertEquals(FIRST_CRASH, launch.reportToShow)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheMarkSeenMethod {
        class WhenTheReportIsShownAtLaunch {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var launch: NextLaunch
            private lateinit var about: AboutScreen

            @Before
            fun showTheReportAtLaunch() {
                val reports = CrashReports(folder.root)
                writeTheFirstCrash(reports)
                showTheReport(reports)
                launch = NextLaunch(reportToShow = reports.unseen())
                about = AboutScreen(report = CrashReports(folder.root).read())
            }

            @Test
            fun `should not show it again at the next launch`() {
                assertNull(launch.reportToShow)
            }

            @Test
            fun `should keep it, for About to show`() {
                assertEquals(FIRST_CRASH, about.report)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDeleteMethod {
        class WhenTheAppCrashedAgainAfterTheReportWasShown {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var launch: NextLaunch
            private lateinit var about: AboutScreen

            @Before
            fun deleteTheReport() {
                val reports = CrashReports(folder.root)
                writeTheFirstCrash(reports)
                showTheReport(reports)
                writeTheSecondCrash(reports)
                deleteTheReports(reports)
                launch = NextLaunch(reportToShow = reports.unseen())
                about = AboutScreen(report = reports.read())
            }

            @Test
            fun `should leave no report to show at the next launch`() {
                assertNull(launch.reportToShow)
            }

            @Test
            fun `should leave no report for About to show`() {
                assertNull(about.report)
            }
        }
    }
}

private const val FIRST_CRASH = "first crash"
private const val SECOND_CRASH = "second crash"

private data class NextLaunch(val reportToShow: String?)

private data class AboutScreen(val report: String?)

private fun writeTheFirstCrash(reports: CrashReports) {
    reports.write(FIRST_CRASH)
}

private fun showTheReport(reports: CrashReports) {
    reports.markSeen()
}

private fun writeTheSecondCrash(reports: CrashReports) {
    reports.write(SECOND_CRASH)
}

private fun deleteTheReports(reports: CrashReports) {
    reports.delete()
}
