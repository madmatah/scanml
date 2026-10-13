package fr.scanmylib.library

import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class PhotoImportTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val phoneZone = ZoneId.of("+02:00")

    private fun bytes(vararg values: Int) = ByteArray(values.size) { values[it].toByte() }

    private fun ascii(text: String) = text.toByteArray(Charsets.US_ASCII)

    @Test
    fun `the EXIF time is read in the phone's time zone`() {
        assertEquals(
            Instant.parse("2026-10-12T18:15:30Z"),
            exifCaptureTime("2026:10:12 20:15:30", subSeconds = null, offset = null, zone = phoneZone),
        )
    }

    @Test
    fun `the offset written by the camera wins over the phone's time zone`() {
        assertEquals(
            Instant.parse("2026-10-12T19:15:30Z"),
            exifCaptureTime("2026:10:12 20:15:30", subSeconds = null, offset = "+01:00", zone = phoneZone),
        )
        // Unreadable offset: as if there were none.
        assertEquals(
            Instant.parse("2026-10-12T18:15:30Z"),
            exifCaptureTime("2026:10:12 20:15:30", subSeconds = null, offset = "+99:00", zone = phoneZone),
        )
    }

    @Test
    fun `sub-seconds tell apart the photos of a burst`() {
        assertEquals(
            Instant.parse("2026-10-12T18:15:30.120Z"),
            exifCaptureTime("2026:10:12 20:15:30", subSeconds = "12", offset = null, zone = phoneZone),
        )
        assertEquals(
            Instant.parse("2026-10-12T18:15:30.000123Z"),
            exifCaptureTime("2026:10:12 20:15:30", subSeconds = "000123 ", offset = null, zone = phoneZone),
        )
        assertEquals(
            Instant.parse("2026-10-12T18:15:30Z"),
            exifCaptureTime("2026:10:12 20:15:30", subSeconds = "", offset = null, zone = phoneZone),
        )
    }

    @Test
    fun `variants written by some cameras are read too`() {
        val expected = Instant.parse("2026-10-12T18:15:30Z")
        assertEquals(expected, exifCaptureTime("2026-10-12 20:15:30", null, null, phoneZone))
        assertEquals(expected, exifCaptureTime(" 2026:10:12 20:15:30 ", null, null, phoneZone))
        assertEquals(expected, exifCaptureTime("2026:10:12 20:15:30.48", null, null, phoneZone))
    }

    @Test
    fun `no time when the camera did not know it`() {
        assertNull(exifCaptureTime(null, null, null, phoneZone))
        assertNull(exifCaptureTime("", null, null, phoneZone))
        assertNull(exifCaptureTime("    :  :     :  :  ", null, null, phoneZone))
        assertNull(exifCaptureTime("0000:00:00 00:00:00", null, null, phoneZone))
        assertNull(exifCaptureTime("2026:02:30 10:00:00", null, null, phoneZone))
        assertNull(exifCaptureTime("2026:10:12 24:00:00", null, null, phoneZone))
        assertNull(exifCaptureTime("12/10/2026 20:15", null, null, phoneZone))
    }

    @Test
    fun `no time outside the years the server accepts`() {
        assertNull(exifCaptureTime("1999:12:31 23:59:59", null, null, ZoneOffset.UTC))
        assertEquals(
            Instant.parse("2000-01-01T00:00:00Z"),
            exifCaptureTime("2000:01:01 00:00:00", null, null, ZoneOffset.UTC),
        )
        assertNull(exifCaptureTime("2201:01:01 00:00:00", null, null, ZoneOffset.UTC))
    }

    private fun at(seconds: Long): Instant = Instant.parse("2026-10-12T18:00:00Z").plusSeconds(seconds)

    @Test
    fun `photos are ordered by the time they were taken`() {
        val chosen = listOf("page 3" to at(30), "page 1" to at(10), "page 2" to at(20))
        assertEquals(listOf("page 1", "page 2", "page 3"), orderByCaptureTime(chosen) { it.second }.map { it.first })
    }

    @Test
    fun `photos without a time come last, in the order they were chosen`() {
        val chosen = listOf("x" to null, "b" to at(20), "y" to null, "a" to at(10))
        assertEquals(listOf("a", "b", "x", "y"), orderByCaptureTime(chosen) { it.second }.map { it.first })
        val undated = listOf<Pair<String, Instant?>>("c" to null, "a" to null, "b" to null)
        assertEquals(listOf("c", "a", "b"), orderByCaptureTime(undated) { it.second }.map { it.first })
    }

    @Test
    fun `photos taken at the same time keep the order they were chosen in`() {
        val chosen = listOf("1" to at(10), "2" to at(10), "0" to at(5), "3" to at(10))
        assertEquals(listOf("0", "1", "2", "3"), orderByCaptureTime(chosen) { it.second }.map { it.first })
    }

    @Test
    fun `recognizes the formats the server accepts`() {
        assertEquals(ImageFormat.JPEG, ImageFormat.sniff(bytes(0xFF, 0xD8, 0xFF, 0xE1, 0x00, 0x10)))
        assertEquals(ImageFormat.PNG, ImageFormat.sniff(bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0)))
        assertEquals(ImageFormat.WEBP, ImageFormat.sniff(ascii("RIFF") + bytes(0x24, 0x10, 0, 0) + ascii("WEBPVP8 ")))
    }

    @Test
    fun `other formats are refused`() {
        assertNull(ImageFormat.sniff(bytes(0, 0, 0, 0x18) + ascii("ftypheic"))) // HEIC
        assertNull(ImageFormat.sniff(ascii("GIF89a")))
        assertNull(ImageFormat.sniff(ascii("RIFF") + bytes(0x24, 0x10, 0, 0) + ascii("WAVEfmt ")))
        assertNull(ImageFormat.sniff(ascii("RIFF")))
        assertNull(ImageFormat.sniff(bytes(0xFF, 0xD8)))
        assertNull(ImageFormat.sniff(ByteArray(0)))
    }

    @Test
    fun `photos over the server's limits are left out`() {
        assertNull(photoRejection(ImageFormat.JPEG, bytes = MAX_SCAN_BYTES, pixels = MAX_SCAN_PIXELS))
        assertEquals(PhotoRejection.TOO_LARGE, photoRejection(ImageFormat.JPEG, MAX_SCAN_BYTES + 1, pixels = 12_000_000))
        // A 200-megapixel photo, well under 40 MiB.
        assertEquals(PhotoRejection.TOO_LARGE, photoRejection(ImageFormat.JPEG, 30_000_000, pixels = 16_320L * 12_240))
        assertNull(photoRejection(ImageFormat.WEBP, 1_000, pixels = null))
        assertEquals(PhotoRejection.UNSUPPORTED_FORMAT, photoRejection(null, 1_000, pixels = 1_000))
    }

    @Test
    fun `reads the format of a file`() {
        val png = folder.newFile("photo.png").apply {
            writeBytes(bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A) + ByteArray(1000))
        }
        assertEquals(ImageFormat.PNG, ImageFormat.of(png))
        assertNull(ImageFormat.of(folder.newFile("truncated.jpg").apply { writeBytes(bytes(0xFF, 0xD8)) }))
        assertNull(ImageFormat.of(folder.newFile("empty.jpg")))
    }
}
