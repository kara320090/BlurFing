package com.blurfing.app.utils

import android.content.Context
import android.net.Uri
import com.blurfing.app.BuildConfig
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import java.time.Instant

/** Explicit allowlist: no source, image bytes, server address, identifiers, or evaluation data. */
object DiagnosticsReport {
    private val json = Json { prettyPrint = true }

    fun create(state: UiState.Ready, settings: ProcessingSettings): String? {
        if (state.step != ScreenStep.COMPARISON || state.isProcessing) return null
        val response = state.protectionResponse ?: return null
        val run = state.processingRun ?: return null
        if (response.status != "succeeded" || response.resultKind !in setOf("mock", "real")) return null
        val report = buildJsonObject {
            put("schema_version", 1)
            put("app_version", BuildConfig.VERSION_NAME)
            put("exported_at_utc", Instant.now().toString())
            put("result_kind", response.resultKind)
            put("status", "succeeded")
            put("image_width", state.originalBitmap.width)
            put("image_height", state.originalBitmap.height)
            put("selected_region_count", state.regions.size)
            put("applied_region_count", response.appliedRegions.size)
            put("method", run.method.apiValue)
            put("strength", run.strength)
            put("server_used", run.useServer)
            put("selected_export_format", settings.exportFormat.name)
            if (settings.exportFormat.name == "JPEG") put("selected_jpeg_quality", settings.jpegQuality)
            response.processingMs?.takeIf { it >= 0 }?.let {
                put(if (response.resultKind == "mock") "mock_reported_delay_ms" else "server_reported_processing_ms", it)
            }
            state.processingTiming?.let {
                putJsonObject("app_elapsed_ms") {
                    put("encode", it.encodeMs); put("request_wait", it.requestMs)
                    put("decode", it.decodeMs); put("total", it.totalMs)
                }
            }
            put("scope", "App integration diagnostics only; fingerprint protection and sensor performance are not measured here.")
        }
        return json.encodeToString(JsonObject.serializer(), report)
    }

    suspend fun write(context: Context, uri: Uri, report: String) = withContext(Dispatchers.IO) {
        require(uri.scheme == "content")
        val bytes = report.toByteArray(Charsets.UTF_8)
        require(bytes.size <= 16 * 1024)
        checkNotNull(context.contentResolver.openOutputStream(uri, "w")).use { it.write(bytes) }
    }
}
