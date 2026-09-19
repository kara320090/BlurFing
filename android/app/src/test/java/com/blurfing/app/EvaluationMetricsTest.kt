package com.blurfing.app

import com.blurfing.app.model.EvaluationMetrics
import org.junit.Assert.*
import org.junit.Test

class EvaluationMetricsTest {

    @Test
    fun unmeasuredMetrics_holdNullScoresAndCannotBeFaked() {
        val metrics = EvaluationMetrics(
            sampleId = "synthetic-sample-001",
            engine = null,
            originalScore = null,
            protectedScore = null,
            isMock = true
        )

        assertFalse("미측정 평가 결과는 isMeasured가 false여야 합니다.", metrics.isMeasured)
        assertNull(metrics.originalScore)
        assertNull(metrics.protectedScore)
        assertTrue(metrics.isMock)
    }

    @Test
    fun measuredMetrics_requiresBothScores() {
        val partial = EvaluationMetrics(
            originalScore = 45.2,
            protectedScore = null
        )
        assertFalse(partial.isMeasured)

        val full = EvaluationMetrics(
            originalScore = 45.2,
            protectedScore = 12.0,
            isMock = false
        )
        assertTrue(full.isMeasured)
        assertEquals(45.2, full.originalScore!!, 0.001)
        assertEquals(12.0, full.protectedScore!!, 0.001)
    }
}
