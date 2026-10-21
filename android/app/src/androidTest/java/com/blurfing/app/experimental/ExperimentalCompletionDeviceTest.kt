package com.blurfing.app.experimental

import com.blurfing.app.captureDesignArtifact

import android.content.pm.PackageManager
import android.net.Uri
import android.graphics.Bitmap
import android.graphics.Color
import androidx.exifinterface.media.ExifInterface
import com.blurfing.app.utils.CameraCaptureFiles
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

/** Real Activity + TCP + public synthetic PNG, with a controlled response, never an AI score. */
@RunWith(AndroidJUnit4::class)
class ExperimentalCompletionDeviceTest {
    @get:Rule val compose=createAndroidComposeRule<ExperimentalPhotoActivity>()
    private val model get()=ViewModelProvider(compose.activity)[ExperimentalPhotoViewModel::class.java]
    private fun asset(name: String)=InstrumentationRegistry.getInstrumentation().context.assets.open("experimental-png/$name").use { it.readBytes() }

    @Test fun realV2ActivityHttpComparisonAndRecreationKeepTheValidatedResult() {
        val context=compose.activity
        val file=File(context.cacheDir,"completion-public-synthetic.png").apply { writeBytes(asset("RGB-pillow.png")) }
        val posts=AtomicInteger()
        MockWebServer().use { server ->
            server.dispatcher=object: Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    if(request.path=="/ready")return MockResponse().setHeader("Content-Type","application/json").setBody(
                        Json.encodeToString(ExperimentalServerReadiness("ready","photo-experimental-v2","experimental",listOf("native_v12"),false)))
                    if(request.path!="/v2/photo/protect")return MockResponse().setResponseCode(404)
                    posts.incrementAndGet()
                    val text=request.body.readUtf8()
                    val id=Regex("name=\"request_id\"[\\s\\S]*?\\r\\n\\r\\n([^\\r\\n]+)").find(text)!!.groupValues[1]
                    val source=model.state.value.source!!
                    val dto=Json.decodeFromString<ExperimentalPhotoResponse>(asset("response-pillow.json").toString(Charsets.UTF_8))
                        .copy(requestId=id,sourceSha256=source.sourceSha256)
                    return MockResponse().setHeader("Content-Type","application/json").setBody(Json.encodeToString(dto))
                }
            }
            server.start()
            val endpoint=server.url("/").toString()
            try {
                compose.runOnUiThread {
                    model.cancel();model.setEngine(ExperimentalPhotoEngine.NATIVE)
                    model.setAddress(endpoint);model.select(context,Uri.fromFile(file))
                }
                compose.waitUntil(15000) { model.state.value.source!=null && !model.state.value.hasActiveWork }
                compose.onNodeWithText("서버 및 처리 설정").performScrollTo().performClick()
                compose.onNodeWithText("서버 연결 확인 · 사진 전송 없음").performScrollTo().performClick()
                compose.waitUntil(10000) { model.state.value.readiness!=null }
                assertEquals(0,posts.get())
                compose.onNodeWithText("선택한 AI 실험 실행").performScrollTo().performClick()
                compose.waitUntil(20000) { model.state.value.result!=null && !model.state.value.busy }
                compose.captureDesignArtifact("automatic-comparison")
                val result=model.state.value.result!!
                assertEquals(1L,result.changedPixels);assertTrue(model.state.value.hasUnsavedResult)
                compose.onNodeWithText("나란히 비교").performScrollTo().assertIsDisplayed()
                compose.waitUntil(10000) { compose.onAllNodesWithContentDescription("AI 비교 원본").fetchSemanticsNodes().isNotEmpty() }
                compose.onNodeWithContentDescription("AI 비교 원본").assertExists()
                compose.onNodeWithContentDescription("AI 비교 처리본").assertExists()
                compose.onNodeWithText("한 장씩").performScrollTo().performClick()
                compose.onNodeWithText("원본 보기").performScrollTo().performClick()
                compose.onNodeWithContentDescription("AI 비교 원본").assertExists()
                compose.activityRule.scenario.recreate()
                assertEquals(endpoint,model.state.value.serverAddress)
                assertEquals(result.requestId,model.state.value.result!!.requestId)
                assertTrue(model.state.value.hasUnsavedResult);assertEquals(1,posts.get())
                compose.onNodeWithText("실험 PNG 처리본 공유").performScrollTo().performClick()
                compose.onNodeWithText("실험 처리본을 공유할까요?").assertIsDisplayed()
                compose.onNodeWithText("취소",useUnmergedTree=true).performClick()
                assertTrue(model.state.value.hasUnsavedResult)
            } finally { compose.runOnUiThread { model.discardSession() };file.delete() }
        }
    }
    @Suppress("DEPRECATION")
    @Test fun pickerAndCameraDoNotRequestBroadImageLibraryAccess() {
        val permissions=compose.activity.packageManager.getPackageInfo(compose.activity.packageName,PackageManager.GET_PERMISSIONS).requestedPermissions.orEmpty()
        assertFalse(permissions.contains("android.permission.READ_MEDIA_IMAGES"))
        assertFalse(permissions.contains("android.permission.READ_EXTERNAL_STORAGE"))
        compose.onNodeWithText("카메라로 촬영").performScrollTo().assertIsDisplayed()
    }
    @Test fun deliveredCameraUriNormalizesExifAndRemovesOnlyItsTemporaryOutput() {
        val context=compose.activity
        val uri=CameraCaptureFiles.create(context)
        val output=CameraCaptureFiles.ownedFile(context,uri)!!
        try {
            val bitmap=Bitmap.createBitmap(8,6,Bitmap.Config.ARGB_8888).apply { eraseColor(Color.CYAN) }
            context.contentResolver.openOutputStream(uri)!!.use { assertTrue(bitmap.compress(Bitmap.CompressFormat.JPEG,95,it)) }
            bitmap.recycle()
            ExifInterface(output.path).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_ROTATE_90.toString());saveAttributes()
            }
            compose.runOnUiThread { model.select(context,uri) }
            compose.waitUntil(15000) { model.state.value.source!=null && !model.state.value.hasActiveWork }
            assertEquals(6,model.state.value.source!!.width);assertEquals(8,model.state.value.source!!.height)
            compose.waitUntil(5000) { !output.exists() }
            assertNull(model.state.value.result)
        } finally { compose.runOnUiThread { model.discardSession() };CameraCaptureFiles.discard(context,uri) }
    }
}
