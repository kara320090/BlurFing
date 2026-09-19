package com.blurfing.app

import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionMethod
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.repository.ApiProtectionRepository
import com.blurfing.app.repository.MockProtectionRepository
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.util.UUID

class ProtectionRepositoryTest {

    @Test
    fun mockProtectionRepository_returnsSucceededMockResult() = runBlocking {
        val repo = MockProtectionRepository(simulatedDelayMs = 10L)
        val request = ProtectionRequest(
            requestId = UUID.randomUUID().toString(),
            method = ProtectionMethod.GAUSSIAN_BLUR,
            strength = 0.5f,
            regions = listOf(NormalizedRegion(0.2f, 0.2f, 0.1f, 0.1f))
        )
        val dummyBytes = ByteArray(100) { 1 }

        val result = repo.protectImage(request, dummyBytes)

        assertTrue(result.isSuccess)
        val response = result.getOrThrow()
        assertEquals(request.requestId, response.requestId)
        assertEquals("succeeded", response.status)
        assertEquals("mock", response.resultKind)
        assertTrue(response.warnings.contains("MOCK_RESULT"))
        assertTrue(response.warnings.contains("AI_AND_SENSOR_UNMEASURED"))
        assertEquals(1, response.appliedRegions.size)
    }

    @Test
    fun mockProtectionRepository_cancellation_failsWithCancellation() = runBlocking {
        val repo = MockProtectionRepository(simulatedDelayMs = 50L)
        val requestId = "req-cancel-test-001"
        val request = ProtectionRequest(
            requestId = requestId,
            method = ProtectionMethod.GAUSSIAN_BLUR,
            strength = 0.5f
        )

        // 사전 취소
        repo.cancelRequest(requestId)
        val result = repo.protectImage(request, ByteArray(10))

        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull() is kotlinx.coroutines.CancellationException)
    }

    @Test
    fun apiProtectionRepository_fileExceedingLimit_failsBeforeNetwork() = runBlocking {
        val repo = ApiProtectionRepository(
            baseUrl = "http://localhost:8000",
            maxImageSizeBytes = 1000L // 1KB 제한 테스트
        )
        val request = ProtectionRequest(
            requestId = "req-large-file",
            method = ProtectionMethod.GAUSSIAN_BLUR,
            strength = 0.5f
        )
        val largeBytes = ByteArray(2000) // 2KB

        val result = repo.protectImage(request, largeBytes)

        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull() is IllegalArgumentException)
        assertTrue(result.exceptionOrNull()?.message?.contains("이미지 용량이 너무 큽니다") == true)
    }

    @Test
    fun apiProtectionRepository_preCancelled_failsImmediately() = runBlocking {
        val repo = ApiProtectionRepository(baseUrl = "http://localhost:8000")
        val requestId = "req-api-cancel-001"
        val request = ProtectionRequest(requestId = requestId)

        repo.cancelRequest(requestId)
        val result = repo.protectImage(request, ByteArray(100))

        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull() is kotlinx.coroutines.CancellationException)
    }
}
