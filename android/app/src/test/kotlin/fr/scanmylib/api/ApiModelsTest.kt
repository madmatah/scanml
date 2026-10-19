package fr.scanmylib.api

import fr.scanmylib.model.DocumentKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class ApiModelsTest {
    @RunWith(Enclosed::class)
    class TheDecodeFromStringMethodOfApiJson {
        class WhenGivenTheHealthExample {
            private lateinit var health: Health

            @Before
            fun decodeTheHealth() {
                health = ApiJson.decodeFromString(Health.serializer(), ApiFixtures.HEALTH)
            }

            @Test
            fun `should read the name of the server and the version of its API`() {
                assertEquals(Health(name = "ScanMyLib", api = 1), health)
            }
        }

        class WhenGivenTheStatusExample {
            private lateinit var status: ServerStatus

            @Before
            fun decodeTheStatus() {
                status = ApiJson.decodeFromString(ServerStatus.serializer(), ApiFixtures.STATUS)
            }

            @Test
            fun `should read the version, the state of the engine and the queue`() {
                assertEquals(
                    ServerStatus(
                        version = "0.1.0",
                        ocr = OcrStatus(state = "idle", lastError = null),
                        queue = QueueCounts(queued = 3, processing = 1),
                    ),
                    status,
                )
            }
        }

        class WhenGivenTheDocumentExample {
            private lateinit var document: Document

            @Before
            fun decodeTheDocument() {
                document = ApiJson.decodeFromString(Document.serializer(), ApiFixtures.DOCUMENT)
            }

            @Test
            fun `should read every field the app uses`() {
                assertEquals(
                    Document(
                        id = ApiFixtures.DOCUMENT_ID,
                        title = "Example Book",
                        author = "Jane Doe",
                        kind = DocumentKind.BOOK,
                        unwarp = false,
                        updatedAt = "2026-10-12T20:00:00+02:00",
                        stats = DocumentStats(pages = 42, done = 40, queued = 1, processing = 1),
                        coverage = Coverage(label = "1–12, 45–60", gaps = listOf(listOf(13, 44)), unnumbered = 3),
                        coverThumbUrl = "/api/pages/${ApiFixtures.PAGE_ID}/thumb",
                        folder = "/home/user/Documents/ScanMyLib/example-book",
                    ),
                    document,
                )
            }
        }

        class WhenGivenThePageExample {
            private lateinit var page: Page

            @Before
            fun decodeThePage() {
                page = ApiJson.decodeFromString(Page.serializer(), ApiFixtures.PAGE)
            }

            @Test
            fun `should read every field the app uses`() {
                assertEquals(
                    Page(
                        id = ApiFixtures.PAGE_ID,
                        documentId = ApiFixtures.DOCUMENT_ID,
                        status = PageStatus.DONE,
                        error = null,
                        pageLabel = "42",
                        numberSource = NumberSource.DETECTED,
                        excluded = false,
                        duplicateOf = null,
                        thumbUrl = "/api/pages/${ApiFixtures.PAGE_ID}/thumb",
                    ),
                    page,
                )
            }
        }

        class WhenAPageHoldsValuesAndFieldsAddedByANewerServer {
            private val newerPage =
                """{"id": "p", "document_id": "d", "status": "archived", "number_source": "ai", "new_field": [1, 2]}"""
            private lateinit var page: Page

            @Before
            fun decodeThePage() {
                page = ApiJson.decodeFromString(Page.serializer(), newerPage)
            }

            @Test
            fun `should read an unknown state as unknown`() {
                assertEquals(PageStatus.UNKNOWN, page.status)
            }

            @Test
            fun `should read an unknown source of the page number as none`() {
                assertNull(page.numberSource)
            }
        }

        class WhenADocumentHoldsAKindAddedByANewerServerAndNoStats {
            private lateinit var document: Document

            @Before
            fun decodeTheDocument() {
                document = ApiJson.decodeFromString(
                    Document.serializer(),
                    """{"id": "d", "title": "T", "kind": "magazine"}""",
                )
            }

            @Test
            fun `should read it as a plain document`() {
                assertEquals(DocumentKind.DOCUMENT, document.kind)
            }

            @Test
            fun `should give the missing stats their defaults`() {
                assertEquals(DocumentStats(), document.stats)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheEncodeToStringMethodOfApiJson {
        class WhenGivenTheBodyOfADocumentUpsert {
            private lateinit var body: String

            @Before
            fun encodeTheBody() {
                body = ApiJson.encodeToString(
                    DocumentUpsert.serializer(),
                    DocumentUpsert(
                        title = "Example Book",
                        author = "Jane Doe",
                        kind = DocumentKind.BOOK,
                        unwarp = true,
                    ),
                )
            }

            @Test
            fun `should write the fields the server reads`() {
                assertEquals("""{"title":"Example Book","author":"Jane Doe","kind":"book","unwarp":true}""", body)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheApkPropertyOfHealth {
        class WhenThePcPublishesAnApk {
            private val apkSha256 = "ab".repeat(32)
            private lateinit var reading: HealthReading

            @Before
            fun readTheApk() {
                val health = ApiJson.decodeFromString(
                    Health.serializer(),
                    """
                    {"name": "ScanMyLib", "version": "0.8.0", "api": 1, "apk": {"application_id": "fr.scanmylib",
                     "version": "0.8.0", "version_code": 800, "sha256": "$apkSha256", "size": 1234,
                     "path": "/download/scanmylib.apk"}}
                    """.trimIndent(),
                )
                reading = HealthReading(health.name, health.apk)
            }

            @Test
            fun `should describe it`() {
                assertEquals(
                    PublishedApk("fr.scanmylib", "0.8.0", 800, apkSha256, 1234, "/download/scanmylib.apk"),
                    reading.apk,
                )
            }
        }

        class WhenThePcPublishesNoApk {
            private lateinit var reading: HealthReading

            @Before
            fun readTheApk() {
                val health = ApiJson.decodeFromString(
                    Health.serializer(),
                    """{"name": "ScanMyLib", "api": 1, "apk": null}""",
                )
                reading = HealthReading(health.name, health.apk)
            }

            @Test
            fun `should describe none`() {
                assertNull(reading.apk)
            }
        }

        class WhenTheDescriptionOfTheApkIsMalformed {
            private lateinit var reading: HealthReading

            @Before
            fun readTheApk() {
                val health = ApiJson.decodeFromString(
                    Health.serializer(),
                    """{"name": "ScanMyLib", "api": 1, "apk": {"version": 3}}""",
                )
                reading = HealthReading(health.name, health.apk)
            }

            @Test
            fun `should describe none`() {
                assertNull(reading.apk)
            }

            @Test
            fun `should leave the health check readable, so that pairing still works`() {
                assertEquals("ScanMyLib", reading.serverName)
            }
        }
    }
}

private data class HealthReading(val serverName: String, val apk: PublishedApk?)
