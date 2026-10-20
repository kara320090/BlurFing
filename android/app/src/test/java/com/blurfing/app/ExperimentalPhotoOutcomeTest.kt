package com.blurfing.app.model

import org.junit.Assert.*
import org.junit.Test

/** Generated metadata and mask counts only; no inference or real AI/security scores. */
class ExperimentalPhotoOutcomeTest {
    private val original = ExperimentalPhotoMetadata(
        "photo-experimental-v2", "experimental", "synthetic", "a".repeat(64), "native_v12",
        "encoded_original_pixels", 1, 16, 12, "partial_success", 2, 1, 1, 1,
        false, false, false, false
    )

    private fun show(
        data: ExperimentalPhotoMetadata = original,
        expectedEngine: String = "native_v12",
        accepted: Long = 24,
        rejected: Long = 8,
        changed: Long = 1,
        outside: Long = 0
    ) = ExperimentalPhotoOutcome.validateAndPresent(data, "synthetic", "a".repeat(64), expectedEngine,
        16, 12, accepted, rejected, changed, outside)

    private fun rejects(action: () -> Unit) {
        try { action(); fail("Invalid experimental payload was accepted") } catch (_: IllegalArgumentException) { }
    }

    @Test fun partialKeepsExposureWarningAndDoesNotClaimProtection() {
        val result = show()
        assertTrue(result.title.contains("일부")); assertTrue(result.detail.contains("원본 지문이 남아"))
        assertTrue(result.canSaveChangedCopy); assertFalse(result.originalReturned); assertFalse(result.mayClaimCompleteProtection)
    }

    @Test fun rejectedIsAnExplicitOriginalResultWithNoProtectedSaveClaim() {
        val data = original.copy(status = "rejected", transformedComponents = 0, rejectedComponents = 2, changedRgbPixels = 0)
        val result = show(data, accepted = 0, rejected = 32, changed = 0)
        assertTrue(result.originalReturned); assertFalse(result.canSaveChangedCopy); assertTrue(result.title.contains("미적용"))
    }

    @Test fun allCandidatesTransformedStillDoesNotMeanFullPhotoProtected() {
        val result = show(original.copy(status = "success", transformedComponents = 2, rejectedComponents = 0), accepted = 32, rejected = 0)
        assertFalse(result.mayClaimCompleteProtection); assertTrue(result.detail.contains("검증되지 않았"))
    }

    @Test fun geometryRequiresItsOwnExplicitEngineAndBoundaryWarning() {
        val result = show(original.copy(photoEngine = "distal_v13"), expectedEngine = "distal_v13")
        assertTrue(result.detail.contains("경계 검토")); assertTrue(result.detail.contains("회귀"))
        rejects { show(original.copy(photoEngine = "distal_v13")) }
    }

    @Test fun oldGaussianSucceededResponseCannotBeRelabeledAsV2() {
        rejects { show(original.copy(contractVersion = "v1", resultKind = "real", status = "succeeded")) }
    }

    @Test fun staleRequestSourceOrDimensionsAreRejected() {
        rejects { show(original.copy(requestId = "old")) }; rejects { show(original.copy(sourceSha256 = "b".repeat(64))) }
        rejects { show(original.copy(imageWidth = 12, imageHeight = 16)) }
    }

    @Test fun nonNormalizedExifAndCoordinateClaimsAreRejected() {
        rejects { show(original.copy(sourceExifOrientation = 6)) }
        rejects { show(original.copy(coordinateSystem = "upright")) }
    }

    @Test fun changedPixelsOutsideDecodedAcceptedMaskCannotPass() {
        rejects { show(outside = 1) }; rejects { show(changed = 25) }
        rejects { show(original.copy(changedRgbPixels = 2)) }
        rejects { show(accepted = Long.MAX_VALUE, rejected = Long.MAX_VALUE) }
    }

    @Test fun falseCountsStatusAndProductionClaimsAreRejected() {
        rejects { show(original.copy(candidateComponents = 3)) }; rejects { show(original.copy(status = "success")) }
        rejects { show(original.copy(privacyValidated = true)) }; rejects { show(original.copy(productionApproved = true)) }
        rejects { show(original.copy(independentFinalTest = true)) }
    }

    @Test fun surfaceNoticeRequiresConsistentCountsAndSyntheticEngine() {
        val valid=original.copy(photoEngine="synthetic_v23",precautionaryComponents=1)
        val result=show(valid,expectedEngine="synthetic_v23")
        assertTrue(result.detail.contains("1개 영역은 원본 지문선 확인 없이"))
        assertFalse(result.mayClaimCompleteProtection)
        rejects { show(valid.copy(precautionaryComponents=2),expectedEngine="synthetic_v23") }
        rejects { show(original.copy(precautionaryComponents=1)) }
    }
}
