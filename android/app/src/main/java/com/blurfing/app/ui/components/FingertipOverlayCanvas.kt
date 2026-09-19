package com.blurfing.app.ui.components

import android.graphics.RectF
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.utils.CoordinateTransformer

/**
 * 손끝 지문 영역 후보 오버레이 및 인터랙티브 편집 캔버스.
 * 사용자가 손끝 지문 패드 영역을 드래그하여 이동하거나 조절할 수 있습니다.
 */
@Composable
fun FingertipOverlayCanvas(
    regions: List<NormalizedRegion>,
    imageBounds: RectF,
    selectedRegionIndex: Int?,
    onRegionSelected: (Int) -> Unit,
    onRegionUpdated: (Int, NormalizedRegion) -> Unit,
    modifier: Modifier = Modifier
) {
    var draggingIndex by remember { mutableStateOf<Int?>(null) }
    var dragStartOffset by remember { mutableStateOf<Offset?>(null) }

    Canvas(
        modifier = modifier
            .fillMaxSize()
            .pointerInput(regions, imageBounds) {
                detectDragGestures(
                    onDragStart = { offset ->
                        // 터치 지점이 포함된 영역 찾기
                        val hitIndex = regions.indices.reversed().firstOrNull { index ->
                            val screenRect = CoordinateTransformer.normalizedRegionToScreenRect(
                                regions[index],
                                imageBounds
                            )
                            screenRect.contains(offset.x, offset.y)
                        }
                        draggingIndex = hitIndex
                        if (hitIndex != null) {
                            onRegionSelected(hitIndex)
                            dragStartOffset = offset
                        }
                    },
                    onDrag = { change, dragAmount ->
                        change.consume()
                        val currentIndex = draggingIndex ?: return@detectDragGestures
                        val currentRegion = regions.getOrNull(currentIndex) ?: return@detectDragGestures

                        val screenRect = CoordinateTransformer.normalizedRegionToScreenRect(
                            currentRegion,
                            imageBounds
                        )
                        screenRect.offset(dragAmount.x, dragAmount.y)

                        // 뷰 경계 내로 클램핑하여 NormalizedRegion 업데이트
                        val updatedRegion = CoordinateTransformer.screenRectToNormalizedRegion(
                            screenRect,
                            imageBounds
                        )
                        onRegionUpdated(currentIndex, updatedRegion)
                    },
                    onDragEnd = {
                        draggingIndex = null
                        dragStartOffset = null
                    },
                    onDragCancel = {
                        draggingIndex = null
                        dragStartOffset = null
                    }
                )
            }
    ) {
        if (imageBounds.width() <= 0f || imageBounds.height() <= 0f) return@Canvas

        regions.forEachIndexed { index, region ->
            val screenRect = CoordinateTransformer.normalizedRegionToScreenRect(region, imageBounds)
            val isSelected = index == selectedRegionIndex

            val strokeColor = if (isSelected) Color(0xFFFF5722) else Color(0xFF00E676)
            val fillColor = strokeColor.copy(alpha = 0.15f)

            // 영역 내부 반투명 채우기
            drawRect(
                color = fillColor,
                topLeft = Offset(screenRect.left, screenRect.top),
                size = Size(screenRect.width(), screenRect.height())
            )

            // 경계선 (선택 시 실선, 미선택 시 점선)
            val pathEffect = if (isSelected) null else PathEffect.dashPathEffect(floatArrayOf(15f, 10f), 0f)
            drawRect(
                color = strokeColor,
                topLeft = Offset(screenRect.left, screenRect.top),
                size = Size(screenRect.width(), screenRect.height()),
                style = Stroke(width = if (isSelected) 4f else 3f, pathEffect = pathEffect)
            )

            // 모서리 핸들 그리기
            val handleRadius = 10f
            drawCircle(color = strokeColor, radius = handleRadius, center = Offset(screenRect.left, screenRect.top))
            drawCircle(color = strokeColor, radius = handleRadius, center = Offset(screenRect.right, screenRect.top))
            drawCircle(color = strokeColor, radius = handleRadius, center = Offset(screenRect.left, screenRect.bottom))
            drawCircle(color = strokeColor, radius = handleRadius, center = Offset(screenRect.right, screenRect.bottom))
        }
    }
}
