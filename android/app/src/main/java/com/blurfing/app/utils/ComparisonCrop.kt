package com.blurfing.app.utils

import com.blurfing.app.model.NormalizedRegion
import kotlin.math.ceil
import kotlin.math.floor

data class ComparisonCrop(val left: Int, val top: Int, val width: Int, val height: Int) {
    companion object {
        /** One rectangle is shared by both images; zoom changes only rendering, never image data. */
        fun calculate(width: Int, height: Int, region: NormalizedRegion?, zoom: Float): ComparisonCrop {
            require(width > 0 && height > 0 && zoom.isFinite() && zoom in 1f..4f)
            val centerX = region?.let { it.x + it.width / 2 } ?: .5f
            val centerY = region?.let { it.y + it.height / 2 } ?: .5f
            val spanX = ((region?.width?.times(1.4f) ?: 1f) / zoom).coerceAtMost(1f)
            val spanY = ((region?.height?.times(1.4f) ?: 1f) / zoom).coerceAtMost(1f)
            val x = (centerX - spanX / 2).coerceIn(0f, 1f - spanX)
            val y = (centerY - spanY / 2).coerceIn(0f, 1f - spanY)
            val left = floor(x * width).toInt().coerceIn(0, width - 1)
            val top = floor(y * height).toInt().coerceIn(0, height - 1)
            val right = ceil((x + spanX) * width).toInt().coerceIn(left + 1, width)
            val bottom = ceil((y + spanY) * height).toInt().coerceIn(top + 1, height)
            return ComparisonCrop(left, top, right - left, bottom - top)
        }
    }
}
