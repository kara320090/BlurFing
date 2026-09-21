package com.blurfing.app.repository

import java.util.Base64
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import java.util.concurrent.ConcurrentHashMap

/**
 * 개발 및 UI 테스트용 Mock 저장소 구현체.
 * 실제 AI/지문 점수를 날조하지 않고 명확히 result_kind = "mock" 및 MOCK_RESULT 경고를 반환합니다.
 */
class MockProtectionRepository(
    private val simulatedDelayMs: Long = 600L
) : ProtectionRepository {

    private val cancelledRequestIds = ConcurrentHashMap.newKeySet<String>()

    override suspend fun protectImage(
        request: ProtectionRequest,
        imageBytes: ByteArray
    ): Result<ProtectionResponse> {
        if (cancelledRequestIds.contains(request.requestId)) {
            return Result.failure(CancellationException("요청이 취소되었습니다: ${request.requestId}"))
        }

        // 지연 시간 시뮬레이션
        if (simulatedDelayMs > 0) {
            delay(simulatedDelayMs)
        }

        if (cancelledRequestIds.contains(request.requestId)) {
            return Result.failure(CancellationException("요청 처리 중 취소되었습니다: ${request.requestId}"))
        }

        // 영역이 지정되지 않은 경우 개발용 합성 영역 제공 (검지, 중지 위치 가정)
        val regions = request.regions ?: listOf(
            NormalizedRegion(x = 0.35f, y = 0.30f, width = 0.12f, height = 0.16f),
            NormalizedRegion(x = 0.52f, y = 0.28f, width = 0.12f, height = 0.16f)
        )

        // Mock 응답에서는 원본 바이트를 Base64로 반환하되, 실제 픽셀 블러 처리는 LocalBlurProcessor 또는 실제 서버에서 수행됨
        val base64Image = Base64.getEncoder().encodeToString(imageBytes)

        val response = ProtectionResponse(
            requestId = request.requestId,
            status = "succeeded",
            resultKind = "mock",
            imageBase64 = base64Image,
            mimeType = "image/png",
            appliedRegions = regions,
            processingMs = simulatedDelayMs,
            warnings = listOf(
                "MOCK_RESULT",
                "DEVELOPMENT_ONLY",
                "AI_AND_SENSOR_UNMEASURED"
            )
        )

        return Result.success(response)
    }

    override fun cancelRequest(requestId: String) {
        cancelledRequestIds.add(requestId)
    }
}
