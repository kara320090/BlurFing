package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.ui.screens.ComparisonScreen
import com.blurfing.app.ui.theme.BlurFingTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ComparisonDeviceTest {
    @get:Rule val compose = createComposeRule()

    @Test fun synchronizedRegionZoomAndUnmeasuredReportRemainUsable() {
        val original = Bitmap.createBitmap(120, 160, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        val processed = Bitmap.createBitmap(120, 160, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.RED) }
        var saves = 0
        compose.setContent {
            BlurFingTheme {
                ComparisonScreen(original, processed,
                    ProtectionResponse("synthetic-ui", "succeeded", "mock", appliedRegions = listOf(NormalizedRegion(.1f, .2f, .2f, .2f))),
                    onSaveProtectedImage = { saves++ }, onBack = {})
            }
        }
        compose.onNodeWithText("나란히 비교").performClick()
        compose.onNodeWithText("영역 1").performClick()
        compose.onNodeWithContentDescription("원본 이미지").assertIsDisplayed()
        compose.onNodeWithContentDescription("보호본 이미지").assertIsDisplayed()
        compose.onNodeWithContentDescription("비교 확대 배율").performScrollTo()
            .performSemanticsAction(SemanticsActions.SetProgress) { it(3f) }
        compose.onNodeWithText("영역 1 · 추가 확대 3.0배").assertExists()
        compose.onNodeWithText("미측정 · Mock 프리뷰는 실제 지문 평가가 아닙니다.").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("보호 사본 저장 (원본 보존)").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(1, saves)
            assertEquals(120, processed.width)
            assertEquals(160, processed.height)
            assertEquals(Color.BLUE, original.getPixel(0, 0))
        }
    }
}
