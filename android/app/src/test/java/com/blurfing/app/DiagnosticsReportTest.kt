package com.blurfing.app

import android.graphics.Bitmap
import android.net.Uri
import com.blurfing.app.model.*
import com.blurfing.app.utils.DiagnosticsReport
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DiagnosticsReportTest {
    private val secret = "PRIVATE_PHOTO_AND_IDENTIFIERS"
    private fun state(bitmap: Bitmap) = UiState.Ready(ScreenStep.COMPARISON,
        Uri.parse("content://private/$secret"), bitmap, listOf(NormalizedRegion(.1f, .1f, .2f, .2f)),
        protectedBitmap = bitmap,
        protectionResponse = ProtectionResponse(secret, "succeeded", "mock", imageBase64 = secret,
            mimeType = secret, warnings = listOf(secret), processingMs = 600,
            evaluation = EvaluationMetrics(sampleId = secret, referenceId = secret, engine = secret,
                originalScore = 99.123456, protectedScore = 11.123456, conditions = secret)),
        processingRun = ProcessingRunInfo(ProtectionMethod.GAUSSIAN_BLUR, .5f, false),
        processingTiming = ProcessingTiming(10, 600, 5, 615))

    @Test fun allowlistExcludesAllPhotoPathsAddressesScoresAndIdentifiers() {
        val bitmap = Bitmap.createBitmap(8, 12, Bitmap.Config.ARGB_8888)
        try {
            val report = DiagnosticsReport.create(state(bitmap), ProcessingSettings(serverAddress = "https://$secret"))!!
            assertFalse(report.contains(secret))
            assertFalse(report.contains("99.123456"))
            assertFalse(report.contains("11.123456"))
            val root = Json.parseToJsonElement(report).jsonObject
            assertEquals("mock", root["result_kind"]!!.jsonPrimitive.content)
            assertEquals(8, root["image_width"]!!.jsonPrimitive.int)
            assertEquals(12, root["image_height"]!!.jsonPrimitive.int)
            assertEquals(615, root["app_elapsed_ms"]!!.jsonObject["total"]!!.jsonPrimitive.int)
            assertTrue(root.containsKey("mock_reported_delay_ms"))
            assertFalse(root.containsKey("server_reported_processing_ms"))
            assertTrue(report.length < 16 * 1024)
        } finally { bitmap.recycle() }
    }

    @Test fun incompleteOrEditorStateDoesNotExportOldReport() {
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888)
        try {
            val ready = state(bitmap)
            assertNull(DiagnosticsReport.create(ready.copy(step = ScreenStep.REGION_EDITOR), ProcessingSettings()))
            assertNull(DiagnosticsReport.create(ready.copy(processingRun = null), ProcessingSettings()))
            assertNull(DiagnosticsReport.create(ready.copy(isProcessing = true), ProcessingSettings()))
        } finally { bitmap.recycle() }
    }

    @Test fun exportRejectsFilePathsAndOversizedRecordsBeforeOpeningProvider() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        try { DiagnosticsReport.write(context, Uri.parse("file:///private/source"), "{}"); fail("File scheme forbidden") }
        catch (_: IllegalArgumentException) {}
        try { DiagnosticsReport.write(context, Uri.parse("content://test/output"), "x".repeat(17 * 1024)); fail("Oversized record forbidden") }
        catch (_: IllegalArgumentException) {}
    }
}
