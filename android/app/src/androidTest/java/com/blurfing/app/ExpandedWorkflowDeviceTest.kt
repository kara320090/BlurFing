package com.blurfing.app

import android.content.ContentUris
import android.content.ContentValues
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.provider.MediaStore
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.SdkSuppress
import com.blurfing.app.model.ExportFormat
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.utils.DiagnosticsReport
import com.blurfing.app.utils.ProtectedShareFiles
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Synthetic Android UI/provider checks. Does not test AI or sensor performance. */
@RunWith(AndroidJUnit4::class)
@SdkSuppress(minSdkVersion = 29)
class ExpandedWorkflowDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val vm get() = ViewModelProvider(compose.activity)[BlurFingViewModel::class.java]
    @Before fun reset() { compose.runOnUiThread { vm.resetToIdle(); vm.updateSettings(ProcessingSettings()) } }

    private fun load(): File {
        val file = File(compose.activity.cacheDir, "expanded-synthetic.png")
        val bitmap = Bitmap.createBitmap(120, 160, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.CYAN) }
        file.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
        bitmap.recycle()
        compose.runOnUiThread { vm.onImageSelected(Uri.fromFile(file), compose.activity) }
        ready(ScreenStep.REGION_EDITOR)
        return file
    }
    private fun ready(step: ScreenStep) {
        compose.waitUntil(15_000) { (vm.uiState.value as? UiState.Ready)?.step == step }
        compose.waitForIdle()
    }
    private fun preview() {
        compose.onNodeWithText("영역 추가").performClick()
        compose.onNodeWithText("보호 설정 (BF-04)").performClick()
        compose.onNodeWithText("Mock 프리뷰 만들기").performScrollTo().performClick()
        ready(ScreenStep.COMPARISON)
    }
    private fun outputIds(): Set<Long> = compose.activity.contentResolver.query(
        MediaStore.Images.Media.EXTERNAL_CONTENT_URI, arrayOf(MediaStore.Images.Media._ID),
        "${MediaStore.Images.Media.RELATIVE_PATH} = ?", arrayOf("Pictures/BlurFing/"), null)!!.use {
        buildSet { while (it.moveToNext()) add(it.getLong(0)) }
    }

    @Test fun manualEditorUndoRedoAndResizeRemainUsable() {
        val source = load()
        try {
            compose.onNodeWithText("보호 설정 (BF-04)").assertIsNotEnabled()
            compose.onNodeWithText("영역 추가").performClick()
            compose.onNodeWithText("실행 취소").performClick()
            compose.onNodeWithText("보호 설정 (BF-04)").assertIsNotEnabled()
            compose.onNodeWithText("다시 실행").performClick()
            compose.onNodeWithContentDescription("선택 영역 너비").performSemanticsAction(SemanticsActions.SetProgress) { it(.35f) }
            compose.runOnIdle { assertEquals(.35f, (vm.uiState.value as UiState.Ready).regions.single().width, .001f) }
            compose.onNodeWithText("실행 취소").performClick()
            compose.runOnIdle { assertEquals(.15f, (vm.uiState.value as UiState.Ready).regions.single().width, .001f) }
            compose.onNodeWithText("영역 모두 지우기").performClick()
            compose.onNodeWithText("보호 설정 (BF-04)").assertIsNotEnabled()
        } finally { compose.runOnUiThread { vm.resetToIdle() }; source.delete() }
    }

    @Test fun jpegSavePreservesSourceAndReportsCorrectMime() {
        val source = load()
        val original = source.readBytes()
        val before = outputIds()
        try {
            preview()
            compose.onNodeWithText("JPEG (용량 절약)").performScrollTo().performClick()
            compose.onNodeWithText("보호 사본 저장 (원본 보존)").performScrollTo().performClick()
            compose.waitUntil(15_000) { (vm.uiState.value as? UiState.Ready)?.saveMessage != null }
            val added = outputIds() - before
            assertEquals(1, added.size)
            val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, added.single())
            assertEquals("image/jpeg", compose.activity.contentResolver.getType(uri))
            val bytes = compose.activity.contentResolver.openInputStream(uri)!!.use { it.readBytes() }
            assertEquals(0xff, bytes[0].toInt() and 0xff)
            assertEquals(0xd8, bytes[1].toInt() and 0xff)
            assertArrayEquals(original, source.readBytes())
            assertNotNull((vm.uiState.value as UiState.Ready).processingTiming)
        } finally {
            (outputIds() - before).forEach { compose.activity.contentResolver.delete(
                ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, it), null, null) }
            compose.runOnUiThread { vm.resetToIdle() }; source.delete()
        }
    }

    @Test fun actualShareProviderIsNarrowAndDiagnosticJsonWritesToChosenUri() = runBlocking {
        val source = load()
        var shareUri: Uri? = null
        var diagnosticUri: Uri? = null
        try {
            preview()
            val state = vm.uiState.value as UiState.Ready
            val share = ProtectedShareFiles.prepare(compose.activity, state.protectedBitmap!!,
                ProcessingSettings(exportFormat = ExportFormat.PNG), true)
            shareUri = share.uri
            assertEquals("com.blurfing.app.protected-share", share.uri.authority)
            assertEquals("image/png", compose.activity.contentResolver.getType(share.uri))
            assertTrue(compose.activity.contentResolver.openInputStream(share.uri)!!.use { it.readBytes().size } > 8)
            try {
                FileProvider.getUriForFile(compose.activity, "com.blurfing.app.protected-share", source)
                fail("Source cache path must not be exposed by the sharing provider")
            } catch (_: IllegalArgumentException) {}
            val report = DiagnosticsReport.create(state, vm.settings.value)!!
            val uri = compose.activity.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, "BlurFing-synthetic-diagnostics.json")
                    put(MediaStore.Downloads.MIME_TYPE, "application/json")
                    put(MediaStore.Downloads.RELATIVE_PATH, "Download/BlurFing/")
                })!!
            diagnosticUri = uri
            DiagnosticsReport.write(compose.activity, uri, report)
            val saved = compose.activity.contentResolver.openInputStream(uri)!!.use { it.readBytes().toString(Charsets.UTF_8) }
            assertEquals(report, saved)
            assertEquals("mock", Json.parseToJsonElement(saved).jsonObject["result_kind"]!!.toString().trim('"'))
            assertFalse(saved.contains(source.name))
            assertFalse(saved.contains(state.protectionResponse!!.requestId))
        } finally {
            shareUri?.let { compose.activity.contentResolver.delete(it, null, null) }
            diagnosticUri?.let { compose.activity.contentResolver.delete(it, null, null) }
            compose.runOnUiThread { vm.resetToIdle() }; source.delete()
        }
    }
}
