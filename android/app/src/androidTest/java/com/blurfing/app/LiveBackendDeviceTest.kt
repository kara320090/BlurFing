package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.repository.ApiProtectionRepository
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.runBlocking
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

/** Opt-in: talks over TCP to backend/main.py, not MockWebServer. */
@RunWith(AndroidJUnit4::class)
class LiveBackendDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val vm get() = ViewModelProvider(compose.activity)[BlurFingViewModel::class.java]
    private fun address(key: String): String {
        val address = InstrumentationRegistry.getArguments().getString(key)
        assumeTrue("Run android/integration/run_device_integration.py to supply local servers", address != null)
        require(address!!.startsWith("http://127.0.0.1:")) { "Only local synthetic integration is allowed" }
        return address
    }
    private fun image(): ByteArray {
        val bitmap = Bitmap.createBitmap(16, 20, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        return ByteArrayOutputStream().use {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)
            bitmap.recycle()
            it.toByteArray()
        }
    }
    private fun load(): File {
        val file = File(compose.activity.cacheDir, "backend-synthetic.png").apply { writeBytes(image()) }
        compose.runOnUiThread { vm.onImageSelected(Uri.fromFile(file), compose.activity) }
        compose.waitUntil(10_000) { vm.uiState.value is UiState.Ready }
        compose.runOnUiThread { vm.addRegion(); vm.addRegion() }
        return file
    }

    @Test fun unavailableTeamProcessorKeepsPhotoAndSupportsExplicitLocalPreview() {
        val base = address("liveBackendUrl")
        val file = load()
        try {
            val loaded = vm.uiState.value as UiState.Ready
            compose.onNodeWithText("선택 삭제").performClick()
            val regions = (vm.uiState.value as UiState.Ready).regions
            compose.runOnUiThread { vm.updateSettings(ProcessingSettings(useServer = true, serverAddress = base)) }
            compose.onNodeWithText("보호 설정 (BF-04)").performClick()
            compose.onNodeWithText("서버로 전송 및 처리").performScrollTo().performClick()
            compose.waitUntil(15_000) { (vm.uiState.value as? UiState.Ready)?.processingError != null }
            compose.runOnIdle {
                val failed = vm.uiState.value as UiState.Ready
                assertTrue(failed.processingError.orEmpty().contains("일시적으로"))
                assertSame(loaded.originalBitmap, failed.originalBitmap)
                assertEquals(regions, failed.regions)
                assertNull(failed.protectedBitmap)
            }
            compose.onNode(isToggleable()).performScrollTo().performClick()
            compose.onNodeWithText("Mock 프리뷰 만들기").performScrollTo().performClick()
            compose.waitUntil(10_000) { (vm.uiState.value as? UiState.Ready)?.step == ScreenStep.COMPARISON }
            compose.runOnIdle { assertEquals("mock", (vm.uiState.value as UiState.Ready).protectionResponse!!.resultKind) }
        } finally {
            compose.runOnUiThread { vm.resetToIdle(); vm.updateSettings(ProcessingSettings()) }
            file.delete()
        }
    }

    @Test fun actualNoRegionsResponseIsNotDisplayedAsProtectionSuccess() = runBlocking {
        val base = address("liveBackendUrl")
        val result = ApiProtectionRepository(base).protectImage(ProtectionRequest("synthetic-empty", regions = emptyList()), image())
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()?.message.orEmpty().contains("영역이 없습니다"))
    }

    @Test fun missingRequiredFieldsHaveNormalizedTeamErrorEnvelope() {
        val base = address("liveBackendUrl")
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("request_id", "synthetic-missing-fields").build()
        val client = OkHttpClient()
        try {
            client.newCall(Request.Builder().url("$base/v1/protect").post(body).build()).execute().use {
                assertEquals(400, it.code)
                val error = JSONObject(it.body!!.string())
                assertEquals("synthetic-missing-fields", error.getString("request_id"))
                assertEquals("INVALID_REQUEST", error.getString("code"))
                assertFalse(error.getBoolean("retryable"))
            }
        } finally { client.connectionPool.evictAll(); client.dispatcher.executorService.shutdown() }
    }

    @Test fun controlledProcessorThroughActualBackendReturnsPixelsToComparison() {
        val base = address("fixtureBackendUrl")
        val file = load()
        try {
            compose.runOnUiThread { vm.startProtection(serverUrl = base) }
            compose.waitUntil(15_000) { (vm.uiState.value as? UiState.Ready)?.let { !it.isProcessing } == true }
            compose.runOnIdle {
                val ready = vm.uiState.value as UiState.Ready
                assertNull(ready.processingError)
                assertEquals(ScreenStep.COMPARISON, ready.step)
                assertEquals(Color.RED, ready.protectedBitmap!!.getPixel(0, 0))
                assertEquals(Color.BLUE, ready.originalBitmap.getPixel(0, 0))
                assertEquals(16, ready.protectedBitmap.width)
                assertEquals(20, ready.protectedBitmap.height)
                assertNull(ready.protectionResponse!!.evaluation)
            }
            compose.onNodeWithText("미측정 · 평가 엔진의 측정 결과가 아직 없습니다.").performScrollTo().assertIsDisplayed()
        } finally {
            compose.runOnUiThread { vm.resetToIdle() }
            file.delete()
        }
    }
}
