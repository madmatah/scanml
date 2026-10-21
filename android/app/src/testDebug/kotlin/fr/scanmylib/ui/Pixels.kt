package fr.scanmylib.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.graphics.drawable.Drawable

internal data class PixelPosition(val x: Int, val y: Int)

internal fun drawOnBitmap(drawable: Drawable, sizePixels: Int): Bitmap {
    val bitmap = Bitmap.createBitmap(sizePixels, sizePixels, Bitmap.Config.ARGB_8888)
    drawable.setBounds(0, 0, sizePixels, sizePixels)
    drawable.draw(Canvas(bitmap))
    return bitmap
}

internal fun gatherPixelsNear(pixels: List<PixelPosition>, drawing: Bitmap, radiusPixels: Int): List<PixelPosition> {
    val drawingAlphas = readAlphas(drawing)
    val offsets = (-radiusPixels..radiusPixels).flatMap { rowOffset ->
        (-radiusPixels..radiusPixels).map { columnOffset -> PixelPosition(columnOffset, rowOffset) }
    }.filter { it.x * it.x + it.y * it.y <= radiusPixels * radiusPixels }
    return pixels.filter { pixel ->
        offsets.any { offset ->
            val column = pixel.x + offset.x
            val row = pixel.y + offset.y
            val isInside = column in 0 until drawing.width && row in 0 until drawing.height
            isInside && drawingAlphas[row * drawing.width + column] > 0
        }
    }
}

private fun readAlphas(bitmap: Bitmap): IntArray {
    val colors = IntArray(bitmap.width * bitmap.height)
    bitmap.getPixels(colors, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
    return IntArray(colors.size) { AndroidColor.alpha(colors[it]) }
}

internal fun gatherDrawnPixels(bitmap: Bitmap): List<PixelPosition> {
    val alphas = readAlphas(bitmap)
    return listPixelPositions(bitmap.width, bitmap.height).filter { alphas[it.y * bitmap.width + it.x] > 0 }
}

private fun listPixelPositions(width: Int, height: Int): List<PixelPosition> =
    (0 until height).flatMap { row -> (0 until width).map { column -> PixelPosition(column, row) } }
