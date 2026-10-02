package com.blurfing.app.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * 지원하는 보호 방식 열거형.
 */
enum class ProtectionMethod(val apiValue: String, val displayName: String) {
    GAUSSIAN_BLUR("gaussian_blur", "가우시안 블러");

    companion object {
        fun fromApiValue(value: String): ProtectionMethod =
            entries.firstOrNull { it.apiValue == value } ?: GAUSSIAN_BLUR
    }
}

/**
 * 보호 처리 요청 모델 (contracts/protection-api.md 준수).
 */
data class ProtectionRequest(
    val requestId: String,
    val method: ProtectionMethod = ProtectionMethod.GAUSSIAN_BLUR,
    val strength: Float = 0.5f,
    val regions: List<NormalizedRegion>? = null
)

/**
 * 보호 처리 성공 응답 모델.
 */
@Serializable
data class ProtectionResponse(
    @SerialName("request_id")
    val requestId: String,
    @SerialName("status")
    val status: String,
    @SerialName("result_kind")
    val resultKind: String, // "mock" or "real"
    @SerialName("image_base64")
    val imageBase64: String? = null,
    @SerialName("mime_type")
    val mimeType: String = "image/png",
    @SerialName("applied_regions")
    val appliedRegions: List<NormalizedRegion> = emptyList(),
    @SerialName("processing_ms")
    val processingMs: Long? = null,
    @SerialName("warnings")
    val warnings: List<String> = emptyList(),
    @SerialName("evaluation")
    val evaluation: EvaluationMetrics? = null
)

/**
 * 연구용 평가 결과 모델.
 * 지문 매칭 점수를 본인 일치 확률(0~100%)로 임의 변환하지 않으며,
 * 미측정 상태는 null로 명확히 유지합니다.
 */
@Serializable
data class EvaluationMetrics(
    @SerialName("sample_id")
    val sampleId: String? = null,
    @SerialName("reference_id")
    val referenceId: String? = null,
    val engine: String? = null,
    @SerialName("original_score")
    val originalScore: Double? = null,
    @SerialName("protected_score")
    val protectedScore: Double? = null,
    @SerialName("is_valid_original")
    val isValidOriginal: Boolean? = null,
    @SerialName("measured_at")
    val measuredAt: String? = null,
    @SerialName("is_mock")
    val isMock: Boolean = true,
    @SerialName("request_id")
    val requestId: String? = null,
    @SerialName("engine_version")
    val engineVersion: String? = null,
    @SerialName("score_unit")
    val scoreUnit: String? = null,
    val conditions: String? = null
) {
    val isMeasured: Boolean
        get() = originalScore?.isFinite() == true && protectedScore?.isFinite() == true
}
