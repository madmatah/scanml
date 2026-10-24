package fr.scanmylib.library

import java.io.File
import java.io.IOException
import java.time.Instant
import kotlin.coroutines.CoroutineContext
import kotlin.properties.Delegates
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestCoroutineScheduler
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class StagingAreaTest {
    @RunWith(Enclosed::class)
    class TheAddMethod {
        class WhenTheRunIsNew {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var added: List<StagedPage>

            @Before
            fun addTwoImages() = runTest {
                added = addTwoImagesAtOnce(StagingArea(resolveStagingRoot(folder)))
            }

            @Test
            fun `should number the pages from 1, in the order given`() {
                assertEquals(listOf(1, 2), added.map { it.seq })
            }
        }

        class WhenTheRunHasPages {
            @get:Rule
            val folder = TemporaryFolder()

            private var position by Delegates.notNull<Int>()

            @Before
            fun addAThirdImage() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                addTwoImagesAtOnce(staging)
                position = staging.shoot("c", SHOT_TIME.plusSeconds(9)).seq
            }

            @Test
            fun `should number the next page after them`() {
                assertEquals(3, position)
            }
        }

        class WhenTheProcessIsRestarted {
            @get:Rule
            val folder = TemporaryFolder()

            private var position by Delegates.notNull<Int>()

            @Before
            fun addAnImageInTheNextProcess() = runTest {
                shootTwoPages(StagingArea(resolveStagingRoot(folder)))
                position = restartTheProcess(resolveStagingRoot(folder)).shoot("c", SHOT_TIME.plusSeconds(3)).seq
            }

            @Test
            fun `should number the next page after those of the earlier process`() {
                assertEquals(3, position)
            }
        }

        class WhenAPhotoWasDeletedDuringTheRun {
            @get:Rule
            val folder = TemporaryFolder()

            private var position by Delegates.notNull<Int>()

            @Before
            fun addAnImage() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                deleteTheSecondOfThreePhotos(staging)
                position = staging.shoot("d", SHOT_TIME.plusSeconds(6)).seq
            }

            @Test
            fun `should number the next page after the last one, leaving the gap until the run is sent`() {
                assertEquals(4, position)
            }
        }

        class WhenTheLastPageWasRemoved {
            @get:Rule
            val folder = TemporaryFolder()

            private var position by Delegates.notNull<Int>()

            @Before
            fun addAnImage() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val pages = shootThreePages(staging)
                staging.remove(DOCUMENT, pages.last())
                position = staging.shoot("d", SHOT_TIME.plusSeconds(6)).seq
            }

            @Test
            fun `should number the next page after the removed one, so that it can come back to its place`() {
                assertEquals(4, position)
            }
        }

        class WhenANumberedPageWaitsInRemoved {
            @get:Rule
            val folder = TemporaryFolder()

            private var position by Delegates.notNull<Int>()

            @Before
            fun addAnImage() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val pages = shootThreePages(staging)
                staging.numberPage(DOCUMENT, pages.last(), TWELVE, nextPagesFollowOn = false)
                staging.remove(DOCUMENT, pages.last())
                position = staging.shoot("d", SHOT_TIME.plusSeconds(6)).seq
            }

            @Test
            fun `should number the next page after it, so that it can come back to its place`() {
                assertEquals(4, position)
            }
        }

        class WhenTheLastTwoPagesWereDeleted {
            @get:Rule
            val folder = TemporaryFolder()

            private var position by Delegates.notNull<Int>()

            @Before
            fun addAnImage() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                shootTwoScansAndTwoPhotos(staging)
                deleteThePhotos(staging)
                position = staging.shoot("next", SHOT_TIME.plusSeconds(4)).seq
            }

            @Test
            fun `should number the next page after the pages kept`() {
                assertEquals(3, position)
            }
        }

        class WhenTheRunWasDiscarded {
            @get:Rule
            val folder = TemporaryFolder()

            private var position by Delegates.notNull<Int>()

            @Before
            fun addAnImage() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                shootTwoPagesAndOneOfTheOtherDocument(staging)
                discardTheRun(staging)
                position = staging.shoot("c", SHOT_TIME).seq
            }

            @Test
            fun `should start a new run from 1`() {
                assertEquals(1, position)
            }
        }

        class WhenTheImageIsEmpty {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var emptyImage: File
            private lateinit var addTheImage: suspend () -> List<StagedPage>

            @Before
            fun keepTheAdd() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                emptyImage = staging.incomingFile(DOCUMENT).apply { createNewFile() }
                addTheImage = { staging.add(DOCUMENT, listOf(StagingInput(emptyImage, SHOT_TIME))) }
            }

            @Test
            fun `should refuse it, since an empty image is not a page`() = runTest {
                val failure = runCatching { addTheImage() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertEquals("empty image: $emptyImage", failure?.message)
            }
        }

        class WhenTheImageIsEmptyAndTheAddIsOver {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>

            @Before
            fun addTheImage() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val emptyImage = staging.incomingFile(DOCUMENT).apply { createNewFile() }
                runCatching { staging.add(DOCUMENT, listOf(StagingInput(emptyImage, SHOT_TIME))) }
                stagedPages = staging.pages(DOCUMENT)
            }

            @Test
            fun `should add no page`() {
                assertEquals(emptyList<StagedPage>(), stagedPages)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheObserveMethod {
        class WhenPagesWereAdded {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var observedRun: List<StagedPage>
            private lateinit var stagedPages: List<StagedPage>

            @Before
            fun observeTheRun() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                addTwoImagesAtOnce(staging)
                staging.shoot("c", SHOT_TIME.plusSeconds(9))
                observedRun = staging.observe(DOCUMENT).first()
                stagedPages = staging.pages(DOCUMENT)
            }

            @Test
            fun `should give the pages in order`() {
                assertEquals(listOf(1, 2, 3), observedRun.map { it.seq })
            }

            @Test
            fun `should give their images`() {
                assertEquals(listOf("a", "b", "c"), observedRun.map { it.file.readText() })
            }

            @Test
            fun `should give the pages the pages method gives`() {
                assertEquals(stagedPages, observedRun)
            }
        }
    }

    @RunWith(Enclosed::class)
    class ThePagesMethod {
        class WhenAnotherDocumentHasARun {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>

            @Before
            fun readTheRunOfADocumentWithoutOne() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                shootTwoPages(staging)
                stagedPages = staging.pages(OTHER_DOCUMENT)
            }

            @Test
            fun `should give no page for a document without a run`() {
                assertEquals(emptyList<StagedPage>(), stagedPages)
            }
        }

        class WhenTheProcessIsRestarted {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                staging.shoot("a", SHOT_TIME)
                staging.shoot("b", SHOT_TIME.plusMillis(1_500))
                stagedPages = restartTheProcess(resolveStagingRoot(folder)).pages(DOCUMENT)
            }

            @Test
            fun `should keep the positions of the run`() {
                assertEquals(listOf(1, 2), stagedPages.map { it.seq })
            }

            @Test
            fun `should keep the capture time of each page`() {
                assertEquals(listOf(SHOT_TIME, SHOT_TIME.plusMillis(1_500)), stagedPages.map { it.capturedAt })
            }

            @Test
            fun `should keep their images`() {
                assertEquals(listOf("a", "b"), stagedPages.map { it.file.readText() })
            }
        }

        class WhenAShotWasUnfinishedWhenTheProcessEnded {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pageContents: List<String>
            private var isUnfinishedImageKept by Delegates.notNull<Boolean>()

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                staging.shoot("a", SHOT_TIME)
                val unfinished = staging.writeAnIncomingImage("half a photo")
                pageContents = restartTheProcess(resolveStagingRoot(folder)).readContents(DOCUMENT)
                isUnfinishedImageKept = unfinished.exists()
            }

            @Test
            fun `should not take the unfinished image for a page`() {
                assertEquals(listOf("a"), pageContents)
            }

            @Test
            fun `should delete the unfinished image`() {
                assertFalse(isUnfinishedImageKept)
            }
        }

        class WhenTheProcessEndedWithAPageRemoved {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pageContents: List<String>
            private var isRemovedImageKept by Delegates.notNull<Boolean>()

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val removed = removeTheSecondOfThreePages(StagingArea(resolveStagingRoot(folder)))
                pageContents = restartTheProcess(resolveStagingRoot(folder)).readContents(DOCUMENT)
                isRemovedImageKept = isOnDisk(folder, removed)
            }

            @Test
            fun `should keep the other pages`() {
                assertEquals(listOf("a", "c"), pageContents)
            }

            @Test
            fun `should delete the removed page, whose undo ended with the process`() {
                assertFalse(isRemovedImageKept)
            }
        }

        class WhenASendWasLeftUnfinished {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var journal: File
            private lateinit var recoveredJournals: List<File>
            private lateinit var recoveredRunDirectories: List<File>
            private lateinit var pageContents: List<String>
            private var nextProcessPageCount by Delegates.notNull<Int>()

            @Before
            fun readTheRunTwice() = runTest {
                val root = resolveStagingRoot(folder)
                StagingArea(root).shoot("a", SHOT_TIME)
                journal = StagingArea(root).sendJournal(DOCUMENT).apply { writeText("journal") }
                val journals = mutableListOf<File>()
                val runDirectories = mutableListOf<File>()
                val staging = StagingArea(root) { found, runDirectory ->
                    journals += found
                    runDirectories += runDirectory
                    found.delete()
                }
                pageContents = staging.readContents(DOCUMENT)
                staging.shoot("b", SHOT_TIME)
                recoveredJournals = journals.toList()
                recoveredRunDirectories = runDirectories.toList()
                nextProcessPageCount = restartTheProcess(root).pages(DOCUMENT).size
            }

            @Test
            fun `should hand the record of the send to the recovery, once per process`() {
                assertEquals(listOf(journal), recoveredJournals)
            }

            @Test
            fun `should hand the recovery the run's directory`() {
                assertEquals(listOf(File(resolveStagingRoot(folder), DOCUMENT)), recoveredRunDirectories)
            }

            @Test
            fun `should read the run's pages once the send is recovered`() {
                assertEquals(listOf("a"), pageContents)
            }

            @Test
            fun `should keep the run whole for the next process`() {
                assertEquals(2, nextProcessPageCount)
            }
        }

        class WhenTheDocumentIdIsEmpty {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var readThePages: suspend () -> List<StagedPage>

            @Before
            fun keepTheRead() {
                val staging = StagingArea(resolveStagingRoot(folder))
                readThePages = { staging.pages("") }
            }

            @Test
            fun `should refuse it, since a document id never points outside the staging area`() = runTest {
                val failure = runCatching { readThePages() }.exceptionOrNull()
                assertTrue("$failure", failure is IllegalArgumentException)
                assertEquals("unexpected document id: ", failure?.message)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheTakeInterruptedMethod {
        class WhenAnImageIsOnItsWayInTheSameProcess {
            @get:Rule
            val folder = TemporaryFolder()

            private var isInterrupted by Delegates.notNull<Boolean>()

            @Before
            fun askWhileTheImageIsOnItsWay() = runTest {
                isInterrupted = askForInterruptedImages(leaveAnImageOnItsWay(resolveStagingRoot(folder)))
            }

            @Test
            fun `should not report it, since it is just on its way`() {
                assertFalse(isInterrupted)
            }
        }

        class WhenTheProcessEndedWithAnImageOnItsWay {
            @get:Rule
            val folder = TemporaryFolder()

            private var isReportedInTheNextProcess by Delegates.notNull<Boolean>()

            @Before
            fun askInBothProcesses() = runTest {
                askForInterruptedImages(leaveAnImageOnItsWay(resolveStagingRoot(folder)))
                isReportedInTheNextProcess = askForInterruptedImages(restartTheProcess(resolveStagingRoot(folder)))
            }

            @Test
            fun `should report it in the next process, though it was asked about while on its way`() {
                assertTrue(isReportedInTheNextProcess)
            }
        }

        class WhenTheProcessEndedWithAnImageOnItsWayAndItWasReported {
            @get:Rule
            val folder = TemporaryFolder()

            private var isInterrupted by Delegates.notNull<Boolean>()

            @Before
            fun askForInterruptedImagesAgain() = runTest {
                askForInterruptedImages(leaveAnImageOnItsWay(resolveStagingRoot(folder)))
                val restarted = restartTheProcess(resolveStagingRoot(folder))
                askForInterruptedImages(restarted)
                isInterrupted = askForInterruptedImages(restarted)
            }

            @Test
            fun `should report it only once`() {
                assertFalse(isInterrupted)
            }
        }

        class WhenTheProcessEndedWithAnImageOnItsWayInAnotherRun {
            @get:Rule
            val folder = TemporaryFolder()

            private var isInterrupted by Delegates.notNull<Boolean>()

            @Before
            fun askForInterruptedImagesOfAnotherDocument() = runTest {
                askForInterruptedImages(leaveAnImageOnItsWay(resolveStagingRoot(folder)))
                val restarted = restartTheProcess(resolveStagingRoot(folder))
                letTheNextProcessNoticeTheImageCutShort(restarted)
                isInterrupted = restarted.takeInterrupted(OTHER_DOCUMENT)
            }

            @Test
            fun `should not report it for another document`() {
                assertFalse(isInterrupted)
            }
        }

        class WhenTheProcessEndedWithAnImageOnItsWayAndTheNextOneEndedToo {
            @get:Rule
            val folder = TemporaryFolder()

            private var isInterrupted by Delegates.notNull<Boolean>()
            private lateinit var pageContents: List<String>

            @Before
            fun askForInterruptedImagesInAThirdProcess() = runTest {
                askForInterruptedImages(leaveAnImageOnItsWay(resolveStagingRoot(folder)))
                askForInterruptedImages(restartTheProcess(resolveStagingRoot(folder)))
                isInterrupted = askForInterruptedImages(restartTheProcess(resolveStagingRoot(folder)))
                pageContents = restartTheProcess(resolveStagingRoot(folder)).readContents(DOCUMENT)
            }

            @Test
            fun `should not report it again`() {
                assertFalse(isInterrupted)
            }

            @Test
            fun `should keep the pages of the run`() {
                assertEquals(listOf("a"), pageContents)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheIncomingFileMethod {
        class WhenAskedTwice {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var first: File
            private lateinit var second: File
            private var isFirstCreated by Delegates.notNull<Boolean>()

            @Before
            fun askForTwoFiles() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                first = staging.incomingFile(DOCUMENT)
                second = staging.incomingFile(DOCUMENT)
                isFirstCreated = first.exists()
            }

            @Test
            fun `should give a new file each time`() {
                assertNotEquals(first, second)
            }

            @Test
            fun `should leave the file to be written`() {
                assertFalse(isFirstCreated)
            }

            @Test
            fun `should place it among the incoming images of the document's run`() {
                assertEquals(File(resolveStagingRoot(folder), "$DOCUMENT/incoming"), first.parentFile)
            }
        }

        class WhenTheDocumentIdIsAPath {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var askForAFile: suspend () -> File

            @Before
            fun keepTheRequest() {
                val staging = StagingArea(resolveStagingRoot(folder))
                askForAFile = { staging.incomingFile("../scans") }
            }

            @Test
            fun `should refuse it, since a document id never points outside the staging area`() = runTest {
                val failure = runCatching { askForAFile() }.exceptionOrNull()
                assertTrue("$failure", failure is IllegalArgumentException)
                assertEquals("unexpected document id: ../scans", failure?.message)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheRemoveMethod {
        class WhenTheSecondOfThreePagesIsRemoved {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pageContents: List<String>
            private var isImageKept by Delegates.notNull<Boolean>()

            @Before
            fun removeIt() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val removed = removeTheSecondOfThreePages(staging)
                pageContents = staging.readContents(DOCUMENT)
                isImageKept = isOnDisk(folder, removed)
            }

            @Test
            fun `should take it out of the run, so that it is neither sent nor counted`() {
                assertEquals(listOf("a", "c"), pageContents)
            }

            @Test
            fun `should keep its image, so that the removal can be undone`() {
                assertTrue(isImageKept)
            }
        }

        class WhenThePageWasNumberedSince {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var removedFiles: List<String>
            private lateinit var numberedName: String

            @Before
            fun removeItByItsEarlierName() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val earlier = numberTheSecondOfThreePages(staging)
                numberedName = staging.pages(DOCUMENT)[1].file.name
                staging.remove(DOCUMENT, earlier)
                removedFiles = listRemovedFiles(folder)
            }

            @Test
            fun `should remove it under its new name`() {
                assertEquals(listOf(numberedName), removedFiles)
            }
        }

        class WhenTheCallerIsCanceledAsThePageMoves {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>
            private lateinit var filesOfTheRun: List<String>

            @Before
            fun removeAsTheCallerIsCanceled() = runTest {
                val disk = CancelingDisk(testScheduler)
                val staging = StagingArea(resolveStagingRoot(folder), disk)
                val pages = shootThreePages(staging)
                disk.cancelAfterItsWork(launch(start = CoroutineStart.LAZY) { staging.remove(DOCUMENT, pages[1]) })
                pagesInTheRun = staging.pages(DOCUMENT).map { it.file.name }
                filesOfTheRun = listPageFiles(folder)
            }

            @Test
            fun `should keep the run in step with its files`() {
                assertEquals(filesOfTheRun, pagesInTheRun)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheRestoreMethod {
        class WhenARemovedPageIsRestored {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pageContents: List<String>

            @Before
            fun restoreIt() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val removed = removeTheSecondOfThreePages(staging)
                staging.restore(DOCUMENT, removed)
                pageContents = staging.readContents(DOCUMENT)
            }

            @Test
            fun `should put it back in its place`() {
                assertEquals(listOf("a", "b", "c"), pageContents)
            }
        }

        class WhenANumberedPageIsRestored {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var numberings: List<PageNumbering>

            @Before
            fun restoreIt() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                numberTheSecondOfThreePages(staging)
                val numbered = staging.pages(DOCUMENT)[1]
                staging.remove(DOCUMENT, numbered)
                staging.restore(DOCUMENT, numbered)
                numberings = staging.pages(DOCUMENT).map { it.numbering }
            }

            @Test
            fun `should put it back with its number`() {
                assertEquals(listOf(PageNumbering.NotGiven, TWELVE_ALONE, PageNumbering.NotGiven), numberings)
            }
        }

        class WhenThePageWasNumberedJustBeforeItsRemoval {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var numberings: List<PageNumbering>

            @Before
            fun restoreItByItsEarlierName() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val earlier = numberTheSecondOfThreePages(staging)
                staging.remove(DOCUMENT, earlier)
                staging.restore(DOCUMENT, earlier)
                numberings = staging.pages(DOCUMENT).map { it.numbering }
            }

            @Test
            fun `should put it back with its number`() {
                assertEquals(listOf(PageNumbering.NotGiven, TWELVE_ALONE, PageNumbering.NotGiven), numberings)
            }
        }

        class WhenAPageOfTheSameNameIsThere {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var restoreThePage: suspend () -> Unit

            @Before
            fun takeItsName() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val removed = removeTheSecondOfThreePages(staging)
                removed.file.writeText("another page")
                restoreThePage = { staging.restore(DOCUMENT, removed) }
            }

            @Test
            fun `should refuse, so that no page is overwritten`() = runTest {
                val failure = runCatching { restoreThePage() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertTrue("${failure?.message}", failure?.message.orEmpty().endsWith(NAME_TAKEN))
            }
        }

        class WhenTheCallerIsCanceledAsThePageMoves {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>
            private lateinit var filesOfTheRun: List<String>

            @Before
            fun restoreAsTheCallerIsCanceled() = runTest {
                val disk = CancelingDisk(testScheduler)
                val staging = StagingArea(resolveStagingRoot(folder), disk)
                val removed = removeTheSecondOfThreePages(staging)
                disk.cancelAfterItsWork(launch(start = CoroutineStart.LAZY) { staging.restore(DOCUMENT, removed) })
                pagesInTheRun = staging.pages(DOCUMENT).map { it.file.name }
                filesOfTheRun = listPageFiles(folder)
            }

            @Test
            fun `should keep the run in step with its files`() {
                assertEquals(filesOfTheRun, pagesInTheRun)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDeleteRemovedMethod {
        class WhenARemovedPageIsDeleted {
            @get:Rule
            val folder = TemporaryFolder()

            private var isImageKept by Delegates.notNull<Boolean>()

            @Before
            fun deleteIt() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val removed = removeTheSecondOfThreePages(staging)
                staging.deleteRemoved(DOCUMENT, removed)
                isImageKept = isOnDisk(folder, removed)
            }

            @Test
            fun `should delete its image for good`() {
                assertFalse(isImageKept)
            }
        }

        class WhenThePageWasNumberedJustBeforeItsRemoval {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var removedFiles: List<String>

            @Before
            fun deleteItByItsEarlierName() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val earlier = numberTheSecondOfThreePages(staging)
                staging.remove(DOCUMENT, earlier)
                staging.deleteRemoved(DOCUMENT, earlier)
                removedFiles = listRemovedFiles(folder)
            }

            @Test
            fun `should delete its image for good, under its new name`() {
                assertEquals(emptyList<String>(), removedFiles)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDeleteMethod {
        class WhenAPhotoIsDeletedDuringTheRun {
            @get:Rule
            val folder = TemporaryFolder()

            private var isImageKept by Delegates.notNull<Boolean>()
            private lateinit var positions: List<Int>

            @Before
            fun deleteAPhoto() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val deleted = deleteTheSecondOfThreePhotos(staging)
                isImageKept = deleted.file.exists()
                positions = staging.pages(DOCUMENT).map { it.seq }
            }

            @Test
            fun `should delete its image`() {
                assertFalse(isImageKept)
            }

            @Test
            fun `should leave a gap in the positions until the run is sent`() {
                assertEquals(listOf(1, 3), positions)
            }
        }

        class WhenThePageWasNumberedSince {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pageContents: List<String>
            private lateinit var filesOfTheRun: List<String>

            @Before
            fun deleteItByItsEarlierName() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val earlier = numberTheSecondOfThreePages(staging)
                staging.delete(DOCUMENT, earlier)
                pageContents = staging.readContents(DOCUMENT)
                filesOfTheRun = listPageFiles(folder)
            }

            @Test
            fun `should take it out of the run`() {
                assertEquals(listOf("a", "c"), pageContents)
            }

            @Test
            fun `should delete its image, under its new name`() {
                assertEquals(2, filesOfTheRun.size)
            }
        }

        class WhenAPhotoWasDeletedDuringTheRunAndTheProcessRestarts {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pageContents: List<String>

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                deleteTheSecondOfThreePhotos(staging)
                staging.shoot("d", SHOT_TIME.plusSeconds(6))
                pageContents = restartTheProcess(resolveStagingRoot(folder)).readContents(DOCUMENT)
            }

            @Test
            fun `should keep the photo out of the run`() {
                assertEquals(listOf("a", "c", "d"), pageContents)
            }
        }

        class WhenTheLastPhotoIsRetaken {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pageContents: List<String>

            @Before
            fun retakeTheLastPhoto() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                staging.shoot("a", SHOT_TIME)
                staging.delete(DOCUMENT, staging.shoot("blurred b", SHOT_TIME.plusSeconds(2)))
                staging.shoot("b", SHOT_TIME.plusSeconds(5))
                pageContents = restartTheProcess(resolveStagingRoot(folder)).readContents(DOCUMENT)
            }

            @Test
            fun `should keep the order of the run`() {
                assertEquals(listOf("a", "b"), pageContents)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDiscardMethod {
        class WhenTheRunHasPages {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var imagesKept: List<File>
            private lateinit var nextProcessPages: List<StagedPage>
            private var nextProcessOtherPageCount by Delegates.notNull<Int>()

            @Before
            fun discardTheRun() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val discarded = shootTwoPagesAndOneOfTheOtherDocument(staging)
                discardTheRun(staging)
                stagedPages = staging.pages(DOCUMENT)
                imagesKept = discarded.map { it.file }.filter { it.exists() }
                nextProcessPages = restartTheProcess(resolveStagingRoot(folder)).pages(DOCUMENT)
                nextProcessOtherPageCount = restartTheProcess(resolveStagingRoot(folder)).pages(OTHER_DOCUMENT).size
            }

            @Test
            fun `should leave no page in the run`() {
                assertEquals(emptyList<StagedPage>(), stagedPages)
            }

            @Test
            fun `should delete its photos`() {
                assertEquals(emptyList<File>(), imagesKept)
            }

            @Test
            fun `should leave no page for the next process`() {
                assertEquals(emptyList<StagedPage>(), nextProcessPages)
            }

            @Test
            fun `should keep the runs of other documents`() {
                assertEquals(1, nextProcessOtherPageCount)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSendMethod {
        class WhenTheSenderHandsEveryPageOver {
            @get:Rule
            val folder = TemporaryFolder()

            private var sentCount by Delegates.notNull<Int>()
            private lateinit var stagedPages: List<StagedPage>
            private var hasRunDirectory by Delegates.notNull<Boolean>()
            private lateinit var nextProcessPages: List<StagedPage>
            private lateinit var outboxFiles: List<String>

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                staging.shoot("a", SHOT_TIME)
                staging.shoot("b", SHOT_TIME)
                val outbox = folder.newFolder("outbox")
                sentCount = staging.send(DOCUMENT) { run ->
                    run.forEach { it.file.renameTo(File(outbox, it.file.name)) }
                    run.size
                }
                stagedPages = staging.pages(DOCUMENT)
                hasRunDirectory = File(resolveStagingRoot(folder), DOCUMENT).exists()
                nextProcessPages = restartTheProcess(resolveStagingRoot(folder)).pages(DOCUMENT)
                outboxFiles = outbox.list().orEmpty().toList()
            }

            @Test
            fun `should give what the sender gives`() {
                assertEquals(2, sentCount)
            }

            @Test
            fun `should hand every page to the sender`() {
                assertEquals(2, outboxFiles.size)
            }

            @Test
            fun `should leave no page in the run`() {
                assertEquals(emptyList<StagedPage>(), stagedPages)
            }

            @Test
            fun `should delete the run's directory`() {
                assertFalse(hasRunDirectory)
            }

            @Test
            fun `should leave no page for the next process`() {
                assertEquals(emptyList<StagedPage>(), nextProcessPages)
            }
        }

        class WhenAPageWasRemoved {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var handedOver: List<String>

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                removeTheSecondOfThreePages(staging)
                handedOver = staging.send(DOCUMENT) { run -> run.map { it.file.readText() } }
            }

            @Test
            fun `should hand over only the pages of the run`() {
                assertEquals(listOf("a", "c"), handedOver)
            }
        }

        class WhenTheSenderFails {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var sendTheRun: suspend () -> Unit

            @Before
            fun keepTheSend() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                shootTwoPages(staging)
                sendTheRun = { staging.send(DOCUMENT) { throw IOException(DATABASE_FULL) } }
            }

            @Test
            fun `should fail with the sender's error`() = runTest {
                val failure = runCatching { sendTheRun() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertEquals(DATABASE_FULL, failure?.message)
            }
        }

        class WhenTheSenderFailsAndTheSendIsOver {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesBefore: List<StagedPage>
            private lateinit var pagesAfter: List<StagedPage>
            private lateinit var imagesLost: List<File>

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                pagesBefore = shootTwoPages(staging)
                runCatching { staging.send(DOCUMENT) { throw IOException(DATABASE_FULL) } }
                pagesAfter = staging.pages(DOCUMENT)
                imagesLost = pagesBefore.map { it.file }.filterNot { it.exists() }
            }

            @Test
            fun `should leave the run as it was`() {
                assertEquals(pagesBefore, pagesAfter)
            }

            @Test
            fun `should keep its images`() {
                assertEquals(emptyList<File>(), imagesLost)
            }
        }

        class WhenTheSenderFailsAfterMovingSomePages {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var sendTheRun: suspend () -> Unit

            @Before
            fun keepTheSend() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val (first) = shootTwoPages(staging)
                val outbox = folder.newFolder("outbox")
                sendTheRun = { staging.send(DOCUMENT) { moveThenFail(first, outbox) } }
            }

            @Test
            fun `should fail with the sender's error`() = runTest {
                val failure = runCatching { sendTheRun() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertEquals(INTERRUPTED, failure?.message)
            }
        }

        class WhenTheSenderFailsAfterMovingSomePagesAndTheSendIsOver {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var notMoved: StagedPage
            private lateinit var stagedPages: List<StagedPage>

            @Before
            fun sendTheRun() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val (first, second) = shootTwoPages(staging)
                notMoved = second
                val outbox = folder.newFolder("outbox")
                runCatching { staging.send(DOCUMENT) { moveThenFail(first, outbox) } }
                stagedPages = staging.pages(DOCUMENT)
            }

            @Test
            fun `should keep in the run the pages it did not move`() {
                assertEquals(listOf(notMoved), stagedPages)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheNumberPageMethod {
        class WhenTheFirstOfThreePagesGets12WithTheNextPages {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var stagedPages: List<StagedPage>
            private lateinit var filesOfTheRun: List<String>
            private lateinit var pagesInTheRun: List<StagedPage>
            private lateinit var pagesOnDisk: List<StagedPage>

            @Before
            fun numberIt() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                stagedPages = shootThreePages(staging)
                staging.numberPage(DOCUMENT, stagedPages[0], TWELVE, nextPagesFollowOn = true)
                filesOfTheRun = listPageFiles(folder)
                pagesInTheRun = staging.pages(DOCUMENT)
                pagesOnDisk = restartTheProcess(resolveStagingRoot(folder)).pages(DOCUMENT)
            }

            @Test
            fun `should rename its file only, since the numbers of the next pages follow from it`() {
                val expected = listOf(
                    StagingArea.fileName(1, stagedPages[0].capturedAt, TWELVE_WITH_THE_NEXT_PAGES),
                    stagedPages[1].file.name,
                    stagedPages[2].file.name,
                )
                assertEquals(expected, filesOfTheRun)
            }

            @Test
            fun `should keep the run in step with its files`() {
                assertEquals(pagesOnDisk, pagesInTheRun)
            }
        }

        class WhenTheProcessIsRestarted {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var numberings: List<PageNumbering>

            @Before
            fun readTheRunInTheNextProcess() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val pages = shootThreePages(staging)
                staging.numberPage(DOCUMENT, pages[0], TWELVE, nextPagesFollowOn = true)
                staging.numberPage(DOCUMENT, pages[2], null, nextPagesFollowOn = true)
                numberings = restartTheProcess(resolveStagingRoot(folder)).pages(DOCUMENT).map { it.numbering }
            }

            @Test
            fun `should keep each page's number, since the files alone describe the run`() {
                assertEquals(
                    listOf(TWELVE_WITH_THE_NEXT_PAGES, PageNumbering.NotGiven, PageNumbering.Cleared),
                    numberings,
                )
            }
        }

        class WhenTheNumberDoesNotChange {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var filesBefore: List<String>
            private lateinit var filesAfter: List<String>

            @Before
            fun numberItAgain() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                numberTheSecondOfThreePages(staging)
                filesBefore = listPageFiles(folder)
                staging.numberPage(DOCUMENT, staging.pages(DOCUMENT)[1], TWELVE, nextPagesFollowOn = false)
                filesAfter = listPageFiles(folder)
            }

            @Test
            fun `should rename nothing`() {
                assertEquals(filesBefore, filesAfter)
            }
        }

        class WhenAPageThatFollowsOnGetsItsRunningNumber {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var filesBefore: List<String>
            private lateinit var filesAfter: List<String>

            @Before
            fun numberItWithItsRunningNumber() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val pages = shootThreePages(staging)
                staging.numberPage(DOCUMENT, pages[0], TWELVE, nextPagesFollowOn = true)
                filesBefore = listPageFiles(folder)
                staging.numberPage(DOCUMENT, pages[1], THIRTEEN, nextPagesFollowOn = true)
                filesAfter = listPageFiles(folder)
            }

            @Test
            fun `should rename nothing, since it follows on already`() {
                assertEquals(filesBefore, filesAfter)
            }
        }

        class WhenThePageLeftTheRun {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var removedPage: StagedPage
            private lateinit var removedFiles: List<String>

            @Before
            fun numberIt() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                removedPage = removeTheSecondOfThreePages(staging)
                staging.numberPage(DOCUMENT, removedPage, TWELVE, nextPagesFollowOn = true)
                removedFiles = listRemovedFiles(folder)
            }

            @Test
            fun `should leave it as it was`() {
                assertEquals(listOf(removedPage.file.name), removedFiles)
            }
        }

        class WhenTheNewNameIsTaken {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var numberThePage: suspend () -> Unit

            @Before
            fun takeTheName() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                val page = shootThreePages(staging)[1]
                File(page.file.parentFile, StagingArea.fileName(page.seq, page.capturedAt, TWELVE_ALONE))
                    .writeText("another page")
                numberThePage = { staging.numberPage(DOCUMENT, page, TWELVE, nextPagesFollowOn = false) }
            }

            @Test
            fun `should refuse, so that no page is overwritten`() = runTest {
                val failure = runCatching { numberThePage() }.exceptionOrNull()
                assertTrue("$failure", failure is IOException)
                assertTrue("${failure?.message}", failure?.message.orEmpty().endsWith(NAME_TAKEN))
            }
        }

        class WhenTheCallerIsCanceledAsThePageIsRenamed {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var pagesInTheRun: List<String>
            private lateinit var filesOfTheRun: List<String>

            @Before
            fun numberAsTheCallerIsCanceled() = runTest {
                val disk = CancelingDisk(testScheduler)
                val staging = StagingArea(resolveStagingRoot(folder), disk)
                val pages = shootThreePages(staging)
                disk.cancelAfterItsWork(
                    launch(start = CoroutineStart.LAZY) {
                        staging.numberPage(DOCUMENT, pages[1], TWELVE, nextPagesFollowOn = true)
                    },
                )
                pagesInTheRun = staging.pages(DOCUMENT).map { it.file.name }
                filesOfTheRun = listPageFiles(folder)
            }

            @Test
            fun `should keep the run in step with its files`() {
                assertEquals(filesOfTheRun, pagesInTheRun)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheRetainRunsMethod {
        class WhenADocumentWasDeleted {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var droppedRun: List<StagedPage>
            private var isDroppedImageKept by Delegates.notNull<Boolean>()
            private lateinit var keptRunContents: List<String>

            @Before
            fun retainTheRunsOfTheLibrary() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                staging.shoot("kept", SHOT_TIME)
                val dropped = staging.shoot("dropped", SHOT_TIME, OTHER_DOCUMENT)
                staging.retainRuns { setOf(DOCUMENT) }
                droppedRun = staging.pages(OTHER_DOCUMENT)
                isDroppedImageKept = dropped.file.exists()
                keptRunContents = staging.readContents(DOCUMENT)
            }

            @Test
            fun `should drop its run`() {
                assertEquals(emptyList<StagedPage>(), droppedRun)
            }

            @Test
            fun `should delete its photos`() {
                assertFalse(isDroppedImageKept)
            }

            @Test
            fun `should keep the runs of the documents that exist`() {
                assertEquals(listOf("kept"), keptRunContents)
            }
        }

        class WhenEarlierProcessesLeftRuns {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var documentsSeen: Set<String>

            @Before
            fun retainTheRunsInANewProcess() = runTest {
                leaveAPageAndAnEmptiedRunInEarlierProcesses(resolveStagingRoot(folder))
                var seen = emptySet<String>()
                restartTheProcess(resolveStagingRoot(folder)).retainRuns { withPages ->
                    seen = withPages
                    setOf(DOCUMENT, OTHER_DOCUMENT)
                }
                documentsSeen = seen
            }

            @Test
            fun `should tell the library which documents have pages waiting, those of earlier processes too`() {
                assertEquals(setOf(DOCUMENT), documentsSeen)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheDocumentsWithPagesMethod {
        class WhenEarlierProcessesLeftRuns {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var documents: Set<String>

            @Before
            fun askInANewProcess() = runTest {
                leaveAPageAndAnEmptiedRunInEarlierProcesses(resolveStagingRoot(folder))
                documents = restartTheProcess(resolveStagingRoot(folder)).documentsWithPages()
            }

            @Test
            fun `should give the documents whose run has pages`() {
                assertEquals(setOf(DOCUMENT), documents)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheObserveRunSizesMethod {
        class WhenEarlierProcessesLeftRuns {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var runSizes: Map<String, Int>

            @Before
            fun observeInANewProcess() = runTest {
                leaveAPageAndAnEmptiedRunInEarlierProcesses(resolveStagingRoot(folder))
                runSizes = restartTheProcess(resolveStagingRoot(folder)).observeRunSizes().first()
            }

            @Test
            fun `should count the pages of each run that has some`() {
                assertEquals(mapOf(DOCUMENT to 1), runSizes)
            }
        }

        class WhenARunHasAPage {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var runSizes: Map<String, Int>

            @Before
            fun observeTheSizes() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                shootAPage(staging)
                runSizes = staging.observeRunSizes().first()
            }

            @Test
            fun `should count its page`() {
                assertEquals(mapOf(DOCUMENT to 1), runSizes)
            }
        }

        class WhenTwoRunsHavePages {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var runSizes: Map<String, Int>

            @Before
            fun observeTheSizes() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                shootAPage(staging)
                shootTwoPagesOfTheOtherDocument(staging)
                runSizes = staging.observeRunSizes().first()
            }

            @Test
            fun `should count the pages of each run`() {
                assertEquals(mapOf(DOCUMENT to 1, OTHER_DOCUMENT to 2), runSizes)
            }
        }

        class WhenTwoRunsHavePagesAndOneIsDiscarded {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var runSizes: Map<String, Int>

            @Before
            fun observeTheSizes() = runTest {
                val staging = StagingArea(resolveStagingRoot(folder))
                shootAPage(staging)
                shootTwoPagesOfTheOtherDocument(staging)
                staging.discard(OTHER_DOCUMENT)
                runSizes = staging.observeRunSizes().first()
            }

            @Test
            fun `should count only the run left`() {
                assertEquals(mapOf(DOCUMENT to 1), runSizes)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheFileNameMethod {
        class WhenGivenAPositionAndACaptureTime {
            private lateinit var name: String

            @Before
            fun nameTheFile() {
                name = StagingArea.fileName(12, SHOT_TIME)
            }

            @Test
            fun `should hold the position on five digits and the capture time in milliseconds`() {
                assertEquals("00012_${SHOT_TIME.toEpochMilli()}.jpg", name)
            }
        }

        @RunWith(Parameterized::class)
        class WhenGivenANumbering(
            private val kind: String,
            private val numbering: PageNumbering,
            private val suffix: String,
        ) {
            private lateinit var name: String

            @Before
            fun nameTheFile() {
                name = StagingArea.fileName(12, SHOT_TIME, numbering)
            }

            @Test
            fun `should hold the numbering after the capture time`() {
                assertEquals(kind, "00012_${SHOT_TIME.toEpochMilli()}$suffix.jpg", name)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun numberings(): List<Array<Any>> = listOf(
                    arrayOf("no number given, as the names of earlier versions", PageNumbering.NotGiven, ""),
                    arrayOf("a number given alone", TWELVE_ALONE, "_h12"),
                    arrayOf("a number given with the next pages", TWELVE_WITH_THE_NEXT_PAGES, "_h12c"),
                    arrayOf("a page cleared", PageNumbering.Cleared, "_n"),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheParseFileNameMethod {
        class WhenTheFileIsAPage {
            private lateinit var parsedName: ParsedName

            @Before
            fun parseTheName() {
                parsedName = ParsedName(StagingArea.parseFileName(File(StagingArea.fileName(12, SHOT_TIME))))
            }

            @Test
            fun `should read its position`() {
                assertEquals(12, parsedName.page?.seq)
            }

            @Test
            fun `should read its capture time`() {
                assertEquals(SHOT_TIME, parsedName.page?.capturedAt)
            }
        }

        @RunWith(Parameterized::class)
        class WhenWrittenByTheFileNameMethod(private val kind: String, private val numbering: PageNumbering) {
            private lateinit var parsedName: ParsedName

            @Before
            fun parseTheName() {
                parsedName = ParsedName(StagingArea.parseFileName(File(StagingArea.fileName(12, SHOT_TIME, numbering))))
            }

            @Test
            fun `should read the numbering it holds`() {
                assertEquals(kind, numbering, parsedName.page?.numbering)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun numberings(): List<Array<Any>> = listOf(
                    arrayOf("no number given", PageNumbering.NotGiven),
                    arrayOf("1, the first page", PageNumbering.Given(1, nextPagesFollowOn = false)),
                    arrayOf(
                        "9999, the last page the server accepts, with the next pages",
                        PageNumbering.Given(9999, nextPagesFollowOn = true),
                    ),
                    arrayOf("a page cleared", PageNumbering.Cleared),
                )
            }
        }

        class WhenTheNameIsOfAnEarlierVersion {
            private lateinit var parsedName: ParsedName

            @Before
            fun parseTheName() {
                parsedName = ParsedName(StagingArea.parseFileName(File(EARLIER_VERSION_NAME)))
            }

            @Test
            fun `should read a page with no number given`() {
                assertEquals(PageNumbering.NotGiven, parsedName.page?.numbering)
            }
        }

        class WhenTheNumberHasALeadingZero {
            private lateinit var parsedName: ParsedName

            @Before
            fun parseTheName() {
                parsedName = ParsedName(StagingArea.parseFileName(File("00012_1760293530123_h032.jpg")))
            }

            @Test
            fun `should read the number`() {
                assertEquals(PageNumbering.Given(32, nextPagesFollowOn = false), parsedName.page?.numbering)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheSuffixCannotBeRead(private val suffix: String, private val fileName: String) {
            private lateinit var parsedName: ParsedName

            @Before
            fun parseTheName() {
                parsedName = ParsedName(StagingArea.parseFileName(File(fileName)))
            }

            @Test
            fun `should read a page with no number given, so that no page is lost to a name it cannot read`() {
                assertEquals(suffix, PageNumbering.NotGiven, parsedName.page?.numbering)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun suffixes(): List<Array<Any>> = listOf(
                    arrayOf("page 0, which no page is", "00012_1760293530123_h0.jpg"),
                    arrayOf("page 10000, past the last page the server accepts", "00012_1760293530123_h10000.jpg"),
                    arrayOf("an unknown letter", "00012_1760293530123_x.jpg"),
                    arrayOf("a page following on without a number", "00012_1760293530123_hc.jpg"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheFileIsNotAPage(private val file: String, private val fileName: String) {
            private lateinit var parsedName: ParsedName

            @Before
            fun parseTheName() {
                parsedName = ParsedName(StagingArea.parseFileName(File(fileName)))
            }

            @Test
            fun `should give no page`() {
                assertNull(file, parsedName.page)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun files(): List<Array<Any>> = listOf(
                    arrayOf("the directory of incoming images", "incoming"),
                    arrayOf("a position of 0, which no page has", "00000_1760293530123.jpg"),
                    arrayOf("a file being written", "00012_1760293530123.jpg.tmp"),
                    arrayOf("a capture time that is not a number", "12_abc.jpg"),
                )
            }
        }
    }
}

private const val DOCUMENT = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
private const val OTHER_DOCUMENT = "0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d"
private const val DATABASE_FULL = "database full"
private const val INTERRUPTED = "interrupted"
private const val NAME_TAKEN = "a page of that name is in the run"
private const val TWELVE = 12
private const val THIRTEEN = 13
private const val EARLIER_VERSION_NAME = "00012_1760293530123.jpg"
private val TWELVE_ALONE = PageNumbering.Given(TWELVE, nextPagesFollowOn = false)
private val TWELVE_WITH_THE_NEXT_PAGES = PageNumbering.Given(TWELVE, nextPagesFollowOn = true)
private val SHOT_TIME: Instant = Instant.parse("2026-10-12T18:15:30.123Z")

/** A page that may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class ParsedName(val page: StagedPage?)

private fun resolveStagingRoot(folder: TemporaryFolder) = File(folder.root, "staging")

private fun restartTheProcess(root: File) = StagingArea(root)

private suspend fun StagingArea.writeAnIncomingImage(content: String, documentId: String = DOCUMENT): File =
    incomingFile(documentId).apply { writeText(content) }

private suspend fun StagingArea.shoot(content: String, at: Instant, documentId: String = DOCUMENT): StagedPage =
    add(documentId, listOf(StagingInput(writeAnIncomingImage(content, documentId), at))).single()

private suspend fun StagingArea.readContents(documentId: String): List<String> =
    pages(documentId).map { it.file.readText() }

private suspend fun shootAPage(staging: StagingArea): StagedPage = staging.shoot("a", SHOT_TIME)

private suspend fun addTwoImagesAtOnce(staging: StagingArea): List<StagedPage> = staging.add(
    DOCUMENT,
    listOf(
        StagingInput(staging.writeAnIncomingImage("a"), SHOT_TIME),
        StagingInput(staging.writeAnIncomingImage("b"), SHOT_TIME.plusSeconds(4)),
    ),
)

private suspend fun shootTwoPages(staging: StagingArea): List<StagedPage> =
    listOf(staging.shoot("a", SHOT_TIME), staging.shoot("b", SHOT_TIME.plusSeconds(4)))

private suspend fun shootTwoPagesOfTheOtherDocument(staging: StagingArea) {
    staging.shoot("b", SHOT_TIME, OTHER_DOCUMENT)
    staging.shoot("c", SHOT_TIME, OTHER_DOCUMENT)
}

private suspend fun shootTwoPagesAndOneOfTheOtherDocument(staging: StagingArea): List<StagedPage> {
    val pages = listOf(staging.shoot("a", SHOT_TIME), staging.shoot("b", SHOT_TIME))
    staging.shoot("other", SHOT_TIME, OTHER_DOCUMENT)
    return pages
}

private suspend fun discardTheRun(staging: StagingArea) {
    staging.discard(DOCUMENT)
}

private suspend fun deleteTheSecondOfThreePhotos(staging: StagingArea): StagedPage {
    staging.shoot("a", SHOT_TIME)
    val blurred = staging.shoot("b", SHOT_TIME.plusSeconds(2))
    staging.shoot("c", SHOT_TIME.plusSeconds(4))
    staging.delete(DOCUMENT, blurred)
    return blurred
}

private suspend fun shootThreePages(staging: StagingArea): List<StagedPage> = listOf(
    staging.shoot("a", SHOT_TIME),
    staging.shoot("b", SHOT_TIME.plusSeconds(2)),
    staging.shoot("c", SHOT_TIME.plusSeconds(4)),
)

private suspend fun removeTheSecondOfThreePages(staging: StagingArea): StagedPage {
    val removed = shootThreePages(staging)[1]
    staging.remove(DOCUMENT, removed)
    return removed
}

private suspend fun numberTheSecondOfThreePages(staging: StagingArea): StagedPage {
    val earlier = shootThreePages(staging)[1]
    staging.numberPage(DOCUMENT, earlier, TWELVE, nextPagesFollowOn = false)
    return earlier
}

private fun listRemovedFiles(folder: TemporaryFolder): List<String> =
    File(resolveStagingRoot(folder), "$DOCUMENT/removed").listFiles().orEmpty().map { it.name }.sorted()

/**
 * The disk's dispatcher, on the test's scheduler, which cancels the act it was given, if any, right
 * after each block, as when the screen that asked is closed while the disk works.
 */
private class CancelingDisk(scheduler: TestCoroutineScheduler) : CoroutineDispatcher() {
    private val disk = StandardTestDispatcher(scheduler)
    private var act: Job? = null

    override fun dispatch(context: CoroutineContext, block: Runnable) {
        disk.dispatch(context) {
            block.run()
            act?.cancel()
        }
    }

    /** Runs [act], once the run is read, so that its first work on the disk is the page's move. */
    suspend fun cancelAfterItsWork(act: Job) {
        this.act = act
        act.start()
        act.join()
        this.act = null
    }
}

/** The names of the page files in the run's directory, in order. */
private fun listPageFiles(folder: TemporaryFolder): List<String> =
    File(resolveStagingRoot(folder), DOCUMENT).listFiles().orEmpty().filter { it.isFile }.map { it.name }.sorted()

/** Whether [page]'s image is anywhere in the staging area, in the run or out of it. */
private fun isOnDisk(folder: TemporaryFolder, page: StagedPage): Boolean =
    resolveStagingRoot(folder).walk().any { it.isFile && it.name == page.file.name }

private suspend fun shootTwoScansAndTwoPhotos(staging: StagingArea) {
    staging.shoot("scanned 1", SHOT_TIME)
    staging.shoot("scanned 2", SHOT_TIME.plusSeconds(1))
    staging.shoot("photo 1", SHOT_TIME.plusSeconds(2))
    staging.shoot("photo 2", SHOT_TIME.plusSeconds(3))
}

private suspend fun deleteThePhotos(staging: StagingArea) {
    staging.pages(DOCUMENT).filter { it.file.readText().startsWith("photo") }.forEach { staging.delete(DOCUMENT, it) }
}

private suspend fun leaveAnImageOnItsWay(root: File): StagingArea = StagingArea(root).apply {
    shoot("a", SHOT_TIME)
    writeAnIncomingImage("half a photo")
}

private suspend fun letTheNextProcessNoticeTheImageCutShort(restarted: StagingArea) {
    restarted.pages(DOCUMENT)
}

private suspend fun askForInterruptedImages(staging: StagingArea): Boolean = staging.takeInterrupted(DOCUMENT)

private suspend fun leaveAPageAndAnEmptiedRunInEarlierProcesses(root: File) {
    StagingArea(root).shoot("a", SHOT_TIME)
    StagingArea(root).shoot("b", SHOT_TIME, OTHER_DOCUMENT)
    StagingArea(root).delete(OTHER_DOCUMENT, StagingArea(root).pages(OTHER_DOCUMENT).single())
}

private fun moveThenFail(page: StagedPage, outbox: File): Nothing {
    page.file.renameTo(File(outbox, page.file.name))
    throw IOException(INTERRUPTED)
}
