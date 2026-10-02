package com.blurfing.app

import com.blurfing.app.model.*
import com.blurfing.app.utils.ComparisonCrop
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class ComparisonPresentationTest {
    private val metrics = EvaluationMetrics(sampleId = "synthetic-sample", referenceId = "synthetic-ref",
        engine = "fixture-engine", engineVersion = "test", originalScore = 41.2, protectedScore = 12.3,
        isValidOriginal = true, measuredAt = "2026-09-28T13:00:00Z", isMock = false,
        requestId = "test-request", scoreUnit = "engine-score", conditions = "synthetic unit test only")
    private fun response(evaluation: EvaluationMetrics? = metrics) =
        ProtectionResponse("test-request", "succeeded", "real", evaluation = evaluation)

    @Test fun fullImageCropExactlyCoversPixels() {
        assertEquals(ComparisonCrop(0, 0, 120, 160), ComparisonCrop.calculate(120, 160, null, 1f))
    }
    @Test fun zoomAndEdgeRegionNeverEscapePixelBounds() {
        val region = NormalizedRegion(.95f, .95f, .05f, .05f)
        for (zoom in listOf(1f, 2f, 4f)) {
            val crop = ComparisonCrop.calculate(120, 160, region, zoom)
            assertTrue(crop.left >= 0 && crop.top >= 0 && crop.width > 0 && crop.height > 0)
            assertTrue(crop.left + crop.width <= 120 && crop.top + crop.height <= 160)
        }
        assertEquals(ComparisonCrop(0, 0, 1, 1), ComparisonCrop.calculate(1, 1, region, 4f))
    }
    @Test fun invalidZoomIsRejected() {
        for (zoom in listOf(0f, 5f, Float.NaN, Float.POSITIVE_INFINITY)) {
            assertTrue(runCatching { ComparisonCrop.calculate(10, 10, null, zoom) }.isFailure)
        }
    }
    @Test fun sameResponseReportIncludesRawScoresWithoutPercentageConversion() {
        val presentation = EvaluationPresentation.from(response())
        assertEquals(41.2, presentation.verifiedReport!!.originalScore!!, 0.0)
        assertEquals(12.3, presentation.verifiedReport!!.protectedScore!!, 0.0)
        assertTrue(presentation.message.contains("확률"))
    }
    @Test fun mockResultOrMockMetricsNeverShowScores() {
        assertNull(EvaluationPresentation.from(response().copy(resultKind = "mock")).verifiedReport)
        assertNull(EvaluationPresentation.from(response(metrics.copy(isMock = true))).verifiedReport)
    }
    @Test fun missingPartialOrMismatchedReportsRemainUnmeasured() {
        val invalid = listOf(null, metrics.copy(originalScore = null), metrics.copy(protectedScore = Double.NaN),
            metrics.copy(requestId = "old-request"), metrics.copy(engineVersion = null),
            metrics.copy(conditions = null), metrics.copy(isValidOriginal = null), metrics.copy(measuredAt = "invalid"))
        invalid.forEach { assertNull(EvaluationPresentation.from(response(it)).verifiedReport) }
    }
    @Test fun invalidOriginalShowsExclusionNoticeInsteadOfSuccess() {
        val presentation = EvaluationPresentation.from(response(metrics.copy(isValidOriginal = false)))
        assertNotNull(presentation.verifiedReport)
        assertTrue(presentation.message.contains("제외"))
    }
    @Test fun optionalWireReportRoundTripsAndOlderResponseStillWorks() {
        val encoded = Json.encodeToString(ProtectionResponse.serializer(), response())
        assertTrue(encoded.contains("original_score"))
        assertEquals(metrics, Json.decodeFromString<ProtectionResponse>(encoded).evaluation)
        val older = Json.decodeFromString<ProtectionResponse>("""{"request_id":"a","status":"succeeded","result_kind":"real"}""")
        assertNull(older.evaluation)
        assertNull(EvaluationPresentation.from(older).verifiedReport)
    }
}
