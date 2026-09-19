package com.blurfing.app.model

import kotlinx.serialization.Serializable

/**
 * 상대 좌표로 표현된 영역 (0.0 ~ 1.0).
 * contracts/protection-api.md 규격:
 * x, y, width, height는 모두 0~1의 상대값이며 width, height는 양수, x + width <= 1, y + height <= 1을 만족해야 합니다.
 */
@Serializable
data class NormalizedRegion(
    val x: Float,
    val y: Float,
    val width: Float,
    val height: Float
) {
    init {
        require(x in 0f..1f) { "x는 0.0과 1.0 사이여야 합니다: $x" }
        require(y in 0f..1f) { "y는 0.0과 1.0 사이여야 합니다: $y" }
        require(width > 0f) { "width는 양수여야 합니다: $width" }
        require(height > 0f) { "height는 양수여야 합니다: $height" }
        require(x + width <= 1.0001f) { "x + width는 1.0을 초과할 수 없습니다: ${x + width}" }
        require(y + height <= 1.0001f) { "y + height는 1.0을 초과할 수 없습니다: ${y + height}" }
    }

    companion object {
        /**
         * 임의의 부동소수점 좌표를 안전하게 0..1 및 경계 내로 클램핑하여 생성합니다.
         */
        fun safeCreate(x: Float, y: Float, width: Float, height: Float): NormalizedRegion {
            val clampedX = x.coerceIn(0f, 0.99f)
            val clampedY = y.coerceIn(0f, 0.99f)
            val maxWidth = 1f - clampedX
            val maxHeight = 1f - clampedY
            val clampedWidth = width.coerceIn(0.01f, maxWidth)
            val clampedHeight = height.coerceIn(0.01f, maxHeight)
            return NormalizedRegion(clampedX, clampedY, clampedWidth, clampedHeight)
        }
    }
}
