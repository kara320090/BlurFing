package com.blurfing.app.repository

import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse

/**
 * 보호 처리 및 연동 저장소 공통 인터페이스.
 * Mock 구현과 실제 HTTP API 구현을 교체할 수 있습니다.
 */
interface ProtectionRepository {
    /**
     * 정규화된 이미지와 요청 파라미터로 보호 처리를 수행합니다.
     */
    suspend fun protectImage(
        request: ProtectionRequest,
        imageBytes: ByteArray
    ): Result<ProtectionResponse>

    /**
     * 진행 중인 특정 request_id의 요청을 취소합니다.
     */
    fun cancelRequest(requestId: String)
}
