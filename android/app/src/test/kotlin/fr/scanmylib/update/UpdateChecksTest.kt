package fr.scanmylib.update

import fr.scanmylib.api.PublishedApk
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class UpdateChecksTest {
    @RunWith(Enclosed::class)
    class TheOfferedUpdateFunction {
        class WhenThePcPublishesANewerApkOfThisApp {
            private lateinit var offer: Offer

            @Before
            fun readTheOffer() {
                offer = Offer(offeredUpdate(PC_URL, PUBLISHED_APK, APP, INSTALLED_VERSION_CODE))
            }

            @Test
            fun `should offer it, downloaded from the paired PC`() {
                assertEquals(
                    AvailableUpdate("0.8.0", 800, SHA256, 1234, "http://192.168.1.10:8770$DOWNLOAD_PATH".toHttpUrl()),
                    offer.update,
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheApkIsNotOneToInstall(
            private val apk: String,
            private val published: PublishedApk?,
            private val installedId: String,
            private val installedVersionCode: Long,
        ) {
            private lateinit var offer: Offer

            @Before
            fun readTheOffer() {
                offer = Offer(offeredUpdate(PC_URL, published, installedId, installedVersionCode))
            }

            @Test
            fun `should offer nothing`() {
                assertNull(apk, offer.update)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun apks(): List<Array<Any?>> = listOf(
                    arrayOf("no APK published", null, APP, INSTALLED_VERSION_CODE),
                    arrayOf("the version installed", PUBLISHED_APK, APP, 800L),
                    arrayOf("an older version", PUBLISHED_APK, APP, 900L),
                    arrayOf(
                        "the production app's, since each app checks its own",
                        PUBLISHED_APK,
                        "fr.scanmylib",
                        INSTALLED_VERSION_CODE,
                    ),
                    arrayOf(
                        "an APK on another host",
                        PUBLISHED_APK.copy(path = "//example.invalid/scanmylib.apk"),
                        APP,
                        INSTALLED_VERSION_CODE,
                    ),
                    arrayOf(
                        "an APK outside the downloads",
                        PUBLISHED_APK.copy(path = "/download/../api/documents"),
                        APP,
                        INSTALLED_VERSION_CODE,
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheVersionIsOneTheServerAnnounces(private val build: String, private val version: String) {
            private lateinit var offer: Offer

            @Before
            fun readTheOffer() {
                offer = Offer(offeredUpdate(PC_URL, PUBLISHED_APK.copy(version = version), APP, INSTALLED_VERSION_CODE))
            }

            @Test
            fun `should offer it, with its version`() {
                assertEquals(build, version, offer.update?.version)
            }

            companion object {
                // A release, or a development build (scripts/lib/version.py), up to 64 characters.
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun versions(): List<Array<Any>> = listOf(
                    arrayOf("a release", "123.45.67"),
                    arrayOf("a development build", "0.2.4-dev.27+g1a2b3c4d5e6f"),
                    arrayOf("a development build with changes", "0.2.4-dev+g1a2b3c4d5e6f.dirty"),
                    arrayOf("a development build without its commit", "0.2.4-dev"),
                    arrayOf("the longest version, of 64 characters", LONGEST_VERSION),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheVersionIsOneTheServerWouldNotAnnounce(private val build: String, private val version: String) {
            private lateinit var offer: Offer

            @Before
            fun readTheOffer() {
                offer = Offer(offeredUpdate(PC_URL, PUBLISHED_APK.copy(version = version), APP, INSTALLED_VERSION_CODE))
            }

            @Test
            fun `should offer nothing`() {
                assertNull(build, offer.update)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun versions(): List<Array<Any>> = listOf(
                    arrayOf("two numbers", "0.8"),
                    arrayOf("four numbers", "0.8.0.1"),
                    arrayOf("an empty pre-release", "0.8.0-"),
                    arrayOf("an empty build", "0.8.0+"),
                    arrayOf("a letter outside ASCII", "0.8.0-é"),
                    arrayOf("65 characters", LONGEST_VERSION + "a"),
                    arrayOf("a major version of four digits", "1234.0.0"),
                    arrayOf("a minor version of three digits", "0.100.0"),
                    arrayOf("a line end", "0.8.0\n"),
                    arrayOf("a name before the version", "ScanMyLib 0.8.0"),
                    arrayOf("no version", ""),
                )
            }
        }

        class WhenTheApkIsTheLargestTheAppDownloads {
            private lateinit var offer: Offer

            @Before
            fun readTheOffer() {
                val largest = PUBLISHED_APK.copy(size = MAX_APK_SIZE)
                offer = Offer(offeredUpdate(PC_URL, largest, APP, INSTALLED_VERSION_CODE))
            }

            @Test
            fun `should offer it`() {
                assertEquals(MAX_APK_SIZE, offer.update?.size)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheSizeIsOneTheAppDoesNotDownload(private val apk: String, private val sizeBytes: Long) {
            private lateinit var offer: Offer

            @Before
            fun readTheOffer() {
                offer = Offer(offeredUpdate(PC_URL, PUBLISHED_APK.copy(size = sizeBytes), APP, INSTALLED_VERSION_CODE))
            }

            @Test
            fun `should offer nothing`() {
                assertNull(apk, offer.update)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun sizes(): List<Array<Any>> = listOf(
                    arrayOf("an empty APK", 0L),
                    arrayOf("a negative size", -1L),
                    arrayOf("a byte over the largest APK the app downloads", MAX_APK_SIZE + 1),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheCheckDownloadedApkFunction {
        @RunWith(Parameterized::class)
        class WhenTheApkMayBeInstalled(
            private val apk: String,
            private val sha256: String,
            private val facts: ApkFacts?,
            private val installedSigners: Set<String>?,
        ) {
            private lateinit var problem: Problem

            @Before
            fun checkTheApk() {
                problem = Problem(
                    checkDownloadedApk(
                        UPDATE,
                        sha256,
                        UPDATE.size,
                        facts,
                        APP,
                        INSTALLED_VERSION_CODE,
                        installedSigners,
                    ),
                )
            }

            @Test
            fun `should let Android install it`() {
                assertNull(apk, problem.failure)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun apks(): List<Array<Any?>> = listOf(
                    arrayOf("the APK announced, of this app, newer, by the same signer", SHA256, FACTS, SIGNERS),
                    arrayOf("a digest written in uppercase", SHA256.uppercase(), FACTS, SIGNERS),
                    arrayOf(
                        "signers Android does not report for the APK, left to its own check",
                        SHA256,
                        FACTS.copy(signers = null),
                        SIGNERS,
                    ),
                    arrayOf(
                        "signers Android does not report for the installed app, left to its own check",
                        SHA256,
                        FACTS,
                        null,
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheApkMayNotBeInstalled(
            private val apk: String,
            private val sha256: String,
            private val sizeBytes: Long,
            private val facts: ApkFacts?,
            private val expected: UpdateFailure,
        ) {
            private lateinit var problem: Problem

            @Before
            fun checkTheApk() {
                problem = Problem(
                    checkDownloadedApk(UPDATE, sha256, sizeBytes, facts, APP, INSTALLED_VERSION_CODE, SIGNERS),
                )
            }

            @Test
            fun `should refuse it, with the reason`() {
                assertEquals(apk, expected, problem.failure)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun apks(): List<Array<Any?>> = listOf(
                    arrayOf("a size not as announced", SHA256, UPDATE.size + 1, FACTS, UpdateFailure.NOT_AS_ANNOUNCED),
                    arrayOf(
                        "a digest not as announced",
                        "00".repeat(32),
                        UPDATE.size,
                        FACTS,
                        UpdateFailure.NOT_AS_ANNOUNCED,
                    ),
                    arrayOf(
                        "a file Android cannot read as an APK",
                        SHA256,
                        UPDATE.size,
                        null,
                        UpdateFailure.UNREADABLE,
                    ),
                    arrayOf(
                        "another app's APK",
                        SHA256,
                        UPDATE.size,
                        FACTS.copy(packageName = "fr.scanmylib"),
                        UpdateFailure.OTHER_APP,
                    ),
                    arrayOf(
                        "an APK no newer than the app installed",
                        SHA256,
                        UPDATE.size,
                        FACTS.copy(versionCode = INSTALLED_VERSION_CODE),
                        UpdateFailure.NOT_NEWER,
                    ),
                    arrayOf(
                        "a newer APK, but not the version announced",
                        SHA256,
                        UPDATE.size,
                        FACTS.copy(versionCode = UNANNOUNCED_NEWER_VERSION_CODE),
                        UpdateFailure.NOT_AS_ANNOUNCED,
                    ),
                    arrayOf(
                        "an APK of another signer",
                        SHA256,
                        UPDATE.size,
                        FACTS.copy(signers = setOf("ef".repeat(32))),
                        UpdateFailure.OTHER_SIGNER,
                    ),
                )
            }
        }
    }
}

private const val APP = "fr.scanmylib.dev"
private const val INSTALLED_VERSION_CODE = 700L
private const val UNANNOUNCED_NEWER_VERSION_CODE = 900L
private val PC_URL: HttpUrl = "http://192.168.1.10:8770/".toHttpUrl()
private const val DOWNLOAD_PATH = "/download/scanmylib.apk"
private val SHA256 = "ab".repeat(32)
private val PUBLISHED_APK = PublishedApk(APP, "0.8.0", 800, SHA256, 1234, DOWNLOAD_PATH)
private val UPDATE = AvailableUpdate("0.8.0", 800, SHA256, 1234, PC_URL)
private val SIGNERS = setOf("cd".repeat(32))
private val FACTS = ApkFacts(APP, 800, SIGNERS)
private val LONGEST_VERSION = "0.2.4-dev+g" + "a".repeat(53)

/** The update offered, null when there is none, held in a non-null value so that a test fails when no hook ran. */
private data class Offer(val update: AvailableUpdate?)

/** Why a downloaded APK may not be installed, null when it may, held as [Offer] is. */
private data class Problem(val failure: UpdateFailure?)
