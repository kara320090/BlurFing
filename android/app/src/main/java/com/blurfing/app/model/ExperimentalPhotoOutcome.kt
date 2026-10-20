package com.blurfing.app.model

/** Private pure-Kotlin proposal. A separate v2 decoder must verify PNG/masks/RGB first. */
data class ExperimentalPhotoMetadata(
    val contractVersion: String,
    val resultKind: String,
    val requestId: String,
    val sourceSha256: String,
    val photoEngine: String,
    val coordinateSystem: String,
    val sourceExifOrientation: Int,
    val imageWidth: Int,
    val imageHeight: Int,
    val status: String,
    val candidateComponents: Int,
    val transformedComponents: Int,
    val rejectedComponents: Int,
    val changedRgbPixels: Long,
    val privacyValidated: Boolean,
    val productionApproved: Boolean,
    val completePhotoProtectionVerified: Boolean,
    val independentFinalTest: Boolean
)

data class ExperimentalPhotoPresentation(
    val title: String,
    val detail: String,
    val canSaveChangedCopy: Boolean,
    val originalReturned: Boolean,
    val mayClaimCompleteProtection: Boolean = false
)

object ExperimentalPhotoOutcome {
    /**
     * accepted/rejected pixel counts and changed pixels outside permission come
     * from the decoded masks and actual source/returned bitmaps, not JSON flags.
     * This helper never accepts the old gaussian_blur/succeeded payload as v2.
     */
    fun validateAndPresent(
        metadata: ExperimentalPhotoMetadata,
        expectedRequestId: String,
        expectedSourceSha256: String,
        expectedEngine: String,
        originalWidth: Int,
        originalHeight: Int,
        decodedAcceptedPixels: Long,
        decodedRejectedPixels: Long,
        actualChangedPixels: Long,
        actualChangedOutsideAcceptedPixels: Long
    ): ExperimentalPhotoPresentation {
        require(metadata.contractVersion == "photo-experimental-v2" && metadata.resultKind == "experimental")
        require(expectedEngine in setOf("native_v12", "distal_v13", "pose_v14", "synthetic_v23") && metadata.photoEngine == expectedEngine)
        require(metadata.requestId == expectedRequestId && metadata.sourceSha256 == expectedSourceSha256)
        require(expectedSourceSha256.matches(Regex("[0-9a-f]{64}")))
        require(metadata.coordinateSystem == "encoded_original_pixels" && metadata.sourceExifOrientation == 1)
        require(metadata.imageWidth == originalWidth && metadata.imageHeight == originalHeight)
        val raster = originalWidth.toLong() * originalHeight.toLong()
        require(originalWidth > 0 && originalHeight > 0 && raster <= 20_000_000L)
        require(metadata.candidateComponents in 0..256 && metadata.transformedComponents in 0..256 && metadata.rejectedComponents in 0..256)
        require(metadata.transformedComponents + metadata.rejectedComponents == metadata.candidateComponents)
        require(decodedAcceptedPixels in 0..raster && decodedRejectedPixels in 0..raster && decodedAcceptedPixels + decodedRejectedPixels <= raster)
        require(actualChangedPixels in 0..decodedAcceptedPixels && actualChangedOutsideAcceptedPixels == 0L)
        require(metadata.changedRgbPixels == actualChangedPixels)
        require(!metadata.privacyValidated && !metadata.productionApproved && !metadata.completePhotoProtectionVerified && !metadata.independentFinalTest)
        val expectedStatus = when {
            metadata.transformedComponents == 0 -> "rejected"
            metadata.rejectedComponents == 0 -> "success"
            else -> "partial_success"
        }
        require(metadata.status == expectedStatus)
        require((metadata.transformedComponents == 0) == (decodedAcceptedPixels == 0L))
        require((metadata.rejectedComponents == 0) == (decodedRejectedPixels == 0L))
        require((metadata.transformedComponents == 0) == (actualChangedPixels == 0L))
        val notice = "실험 결과이며 전체 지문 보호 효과는 검증되지 않았습니다. 후보 수는 손가락 개수가 아닙니다."
        if(metadata.candidateComponents==0) return ExperimentalPhotoPresentation(
            "보호 미적용 · 손끝 후보 확인 필요",
            "자동 처리할 손끝 후보를 확인하지 못했습니다. 지문이 없다는 뜻은 아닙니다. 손바닥 쪽 손끝이 선명하게 보이는 사진으로 다시 시도해 주세요.",
            false,true)
        val geometry = if (expectedEngine == "distal_v13") " 경계 검토가 필요하며 기존 정답 자료에서 검출 정확도 회귀가 관측됐습니다." else if (expectedEngine == "pose_v14") " 손 자세 기반 경계는 검토가 필요하며 전체 보호를 보장하지 않습니다." else if (expectedEngine == "synthetic_v23") " 자동 가시성 판정은 검증 중이며, 불확실한 영역은 원본으로 남습니다." else ""
        return when (metadata.status) {
            "success" -> ExperimentalPhotoPresentation("검출 후보 변환 완료", notice + geometry, true, false)
            "partial_success" -> ExperimentalPhotoPresentation("일부 후보만 변환됨", "거절된 ${metadata.rejectedComponents}개 후보는 원본 지문이 남아 있습니다. " + notice + geometry, true, false)
            else -> ExperimentalPhotoPresentation("보호 미적용 · 원본 반환", notice + geometry, false, true)
        }
    }
}
