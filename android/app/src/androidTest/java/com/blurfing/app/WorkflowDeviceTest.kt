package com.blurfing.app

import android.content.ContentUris
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import com.blurfing.app.utils.CameraCaptureFiles
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.CameraCaptureViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Real Android UI/MediaStore tests with synthetic pixels; no biometric inputs or AI claims. */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 29)
class WorkflowDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val vm get() = ViewModelProvider(compose.activity)[BlurFingViewModel::class.java]

    private fun image(file: File) {
        val bitmap = Bitmap.createBitmap(120, 160, Bitmap.Config.ARGB_8888)
        for (y in 0 until bitmap.height) for (x in 0 until bitmap.width) {
            bitmap.setPixel(x, y, if ((x / 4 + y / 4) % 2 == 0) Color.BLUE else Color.YELLOW)
        }
        file.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
        bitmap.recycle()
    }

    private fun ready(step: ScreenStep) {
        compose.waitUntil(15_000) { (vm.uiState.value as? UiState.Ready)?.step == step }
        compose.waitForIdle()
    }

    private fun outputIds(): Set<Long> {
        val resolver = compose.activity.contentResolver
        return resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            arrayOf(MediaStore.Images.Media._ID),
            "${MediaStore.Images.Media.RELATIVE_PATH} = ?", arrayOf("Pictures/BlurFing/"), null)!!.use {
            buildSet { while (it.moveToNext()) add(it.getLong(0)) }
        }
    }

    @Test fun selectedImageThroughEditorPreviewComparisonAndRealGallerySave() {
        val source = File(compose.activity.cacheDir, "workflow-synthetic.png").also(::image)
        val original = source.readBytes()
        val before = outputIds()
        try {
            // The picker result boundary is injected. System chooser gestures are a separate manual check.
            compose.runOnUiThread { vm.onImageSelected(Uri.fromFile(source), compose.activity) }
            ready(ScreenStep.REGION_EDITOR)
            compose.onNodeWithText("영역 추가").performClick()
            compose.onNodeWithText("영역 추가").performClick()
            compose.runOnIdle { assertEquals(2, (vm.uiState.value as UiState.Ready).regions.size) }
            compose.onNodeWithText("선택 삭제").performClick()
            compose.onNodeWithText("보호 설정 (BF-04)").performClick()
            compose.onNodeWithText("Mock 프리뷰 만들기").performScrollTo().performClick()
            ready(ScreenStep.COMPARISON)
            compose.onNodeWithText("원본 보기").performClick()
            compose.onNodeWithContentDescription("원본 이미지").assertIsDisplayed()
            compose.onNodeWithText("보호본 보기").performClick()
            compose.onNodeWithText("보호 사본 저장 (원본 보존)").performScrollTo().performClick()
            compose.waitUntil(15_000) { (vm.uiState.value as? UiState.Ready)?.saveMessage != null }
            val created = outputIds() - before
            assertEquals(1, created.size)
            val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, created.single())
            compose.activity.contentResolver.openInputStream(uri).use {
                val saved = BitmapFactory.decodeStream(it)!!
                assertEquals(120, saved.width)
                assertEquals(160, saved.height)
                saved.recycle()
            }
            assertArrayEquals(original, source.readBytes())
        } finally {
            (outputIds() - before).forEach {
                compose.activity.contentResolver.delete(
                    ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, it), null, null)
            }
            compose.runOnUiThread { vm.resetToIdle() }
            source.delete()
        }
    }

    @Test fun realFileProviderCameraOutputImportsAndCleansUp() {
        val camera = ViewModelProvider(compose.activity)[CameraCaptureViewModel::class.java]
        lateinit var output: Uri
        compose.runOnUiThread { output = camera.beginCapture()!! }
        assertEquals("content", output.scheme)
        val bitmap = Bitmap.createBitmap(120, 160, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.CYAN) }
        compose.activity.contentResolver.openOutputStream(output).use {
            assertTrue(bitmap.compress(Bitmap.CompressFormat.JPEG, 95, it!!))
        }
        bitmap.recycle()
        compose.runOnUiThread {
            vm.onCameraImageCaptured(camera.completeCapture(true)!!, compose.activity)
        }
        ready(ScreenStep.REGION_EDITOR)
        compose.waitUntil(5_000) { !CameraCaptureFiles.hasOutput(compose.activity, output) }
        compose.onNodeWithContentDescription("손끝 영역 편집 이미지").assertIsDisplayed()
        compose.runOnUiThread { vm.resetToIdle() }
    }

    @Test fun brokenImageShowsRecoveryActions() {
        val file = File(compose.activity.cacheDir, "workflow-broken.png").apply { writeText("not an image") }
        try {
            compose.runOnUiThread { vm.onImageSelected(Uri.fromFile(file), compose.activity) }
            compose.waitUntil(5_000) { vm.uiState.value is UiState.Error }
            compose.onNodeWithText("갤러리에서 다시 선택").assertIsDisplayed().assertIsEnabled()
            compose.onNodeWithText("카메라로 다시 촬영").assertIsDisplayed().assertIsEnabled()
        } finally {
            compose.runOnUiThread { vm.resetToIdle() }
            file.delete()
        }
    }
}
