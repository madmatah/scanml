package fr.scanmylib.library

import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class PhotoImportTest {
    @RunWith(Enclosed::class)
    class TheExifCaptureTimeFunction {
        @RunWith(Parameterized::class)
        class WhenTheCameraWroteATimeTheServerAccepts(
            private val tags: String,
            private val dateTime: String,
            private val subSeconds: String?,
            private val offset: String?,
            private val zone: ZoneId,
            private val expected: Instant,
        ) {
            private lateinit var captureTime: CaptureTime

            @Before
            fun readTheTags() {
                captureTime = CaptureTime(exifCaptureTime(dateTime, subSeconds, offset, zone))
            }

            @Test
            fun `should read when the photo was taken`() {
                assertEquals(tags, expected, captureTime.instant)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun tags(): List<Array<Any?>> = listOf(
                    arrayOf(
                        "a time without an offset is read in the phone's time zone",
                        "2026:10:12 20:15:30",
                        null,
                        null,
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30Z"),
                    ),
                    arrayOf(
                        "the offset written by the camera wins over the phone's time zone",
                        "2026:10:12 20:15:30",
                        null,
                        "+01:00",
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T19:15:30Z"),
                    ),
                    arrayOf(
                        "an unreadable offset is read as if there were none",
                        "2026:10:12 20:15:30",
                        null,
                        "+99:00",
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30Z"),
                    ),
                    arrayOf(
                        "sub-seconds tell apart the photos of a burst",
                        "2026:10:12 20:15:30",
                        "12",
                        null,
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30.120Z"),
                    ),
                    arrayOf(
                        "sub-seconds are read to the microsecond, without their trailing space",
                        "2026:10:12 20:15:30",
                        "000123 ",
                        null,
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30.000123Z"),
                    ),
                    arrayOf(
                        "empty sub-seconds add nothing",
                        "2026:10:12 20:15:30",
                        "",
                        null,
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30Z"),
                    ),
                    arrayOf(
                        "a date written with dashes, as some cameras write it, is read",
                        "2026-10-12 20:15:30",
                        null,
                        null,
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30Z"),
                    ),
                    arrayOf(
                        "a time between spaces, as some cameras write it, is read",
                        " 2026:10:12 20:15:30 ",
                        null,
                        null,
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30Z"),
                    ),
                    arrayOf(
                        "a time with a fraction of a second, as some cameras write it, is read to the second",
                        "2026:10:12 20:15:30.48",
                        null,
                        null,
                        PHONE_ZONE,
                        Instant.parse("2026-10-12T18:15:30Z"),
                    ),
                    arrayOf(
                        "the first moment of 2000, the first year the server accepts, is read",
                        "2000:01:01 00:00:00",
                        null,
                        null,
                        ZoneOffset.UTC,
                        Instant.parse("2000-01-01T00:00:00Z"),
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheCameraDidNotKnowTheTime(private val cameraDate: String, private val dateTime: String?) {
            private lateinit var captureTime: CaptureTime

            @Before
            fun readTheTags() {
                captureTime = CaptureTime(exifCaptureTime(dateTime, subSeconds = null, offset = null, PHONE_ZONE))
            }

            @Test
            fun `should give no time`() {
                assertNull(cameraDate, captureTime.instant)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun cameraDates(): List<Array<Any?>> = listOf(
                    arrayOf("no date", null),
                    arrayOf("an empty date", ""),
                    arrayOf("blanks, from a camera whose clock is not set", "    :  :     :  :  "),
                    arrayOf("zeros, from a camera whose clock is not set", "0000:00:00 00:00:00"),
                    arrayOf("a day that does not exist", "2026:02:30 10:00:00"),
                    arrayOf("an hour that does not exist", "2026:10:12 24:00:00"),
                    arrayOf("a date in another format", "12/10/2026 20:15"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheTimeIsOutsideTheYearsTheServerAccepts(
            private val cameraDate: String,
            private val dateTime: String,
        ) {
            private lateinit var captureTime: CaptureTime

            @Before
            fun readTheTags() {
                captureTime = CaptureTime(exifCaptureTime(dateTime, subSeconds = null, offset = null, ZoneOffset.UTC))
            }

            @Test
            fun `should give no time, which the server would refuse`() {
                assertNull(cameraDate, captureTime.instant)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun cameraDates(): List<Array<Any>> = listOf(
                    arrayOf("the last moment of 1999", "1999:12:31 23:59:59"),
                    arrayOf("the first moment of 2201", "2201:01:01 00:00:00"),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOrderByCaptureTimeFunction {
        class WhenEveryPhotoHasATime {
            private lateinit var order: List<String>

            @Before
            fun orderThePhotos() {
                val chosen = listOf("page 3" to at(30), "page 1" to at(10), "page 2" to at(20))
                order = orderByCaptureTime(chosen) { it.second }.map { it.first }
            }

            @Test
            fun `should order them by the time they were taken`() {
                assertEquals(listOf("page 1", "page 2", "page 3"), order)
            }
        }

        class WhenSomePhotosHaveNoTime {
            private lateinit var order: List<String>

            @Before
            fun orderThePhotos() {
                val chosen = listOf("x" to null, "b" to at(20), "y" to null, "a" to at(10))
                order = orderByCaptureTime(chosen) { it.second }.map { it.first }
            }

            @Test
            fun `should put the photos without a time last, in the order they were chosen`() {
                assertEquals(listOf("a", "b", "x", "y"), order)
            }
        }

        class WhenNoPhotoHasATime {
            private lateinit var order: List<String>

            @Before
            fun orderThePhotos() {
                val chosen = listOf<Pair<String, Instant?>>("c" to null, "a" to null, "b" to null)
                order = orderByCaptureTime(chosen) { it.second }.map { it.first }
            }

            @Test
            fun `should keep the order they were chosen in`() {
                assertEquals(listOf("c", "a", "b"), order)
            }
        }

        class WhenPhotosWereTakenAtTheSameTime {
            private lateinit var order: List<String>

            @Before
            fun orderThePhotos() {
                val chosen = listOf("1" to at(10), "2" to at(10), "0" to at(5), "3" to at(10))
                order = orderByCaptureTime(chosen) { it.second }.map { it.first }
            }

            @Test
            fun `should keep the order they were chosen in`() {
                assertEquals(listOf("0", "1", "2", "3"), order)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheSniffMethod {
        @RunWith(Parameterized::class)
        class WhenTheServerAcceptsTheFormat(
            private val header: String,
            private val bytes: ByteArray,
            private val expected: ImageFormat,
        ) {
            private lateinit var format: SniffedFormat

            @Before
            fun sniffTheHeader() {
                format = SniffedFormat(ImageFormat.sniff(bytes))
            }

            @Test
            fun `should recognize it`() {
                assertEquals(header, expected, format.format)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun headers(): List<Array<Any>> = listOf(
                    arrayOf("JPEG", bytes(0xFF, 0xD8, 0xFF, 0xE1, 0x00, 0x10), ImageFormat.JPEG),
                    arrayOf("PNG", bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0), ImageFormat.PNG),
                    arrayOf("WebP", ascii("RIFF") + bytes(0x24, 0x10, 0, 0) + ascii("WEBPVP8 "), ImageFormat.WEBP),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheServerRefusesTheFormat(private val header: String, private val bytes: ByteArray) {
            private lateinit var format: SniffedFormat

            @Before
            fun sniffTheHeader() {
                format = SniffedFormat(ImageFormat.sniff(bytes))
            }

            @Test
            fun `should refuse it`() {
                assertNull(header, format.format)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun headers(): List<Array<Any>> = listOf(
                    arrayOf("HEIC", bytes(0, 0, 0, 0x18) + ascii("ftypheic")),
                    arrayOf("GIF", ascii("GIF89a")),
                    arrayOf("a RIFF container of sound", ascii("RIFF") + bytes(0x24, 0x10, 0, 0) + ascii("WAVEfmt ")),
                    arrayOf("a RIFF container cut short", ascii("RIFF")),
                    arrayOf("a JPEG cut short", bytes(0xFF, 0xD8)),
                    arrayOf("no bytes", ByteArray(0)),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class ThePhotoRejectionFunction {
        @RunWith(Parameterized::class)
        class WhenTheServerAcceptsThePhoto(
            private val photo: String,
            private val format: ImageFormat,
            private val sizeBytes: Long,
            private val pixels: Long?,
        ) {
            private lateinit var rejection: Rejection

            @Before
            fun checkThePhoto() {
                rejection = Rejection(photoRejection(format, sizeBytes, pixels))
            }

            @Test
            fun `should import it`() {
                assertNull(photo, rejection.reason)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun photos(): List<Array<Any?>> = listOf(
                    arrayOf("a JPEG at the server's limits", ImageFormat.JPEG, MAX_SCAN_BYTES, MAX_SCAN_PIXELS),
                    arrayOf("a WebP whose pixels are unknown", ImageFormat.WEBP, 1_000L, null),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheServerWouldRefuseThePhoto(
            private val photo: String,
            private val format: ImageFormat?,
            private val sizeBytes: Long,
            private val pixels: Long,
            private val expected: PhotoRejection,
        ) {
            private lateinit var rejection: Rejection

            @Before
            fun checkThePhoto() {
                rejection = Rejection(photoRejection(format, sizeBytes, pixels))
            }

            @Test
            fun `should leave it out, with the reason`() {
                assertEquals(photo, expected, rejection.reason)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun photos(): List<Array<Any?>> = listOf(
                    arrayOf(
                        "a JPEG one byte over 40 MiB is too large",
                        ImageFormat.JPEG,
                        MAX_SCAN_BYTES + 1,
                        12_000_000L,
                        PhotoRejection.TOO_LARGE,
                    ),
                    arrayOf(
                        "a photo of 200 megapixels, well under 40 MiB, is too large",
                        ImageFormat.JPEG,
                        30_000_000L,
                        16_320L * 12_240,
                        PhotoRejection.TOO_LARGE,
                    ),
                    arrayOf(
                        "a format the server refuses is unsupported",
                        null,
                        1_000L,
                        1_000L,
                        PhotoRejection.UNSUPPORTED_FORMAT,
                    ),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheOfMethod {
        class WhenTheFileIsAPng {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var format: SniffedFormat

            @Before
            fun readTheFile() {
                val png = folder.newFile("photo.png").apply {
                    writeBytes(bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A) + ByteArray(1000))
                }
                format = SniffedFormat(ImageFormat.of(png))
            }

            @Test
            fun `should read its format`() {
                assertEquals(ImageFormat.PNG, format.format)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheFileIsTooShortForAFormat(private val file: String, private val content: ByteArray) {
            @get:Rule
            val folder = TemporaryFolder()

            private lateinit var format: SniffedFormat

            @Before
            fun readTheFile() {
                format = SniffedFormat(ImageFormat.of(folder.newFile("photo.jpg").apply { writeBytes(content) }))
            }

            @Test
            fun `should refuse it`() {
                assertNull(file, format.format)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun files(): List<Array<Any>> = listOf(
                    arrayOf("a JPEG cut short", bytes(0xFF, 0xD8)),
                    arrayOf("an empty file", ByteArray(0)),
                )
            }
        }
    }
}

private val PHONE_ZONE: ZoneId = ZoneId.of("+02:00")

/** A capture time that may be missing, held in a non-null value so that a test fails when no hook ran. */
private data class CaptureTime(val instant: Instant?)

/** A format that may be refused, held as [CaptureTime] is. */
private data class SniffedFormat(val format: ImageFormat?)

/** Why the server would refuse a photo, null when it accepts it, held as [CaptureTime] is. */
private data class Rejection(val reason: PhotoRejection?)

private fun at(seconds: Long): Instant = Instant.parse("2026-10-12T18:00:00Z").plusSeconds(seconds)

private fun bytes(vararg values: Int) = ByteArray(values.size) { values[it].toByte() }

private fun ascii(text: String) = text.toByteArray(Charsets.US_ASCII)
