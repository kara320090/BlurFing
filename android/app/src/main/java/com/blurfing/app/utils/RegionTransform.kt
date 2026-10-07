package com.blurfing.app.utils

import com.blurfing.app.model.NormalizedRegion

enum class RegionCorner { TOP_LEFT, TOP_RIGHT, BOTTOM_LEFT, BOTTOM_RIGHT }
object RegionTransform {
    fun move(r: NormalizedRegion, dx: Float, dy: Float) = r.copy(
        x = (r.x + dx).coerceIn(0f, (1f-r.width).coerceAtLeast(0f)),
        y = (r.y + dy).coerceIn(0f, (1f-r.height).coerceAtLeast(0f)))

    fun resize(r: NormalizedRegion, corner: RegionCorner, dx: Float, dy: Float,
        minWidth: Float = .01f, minHeight: Float = .01f): NormalizedRegion {
        val leftEdge = corner == RegionCorner.TOP_LEFT || corner == RegionCorner.BOTTOM_LEFT
        val topEdge = corner == RegionCorner.TOP_LEFT || corner == RegionCorner.TOP_RIGHT
        val right = r.x + r.width
        val bottom = r.y + r.height
        val w = minOf(minWidth, r.width).coerceAtLeast(.00001f)
        val h = minOf(minHeight, r.height).coerceAtLeast(.00001f)
        val left = if (leftEdge) (r.x+dx).coerceIn(0f, right-w) else r.x
        val top = if (topEdge) (r.y+dy).coerceIn(0f, bottom-h) else r.y
        val endX = if (leftEdge) right else (right+dx).coerceIn(left+w, 1f)
        val endY = if (topEdge) bottom else (bottom+dy).coerceIn(top+h, 1f)
        return NormalizedRegion(left, top, endX-left, endY-top)
    }
}
