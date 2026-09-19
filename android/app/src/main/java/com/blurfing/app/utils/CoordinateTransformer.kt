package com.blurfing.app.utils

import android.graphics.RectF
import com.blurfing.app.model.NormalizedRegion
import kotlin.math.min

/**
 * 화면 뷰 좌표(픽셀)와 원본 이미지 상대 좌표(0.0 ~ 1.0) 간의 양방향 변환 유틸리티.
 * 이미지 뷰의 종횡비(Fit/Letterbox) 여백을 정확히 계산하여 좌표계 왜곡을 방지합니다.
 */
object CoordinateTransformer {

    /**
     * 뷰 내에서 이미지가 실제로 그려지는 사각형 영역(Letterbox / Pillarbox 반영)을 계산합니다.
     */
    fun computeImageBoundsInView(
        viewWidth: Float,
        viewHeight: Float,
        imageWidth: Float,
        imageHeight: Float
    ): RectF {
        if (viewWidth <= 0f || viewHeight <= 0f || imageWidth <= 0f || imageHeight <= 0f) {
            return RectF(0f, 0f, 0f, 0f)
        }

        val scale = min(viewWidth / imageWidth, viewHeight / imageHeight)
        val renderedWidth = imageWidth * scale
        val renderedHeight = imageHeight * scale
        val offsetX = (viewWidth - renderedWidth) / 2f
        val offsetY = (viewHeight - renderedHeight) / 2f

        return RectF(offsetX, offsetY, offsetX + renderedWidth, offsetY + renderedHeight)
    }

    /**
     * 화면 터치 좌표 (픽셀)를 정규화된 이미지 상대 좌표(0.0 ~ 1.0)로 변환합니다.
     */
    fun screenPointToNormalized(
        touchX: Float,
        touchY: Float,
        imageBounds: RectF
    ): Pair<Float, Float> {
        val width = imageBounds.width()
        val height = imageBounds.height()
        if (width <= 0f || height <= 0f) return Pair(0f, 0f)

        val normalizedX = ((touchX - imageBounds.left) / width).coerceIn(0f, 1f)
        val normalizedY = ((touchY - imageBounds.top) / height).coerceIn(0f, 1f)
        return Pair(normalizedX, normalizedY)
    }

    /**
     * 정규화된 영역(0.0 ~ 1.0)을 화면 뷰의 픽셀 좌표 사각형으로 변환합니다.
     */
    fun normalizedRegionToScreenRect(
        region: NormalizedRegion,
        imageBounds: RectF
    ): RectF {
        val left = imageBounds.left + (region.x * imageBounds.width())
        val top = imageBounds.top + (region.y * imageBounds.height())
        val right = left + (region.width * imageBounds.width())
        val bottom = top + (region.height * imageBounds.height())
        return RectF(left, top, right, bottom)
    }

    /**
     * 화면상의 사각형을 NormalizedRegion으로 안전하게 변환합니다.
     */
    fun screenRectToNormalizedRegion(
        rect: RectF,
        imageBounds: RectF
    ): NormalizedRegion {
        val (normLeft, normTop) = screenPointToNormalized(rect.left, rect.top, imageBounds)
        val (normRight, normBottom) = screenPointToNormalized(rect.right, rect.bottom, imageBounds)

        val width = (normRight - normLeft).coerceAtLeast(0.01f)
        val height = (normBottom - normTop).coerceAtLeast(0.01f)

        return NormalizedRegion.safeCreate(normLeft, normTop, width, height)
    }
}
