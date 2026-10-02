package com.blurfing.app.model

import java.time.Instant

data class EvaluationPresentation(val message: String, val verifiedReport: EvaluationMetrics? = null) {
    companion object {
        fun from(response: ProtectionResponse?): EvaluationPresentation {
            if (response?.resultKind == "mock") return EvaluationPresentation("미측정 · Mock 프리뷰는 실제 지문 평가가 아닙니다.")
            val metrics = response?.evaluation ?: return EvaluationPresentation("미측정 · 평가 엔진의 측정 결과가 아직 없습니다.")
            if (metrics.isMock) return EvaluationPresentation("미측정 · 제공된 값은 Mock 평가 자료입니다.")
            val metadata = listOf(metrics.sampleId, metrics.referenceId, metrics.engine, metrics.engineVersion,
                metrics.scoreUnit, metrics.conditions, metrics.measuredAt)
            if (response.status != "succeeded" || response.resultKind != "real" || !metrics.isMeasured ||
                metrics.requestId != response.requestId || metrics.isValidOriginal == null ||
                metadata.any { it.isNullOrBlank() } || runCatching { Instant.parse(metrics.measuredAt) }.isFailure) {
                return EvaluationPresentation("미측정 · 현재 요청과 연결된 점수·엔진·측정 조건을 모두 확인할 수 없습니다.")
            }
            return EvaluationPresentation(
                if (metrics.isValidOriginal) "매칭 점수는 본인 일치 확률이나 보호 성공률이 아닙니다."
                else "원본 기준이 유효하지 않아 보호 성공 집계에서 제외합니다.", metrics)
        }
    }
}
