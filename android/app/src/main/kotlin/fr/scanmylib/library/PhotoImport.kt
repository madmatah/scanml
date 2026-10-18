package fr.scanmylib.library

import java.io.File
import java.time.DateTimeException
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset

/** Image formats the server accepts for scans; it refuses the others (HEIC, GIF...) for good. */
enum class ImageFormat {
    JPEG,
    PNG,
    WEBP,
    ;

    companion object {
        /** How many leading bytes [sniff] needs. */
        const val SIGNATURE_SIZE = 12

        private val JPEG_SIGNATURE = bytes(0xFF, 0xD8, 0xFF)
        private val PNG_SIGNATURE = bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
        private val RIFF_SIGNATURE = "RIFF".toByteArray(Charsets.US_ASCII)
        private val WEBP_FORM_TYPE = "WEBP".toByteArray(Charsets.US_ASCII)

        /** The format of an image whose file starts with [header], or null if the server refuses it. */
        fun sniff(header: ByteArray): ImageFormat? = when {
            header.startsWith(JPEG_SIGNATURE) -> JPEG

            header.startsWith(PNG_SIGNATURE) -> PNG

            // RIFF container: "RIFF", 4 bytes of size, then the form type.
            header.startsWith(RIFF_SIGNATURE) && header.size >= SIGNATURE_SIZE &&
                header.copyOfRange(8, SIGNATURE_SIZE).contentEquals(WEBP_FORM_TYPE) -> WEBP

            else -> null
        }

        /** The format of the image in [file], or null if the server refuses it. */
        fun of(file: File): ImageFormat? {
            val header = ByteArray(SIGNATURE_SIZE)
            var size = 0
            file.inputStream().use { input ->
                while (size < header.size) {
                    val read = input.read(header, size, header.size - size)
                    if (read < 0) break
                    size += read
                }
            }
            return sniff(header.copyOf(size))
        }

        private fun bytes(vararg values: Int) = ByteArray(values.size) { values[it].toByte() }

        private fun ByteArray.startsWith(prefix: ByteArray) =
            size >= prefix.size && prefix.indices.all { this[it] == prefix[it] }
    }
}

/** Why a chosen photo is left out of an import: the server would refuse it for good. */
enum class PhotoRejection {
    /** HEIC, GIF... (HTTP 415). */
    UNSUPPORTED_FORMAT,

    /** Over the server's limits, [MAX_SCAN_BYTES] or [MAX_SCAN_PIXELS] (HTTP 413). */
    TOO_LARGE,
}

/** Largest scan file the server accepts. */
const val MAX_SCAN_BYTES = 40L * 1024 * 1024

/** Most pixels (width × height) the server accepts in a scan. */
const val MAX_SCAN_PIXELS = 120_000_000L

/**
 * Whether the server would refuse a photo in [format] (null: not one it accepts), of [bytes] bytes
 * and [pixels] pixels (null if unknown); null if it accepts it.
 */
fun photoRejection(format: ImageFormat?, bytes: Long, pixels: Long?): PhotoRejection? = when {
    format == null -> PhotoRejection.UNSUPPORTED_FORMAT
    bytes > MAX_SCAN_BYTES || (pixels != null && pixels > MAX_SCAN_PIXELS) -> PhotoRejection.TOO_LARGE
    else -> null
}

/** Years the server accepts in `captured_at`: it refuses a page dated otherwise (HTTP 422). */
private val CAPTURE_YEARS = 2000..2200

/** EXIF date and time: "2026:10:12 20:15:30" (some cameras write dashes in the date). */
private val EXIF_DATE_TIME = Regex("""^(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})""")

/**
 * When a photo was taken, from its EXIF tags: `DateTimeOriginal` ("2026:10:12 20:15:30"), refined
 * by `SubSecTimeOriginal` ("123") and placed in time by `OffsetTimeOriginal` ("+02:00") when the
 * camera wrote them; without an offset, the time is read in [zone].
 *
 * @return null when the date is missing, invalid (cameras write "0000:00:00 00:00:00" or blanks
 *   when their clock is not set), or outside the years the server accepts.
 */
fun exifCaptureTime(dateTime: String?, subSeconds: String?, offset: String?, zone: ZoneId): Instant? {
    val match = dateTime?.trim()?.let(EXIF_DATE_TIME::find) ?: return null
    val (year, month, day, hour, minute, second) = match.destructured
    val nanos = subSeconds?.trim()?.takeWhile { it in '0'..'9' }?.take(9)?.padEnd(9, '0')?.toInt() ?: 0
    val time = try {
        LocalDateTime.of(year.toInt(), month.toInt(), day.toInt(), hour.toInt(), minute.toInt(), second.toInt(), nanos)
    } catch (e: DateTimeException) {
        return null
    }
    val zoneOffset = offset?.trim()?.let {
        try {
            ZoneOffset.of(it)
        } catch (e: DateTimeException) {
            null
        }
    }
    val instant = if (zoneOffset != null) time.toInstant(zoneOffset) else time.atZone(zone).toInstant()
    return instant.takeIf { it.atZone(zone).year in CAPTURE_YEARS }
}

/**
 * Orders photos by the time they were taken: dated photos first, oldest first, then the photos
 * without a date, in their original order. Photos taken at the same time keep their order too.
 */
fun <T> orderByCaptureTime(photos: List<T>, takenAt: (T) -> Instant?): List<T> =
    photos.sortedWith(compareBy(nullsLast<Instant>()) { takenAt(it) })
