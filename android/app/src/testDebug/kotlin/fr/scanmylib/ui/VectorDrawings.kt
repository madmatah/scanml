package fr.scanmylib.ui

import android.content.res.XmlResourceParser
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.graphics.Paint
import android.graphics.Path
import androidx.compose.ui.graphics.asAndroidPath
import androidx.compose.ui.graphics.vector.PathNode
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.graphics.vector.toPath
import org.robolectric.RuntimeEnvironment
import org.xmlpull.v1.XmlPullParser

private const val ANDROID_NAMESPACE = "http://schemas.android.com/apk/res/android"
private const val DEFAULT_STROKE_MITER = 4f

internal data class Translation(val x: Float, val y: Float)

internal data class PathPaint(
    val fillColor: Int = AndroidColor.TRANSPARENT,
    val fillAlpha: Float = 1f,
    val fillType: Path.FillType = Path.FillType.WINDING,
    val strokeColor: Int = AndroidColor.TRANSPARENT,
    val strokeAlpha: Float = 1f,
    val strokeWidthUnits: Float = 0f,
    val strokeCap: Paint.Cap = Paint.Cap.BUTT,
    val strokeJoin: Paint.Join = Paint.Join.MITER,
    val strokeMiter: Float = DEFAULT_STROKE_MITER,
) {
    val isFilled: Boolean get() = AndroidColor.alpha(fillColor) > 0
}

internal data class PathRecord(
    val groupNames: List<String>,
    val translationUnits: Translation,
    val nodes: List<PathNode>,
    val paint: PathPaint,
)

internal data class VectorDrawing(
    val viewportWidthUnits: Float,
    val viewportHeightUnits: Float,
    val records: List<PathRecord>,
)

internal data class AdaptiveIconLayers(val foreground: VectorDrawing, val monochrome: VectorDrawing)

internal fun readAdaptiveIconLayers(mipmapId: Int): AdaptiveIconLayers {
    val layerIds = mutableMapOf<String, Int>()
    openXml(mipmapId).use { parser ->
        forEachStartTag(parser) { tag ->
            when (tag) {
                "adaptive-icon" -> refuseUnmodeledAttributes(parser, allowed = emptySet())

                "background" -> refuseUnmodeledAttributes(parser, allowed = setOf("drawable"))

                "foreground", "monochrome" -> {
                    refuseUnmodeledAttributes(parser, allowed = setOf("drawable"))
                    layerIds[tag] = parser.getAttributeResourceValue(ANDROID_NAMESPACE, "drawable", 0)
                }

                else -> throw IllegalArgumentException("the icon holds a <$tag>, which the reader does not model")
            }
        }
    }
    val foregroundId = requireNotNull(layerIds["foreground"]?.takeIf { it != 0 }) { "the icon names no foreground" }
    val monochromeId = requireNotNull(layerIds["monochrome"]?.takeIf { it != 0 }) { "the icon names no monochrome" }
    return AdaptiveIconLayers(readVectorDrawing(foregroundId), readVectorDrawing(monochromeId))
}

internal fun readVectorDrawing(drawableId: Int): VectorDrawing {
    var viewportWidthUnits = Float.NaN
    var viewportHeightUnits = Float.NaN
    val records = mutableListOf<PathRecord>()
    val groups = ArrayDeque<VectorGroup>()
    openXml(drawableId).use { parser ->
        forEachEvent(parser) { event ->
            when (event) {
                XmlPullParser.START_TAG -> when (val tag = parser.name) {
                    "vector" -> {
                        refuseUnmodeledAttributes(parser, allowed = VECTOR_ATTRIBUTES)
                        viewportWidthUnits =
                            parser.getAttributeFloatValue(ANDROID_NAMESPACE, "viewportWidth", Float.NaN)
                        viewportHeightUnits =
                            parser.getAttributeFloatValue(ANDROID_NAMESPACE, "viewportHeight", Float.NaN)
                    }

                    "group" -> groups.addLast(readGroup(parser))

                    "path" -> records += readPath(parser, groups)

                    else -> throw IllegalArgumentException("the vector holds a <$tag>, which the reader does not model")
                }

                XmlPullParser.END_TAG -> if (parser.name == "group") groups.removeLast()
            }
        }
    }
    require(!viewportWidthUnits.isNaN() && !viewportHeightUnits.isNaN()) { "the vector has no viewport" }
    return VectorDrawing(viewportWidthUnits, viewportHeightUnits, records)
}

internal fun PathRecord.repaintIn(color: Int): PathRecord = copy(
    paint = paint.copy(fillColor = repaint(paint.fillColor, color), strokeColor = repaint(paint.strokeColor, color)),
)

internal fun PathRecord.shiftBy(shiftUnits: Translation): PathRecord =
    copy(translationUnits = addTranslations(translationUnits, shiftUnits))

internal fun drawRecords(records: List<PathRecord>, sizePixels: Int, pixelsPerUnit: Float): Bitmap {
    val bitmap = Bitmap.createBitmap(sizePixels, sizePixels, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    records.forEach { record ->
        val path = record.nodes.toPath().asAndroidPath().apply { fillType = record.paint.fillType }
        canvas.save()
        canvas.scale(pixelsPerUnit, pixelsPerUnit)
        canvas.translate(record.translationUnits.x, record.translationUnits.y)
        if (record.paint.isFilled) canvas.drawPath(path, fillPaint(record.paint))
        if (AndroidColor.alpha(record.paint.strokeColor) > 0 && record.paint.strokeWidthUnits > 0f) {
            canvas.drawPath(path, strokePaint(record.paint))
        }
        canvas.restore()
    }
    return bitmap
}

private data class VectorGroup(val name: String?, val translationUnits: Translation)

private val VECTOR_ATTRIBUTES = setOf("width", "height", "viewportWidth", "viewportHeight")
private val GROUP_ATTRIBUTES = setOf("name", "translateX", "translateY")
private val PATH_ATTRIBUTES = setOf(
    "pathData",
    "fillColor",
    "fillAlpha",
    "fillType",
    "strokeColor",
    "strokeAlpha",
    "strokeWidth",
    "strokeLineCap",
    "strokeLineJoin",
    "strokeMiterLimit",
)

private fun openXml(resourceId: Int): XmlResourceParser =
    RuntimeEnvironment.getApplication().resources.getXml(resourceId)

private fun forEachEvent(parser: XmlResourceParser, onEvent: (Int) -> Unit) {
    var event = parser.next()
    while (event != XmlPullParser.END_DOCUMENT) {
        onEvent(event)
        event = parser.next()
    }
}

private fun forEachStartTag(parser: XmlResourceParser, onStartTag: (String) -> Unit) =
    forEachEvent(parser) { event -> if (event == XmlPullParser.START_TAG) onStartTag(parser.name) }

private fun refuseUnmodeledAttributes(parser: XmlResourceParser, allowed: Set<String>) {
    (0 until parser.attributeCount).forEach { index ->
        val name = parser.getAttributeName(index)
        require(parser.getAttributeNamespace(index) == ANDROID_NAMESPACE && name in allowed) {
            "<${parser.name}> has the attribute $name, which the reader does not model"
        }
    }
}

private fun readGroup(parser: XmlResourceParser): VectorGroup {
    refuseUnmodeledAttributes(parser, allowed = GROUP_ATTRIBUTES)
    return VectorGroup(
        name = parser.getAttributeValue(ANDROID_NAMESPACE, "name"),
        translationUnits = Translation(
            parser.getAttributeFloatValue(ANDROID_NAMESPACE, "translateX", 0f),
            parser.getAttributeFloatValue(ANDROID_NAMESPACE, "translateY", 0f),
        ),
    )
}

private fun readPath(parser: XmlResourceParser, groups: List<VectorGroup>): List<PathRecord> {
    refuseUnmodeledAttributes(parser, allowed = PATH_ATTRIBUTES)
    val paint = PathPaint(
        fillColor = readColor(parser, "fillColor"),
        fillAlpha = parser.getAttributeFloatValue(ANDROID_NAMESPACE, "fillAlpha", 1f),
        fillType = Path.FillType.entries[parser.getAttributeIntValue(ANDROID_NAMESPACE, "fillType", 0)],
        strokeColor = readColor(parser, "strokeColor"),
        strokeAlpha = parser.getAttributeFloatValue(ANDROID_NAMESPACE, "strokeAlpha", 1f),
        strokeWidthUnits = parser.getAttributeFloatValue(ANDROID_NAMESPACE, "strokeWidth", 0f),
        strokeCap = Paint.Cap.entries[parser.getAttributeIntValue(ANDROID_NAMESPACE, "strokeLineCap", 0)],
        strokeJoin = Paint.Join.entries[parser.getAttributeIntValue(ANDROID_NAMESPACE, "strokeLineJoin", 0)],
        strokeMiter = parser.getAttributeFloatValue(ANDROID_NAMESPACE, "strokeMiterLimit", DEFAULT_STROKE_MITER),
    )
    val nodes = addPathNodes(parser.getAttributeValue(ANDROID_NAMESPACE, "pathData"))
    val groupNames = groups.mapNotNull { it.name }
    val translationUnits = groups.map { it.translationUnits }.fold(Translation(0f, 0f), ::addTranslations)
    val subpaths = if (paint.isFilled) listOf(nodes) else splitIntoSubpaths(nodes)
    return subpaths.map { PathRecord(groupNames, translationUnits, it, paint) }
}

private fun readColor(parser: XmlResourceParser, attribute: String): Int {
    require(parser.getAttributeValue(ANDROID_NAMESPACE, attribute)?.startsWith("?") != true) {
        "<${parser.name}> takes its $attribute from the theme, which the reader does not model"
    }
    val colorId = parser.getAttributeResourceValue(ANDROID_NAMESPACE, attribute, 0)
    return if (colorId != 0) {
        RuntimeEnvironment.getApplication().resources.getColor(colorId, null)
    } else {
        parser.getAttributeIntValue(ANDROID_NAMESPACE, attribute, AndroidColor.TRANSPARENT)
    }
}

private fun splitIntoSubpaths(nodes: List<PathNode>): List<List<PathNode>> {
    require(nodes.drop(1).none { it is PathNode.RelativeMoveTo }) {
        "a relative move starts a later subpath, which would move once split from the subpath before it"
    }
    val starts = nodes.indices.filter { nodes[it] is PathNode.MoveTo || nodes[it] is PathNode.RelativeMoveTo }
    require(starts.firstOrNull() == 0) { "the path does not start with a move" }
    return starts.zip(starts.drop(1) + nodes.size) { start, end -> nodes.subList(start, end).toList() }
}

private fun addTranslations(first: Translation, second: Translation): Translation =
    Translation(first.x + second.x, first.y + second.y)

private fun repaint(color: Int, newColor: Int): Int = if (AndroidColor.alpha(color) == 0) {
    color
} else {
    (color and AndroidColor.BLACK) or (newColor and AndroidColor.BLACK.inv())
}

private fun fillPaint(paint: PathPaint): Paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
    style = Paint.Style.FILL
    color = multiplyAlpha(paint.fillColor, paint.fillAlpha)
}

private fun strokePaint(paint: PathPaint): Paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
    style = Paint.Style.STROKE
    color = multiplyAlpha(paint.strokeColor, paint.strokeAlpha)
    strokeWidth = paint.strokeWidthUnits
    strokeCap = paint.strokeCap
    strokeJoin = paint.strokeJoin
    strokeMiter = paint.strokeMiter
}

private fun multiplyAlpha(color: Int, alpha: Float): Int = AndroidColor.argb(
    (AndroidColor.alpha(color) * alpha).toInt(),
    AndroidColor.red(color),
    AndroidColor.green(color),
    AndroidColor.blue(color),
)
