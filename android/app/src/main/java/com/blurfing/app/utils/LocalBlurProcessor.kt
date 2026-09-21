package com.blurfing.app.utils

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import com.blurfing.app.model.NormalizedRegion
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * 로컬 가우시안/박스 블러 처리 유틸리티.
 * 개발용 Mock 프리뷰 및 오프라인 처리를 지원합니다.
 *
 * 주의: 본 블러 구현은 UI 프리뷰 및 기능 검증용이며,
 * AI 보호 알고리즘(유재윤 담당)의 공식 방어 성능으로 주장하지 않습니다.
 */
object LocalBlurProcessor {

    /**
     * 지정된 정규화 영역들에 블러 효과를 적용한 새로운 비트맵 사본을 생성합니다.
     * 원본 비트맵은 수정하지 않습니다.
     */
    fun applyBlur(
        sourceBitmap: Bitmap,
        regions: List<NormalizedRegion>,
        strength: Float = 0.5f
    ): Bitmap {
        val outputBitmap = sourceBitmap.copy(sourceBitmap.config ?: Bitmap.Config.ARGB_8888, true)
        val canvas = Canvas(outputBitmap)
        val paint = Paint(Paint.FILTER_BITMAP_FLAG)

        val imageWidth = sourceBitmap.width
        val imageHeight = sourceBitmap.height

        // 강도(0.1 ~ 1.0)에 따른 축소 비율 (다운샘플링 후 업샘플링을 통한 고속 블러)
        val scaleDownFactor = (2 + (strength * 18)).roundToInt().coerceIn(2, 20)

        for (region in regions) {
            val left = (region.x * imageWidth).roundToInt().coerceIn(0, imageWidth - 1)
            val top = (region.y * imageHeight).roundToInt().coerceIn(0, imageHeight - 1)
            val width = (region.width * imageWidth).roundToInt().coerceAtLeast(1)
            val height = (region.height * imageHeight).roundToInt().coerceAtLeast(1)

            val right = (left + width).coerceAtMost(imageWidth)
            val bottom = (top + height).coerceAtMost(imageHeight)

            val regionWidth = right - left
            val regionHeight = bottom - top
            if (regionWidth <= 0 || regionHeight <= 0) continue

            // 1. 해당 영역 크롭
            val cropped = Bitmap.createBitmap(sourceBitmap, left, top, regionWidth, regionHeight)

            // 2. 다운샘플링하여 디테일 손실 유도
            val downWidth = max(1, regionWidth / scaleDownFactor)
            val downHeight = max(1, regionHeight / scaleDownFactor)
            val downscaled = Bitmap.createScaledBitmap(cropped, downWidth, downHeight, true)

            // 3. 다시 원본 크기로 업샘플링하여 부드러운 블러 효과 생성
            val blurred = Bitmap.createScaledBitmap(downscaled, regionWidth, regionHeight, true)

            // 4. 대상 비트맵에 합성
            canvas.drawBitmap(blurred, null, Rect(left, top, right, bottom), paint)

            // createBitmap/createScaledBitmap은 크기가 같으면 입력 객체를 돌려줄 수 있다.
            listOf(cropped, downscaled, blurred).distinct().forEach {
                if (it !== sourceBitmap && it !== outputBitmap && !it.isRecycled) it.recycle()
            }
        }

        return outputBitmap
    }
}
