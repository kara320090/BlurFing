package com.blurfing.app.experimental

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import java.io.IOException

class ExperimentalPhotoException(message: String, cause: Throwable? = null) : IOException(message, cause)

const val EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT = "http://10.0.2.2:8001"

enum class ExperimentalPhotoEngine(val id: String, val method: String, val title: String) {
    NATIVE("native_v12", "photo_native_v12_experimental", "학습 모델 영역 (V12)"),
    DISTAL("distal_v13", "photo_distal_v13_geometry_experimental", "손끝 기하 영역 (V13)"),
    POSE("pose_v14", "photo_pose_v14_geometry_experimental", "한 손 자세 영역 (V14)"),
    SYNTHETIC("synthetic_v23", "photo_synthetic_v23_automatic_experimental", "자동 지문 합성 (V23 · 검증 중)");
    companion object {
        fun fromId(id: String): ExperimentalPhotoEngine =
            entries.singleOrNull { it.id == id } ?: throw IllegalArgumentException("지원하지 않는 AI 실험입니다.")
    }
}

@Serializable
data class ExperimentalPermissionMask(
    val encoding: String,
    @SerialName("image_base64") val imageBase64: String,
    @SerialName("png_sha256") val pngSha256: String,
    @SerialName("boolean_pixel_sha256") val booleanPixelSha256: String,
    val pixels: Long
)

@Serializable
data class ExperimentalRegionBounds(
    @SerialName("region_id") val regionId: Int,
    val status: String,
    @SerialName("reason_code") val reasonCode: String,
    @SerialName("mask_pixels") val maskPixels: Long,
    @SerialName("changed_RGB_pixels") val changedRgbPixels: Long,
    @SerialName("permission_boolean_sha256") val permissionBooleanSha256: String,
    val x: Double, val y: Double, val width: Double, val height: Double,
    @SerialName("bounds_are_not_filled_permission") val boundsAreNotFilledPermission: Boolean
)

fun ExperimentalRegionBounds.userExplanation(): String = when(reasonCode) {
    "TRANSFORMED" -> "지문 합성 적용"
    "TRANSFORMED_PRECAUTIONARY_SURFACE" -> "손끝 영역 합성 적용 · 원본 지문선은 확인되지 않음"
    "REJECT_BOUNDARY_UNCERTAIN" -> "손끝 경계를 확인하지 못했습니다. 손끝과 첫 관절이 모두 보이게 촬영해 주세요."
    "REJECT_VISIBILITY_UNCERTAIN" -> "지문선을 확인하기 어렵습니다. 반사를 줄이고 초점을 맞춰 촬영해 주세요."
    "REJECT_OBSERVATION_BUDGET" -> "분석 범위 제한에 도달했습니다. 손끝을 중심으로 다시 촬영해 주세요."
    "REJECT_RENDERER_UNRESOLVED" -> "합성 결과 검사를 통과하지 못해 원본을 유지했습니다."
    else -> "처리 조건을 충족하지 못해 원본을 유지했습니다."
}

@Serializable
data class ExperimentalPhotoResponse(
    @SerialName("contract_version") val contractVersion: String,
    @SerialName("request_id") val requestId: String,
    @SerialName("result_kind") val resultKind: String,
    val method: String,
    @SerialName("photo_engine") val photoEngine: String,
    val status: String,
    @SerialName("image_base64") val imageBase64: String,
    @SerialName("mime_type") val mimeType: String,
    @SerialName("image_width") val imageWidth: Int,
    @SerialName("image_height") val imageHeight: Int,
    @SerialName("source_exif_orientation") val sourceExifOrientation: Int,
    @SerialName("coordinate_system") val coordinateSystem: String,
    @SerialName("source_sha256") val sourceSha256: String,
    @SerialName("source_RGB_sha256") val sourceRgbSha256: String,
    @SerialName("returned_RGB_sha256") val returnedRgbSha256: String,
    @SerialName("candidate_components") val candidateComponents: Int,
    @SerialName("transformed_components") val transformedComponents: Int,
    @SerialName("rejected_components") val rejectedComponents: Int,
    @SerialName("changed_RGB_pixels") val changedRgbPixels: Long,
    @SerialName("accepted_permission_mask") val acceptedPermissionMask: ExperimentalPermissionMask,
    @SerialName("rejected_permission_mask") val rejectedPermissionMask: ExperimentalPermissionMask,
    @SerialName("region_display_bounds") val regionDisplayBounds: List<ExperimentalRegionBounds>,
    @SerialName("bounds_are_not_filled_permission") val boundsAreNotFilledPermission: Boolean,
    @SerialName("processing_ms") val processingMs: Long,
    val warnings: List<String>,
    @SerialName("privacy_validated") val privacyValidated: Boolean,
    @SerialName("production_approved") val productionApproved: Boolean,
    @SerialName("complete_photo_protection_verified") val completePhotoProtectionVerified: Boolean,
    @SerialName("independent_final_test") val independentFinalTest: Boolean,
    val evaluation: JsonElement?
)
