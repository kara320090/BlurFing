package com.blurfing.app

import android.graphics.RectF
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.utils.CoordinateTransformer
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class CoordinateTransformerTest {

    @Test
    fun computeImageBounds_letterbox_horizontalPillars() {
        // 가로가 긴 뷰 (1000 x 500)에 정사각형 이미지 (500 x 500) 배치
        // 스케일은 1.0, 렌더링 폭 500, 높이 500, 좌우 여백 각 250
        val bounds = CoordinateTransformer.computeImageBoundsInView(
            viewWidth = 1000f,
            viewHeight = 500f,
            imageWidth = 500f,
            imageHeight = 500f
        )

        assertEquals(250f, bounds.left, 0.01f)
        assertEquals(0f, bounds.top, 0.01f)
        assertEquals(750f, bounds.right, 0.01f)
        assertEquals(500f, bounds.bottom, 0.01f)
        assertEquals(500f, bounds.width(), 0.01f)
        assertEquals(500f, bounds.height(), 0.01f)
    }

    @Test
    fun computeImageBounds_pillarbox_verticalBars() {
        // 세로가 긴 뷰 (500 x 1000)에 정사각형 이미지 (500 x 500) 배치
        // 스케일은 1.0, 렌더링 폭 500, 높이 500, 상하 여백 각 250
        val bounds = CoordinateTransformer.computeImageBoundsInView(
            viewWidth = 500f,
            viewHeight = 1000f,
            imageWidth = 500f,
            imageHeight = 500f
        )

        assertEquals(0f, bounds.left, 0.01f)
        assertEquals(250f, bounds.top, 0.01f)
        assertEquals(500f, bounds.right, 0.01f)
        assertEquals(750f, bounds.bottom, 0.01f)
    }

    @Test
    fun screenPointToNormalized_roundTrip() {
        val imageBounds = RectF(100f, 200f, 900f, 1000f) // width=800, height=800

        // 정규화 좌표 (0.25, 0.5) -> 화면 좌표
        val region = NormalizedRegion(0.25f, 0.5f, 0.2f, 0.3f)
        val screenRect = CoordinateTransformer.normalizedRegionToScreenRect(region, imageBounds)

        assertEquals(300f, screenRect.left, 0.01f) // 100 + 0.25 * 800 = 300
        assertEquals(600f, screenRect.top, 0.01f)  // 200 + 0.5 * 800 = 600
        assertEquals(460f, screenRect.right, 0.01f) // 300 + 0.2 * 800 = 460
        assertEquals(840f, screenRect.bottom, 0.01f) // 600 + 0.3 * 800 = 840

        // 다시 화면 좌표 -> 정규화 좌표 역변환
        val reconstructed = CoordinateTransformer.screenRectToNormalizedRegion(screenRect, imageBounds)
        assertEquals(region.x, reconstructed.x, 0.001f)
        assertEquals(region.y, reconstructed.y, 0.001f)
        assertEquals(region.width, reconstructed.width, 0.001f)
        assertEquals(region.height, reconstructed.height, 0.001f)
    }

    @Test
    fun screenPoint_outsideBounds_clampsToZeroOne() {
        val imageBounds = RectF(100f, 100f, 500f, 500f)

        // 이미지 영역 왼쪽/위쪽 바깥 터치
        val (normX1, normY1) = CoordinateTransformer.screenPointToNormalized(50f, 50f, imageBounds)
        assertEquals(0f, normX1, 0.001f)
        assertEquals(0f, normY1, 0.001f)

        // 이미지 영역 오른쪽/아래쪽 바깥 터치
        val (normX2, normY2) = CoordinateTransformer.screenPointToNormalized(600f, 600f, imageBounds)
        assertEquals(1f, normX2, 0.001f)
        assertEquals(1f, normY2, 0.001f)
    }
}
