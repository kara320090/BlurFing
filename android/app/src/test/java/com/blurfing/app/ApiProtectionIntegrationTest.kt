package com.blurfing.app

import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.repository.ApiProtectionRepository
import kotlinx.coroutines.*
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

/** 실제 HTTP 소켓 + 합성 응답. 팀의 보호 서버/AI 성능 검증과 구분한다. */
class ApiProtectionIntegrationTest {
    private lateinit var server: MockWebServer
    private lateinit var repo: ApiProtectionRepository
    private val request = ProtectionRequest("synthetic-001", regions = listOf(
        NormalizedRegion(0.2f, 0.3f, 0.1f, 0.1f)
    ))
    private fun body(id: String = request.requestId, status: String = "succeeded") =
        """{"request_id":"$id","status":"$status","result_kind":"real","image_base64":"AA==","mime_type":"image/png"}"""

    @Before fun startServer() {
        server = MockWebServer()
        server.start()
        repo = ApiProtectionRepository(baseUrl = server.url("/").toString())
    }
    @After fun stopServer() { server.shutdown() }

    @Test fun sendsMultipartContractAndAcceptsCorrelatedResponse() = runBlocking {
        server.enqueue(MockResponse().setBody(body()))
        val response = repo.protectImage(request, byteArrayOf(1, 2, 3)).getOrThrow()
        assertEquals("real", response.resultKind)
        val recorded = server.takeRequest(2, TimeUnit.SECONDS)!!
        assertEquals("/v1/protect", recorded.path)
        assertEquals("POST", recorded.method)
        val uploaded = recorded.body.readUtf8()
        listOf("name=\"image\"", "name=\"request_id\"", request.requestId,
            "gaussian_blur", "name=\"strength\"", "name=\"regions\"", "\"x\":0.2").forEach {
            assertTrue(it, uploaded.contains(it))
        }
    }

    @Test fun missingProtectEndpointCanRetryWithoutRecreatingRepository() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(404))
        server.enqueue(MockResponse().setBody(body()))
        val error = repo.protectImage(request, byteArrayOf(1)).exceptionOrNull()
        assertTrue(error?.message?.contains("아직 준비되지") == true)
        assertTrue(repo.protectImage(request, byteArrayOf(1)).isSuccess)
        assertEquals(2, server.requestCount)
    }

    @Test fun rejectsWrongRequestNoRegionsMissingImageAndMalformedJson() = runBlocking {
        val invalidBodies = listOf(body("other-request"), body(status = "no_regions"),
            body().replace("\"AA==\"", "null"), body().replace("\"real\"", "\"unknown\""), "{broken")
        for (invalid in invalidBodies) {
            server.enqueue(MockResponse().setBody(invalid))
            assertTrue(invalid, repo.protectImage(request, byteArrayOf(1)).isFailure)
        }
    }

    @Test fun serverErrorDoesNotExposeInternalResponseBody() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(500).setBody("PRIVATE_INTERNAL_PATH"))
        val error = repo.protectImage(request, byteArrayOf(1)).exceptionOrNull()!!
        assertFalse(error.message.orEmpty().contains("PRIVATE_INTERNAL_PATH"))
    }

    @Test fun timeoutReturnsFailure() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        val shortTimeout = ApiProtectionRepository(server.url("/").toString(), timeoutSeconds = 1)
        val result = withTimeout(5000) { shortTimeout.protectImage(request, byteArrayOf(1)) }
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()?.message?.contains("응답 시간이 초과") == true)
    }

    @Test fun explicitCancelInterruptsHttpAndAllowsAnotherRequest() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        val pending = async(Dispatchers.IO) { repo.protectImage(request, byteArrayOf(1)) }
        assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
        repo.cancelRequest(request.requestId)
        val result = withTimeout(3000) { pending.await() }
        assertTrue(result.exceptionOrNull() is CancellationException)
        server.enqueue(MockResponse().setBody(body()))
        assertTrue(repo.protectImage(request, byteArrayOf(1)).isSuccess)
    }

    @Test fun coroutineCancellationDoesNotWaitForSocketTimeout() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        val pending = async(Dispatchers.IO) { repo.protectImage(request, byteArrayOf(1)) }
        assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
        withTimeout(3000) { pending.cancelAndJoin() }
        assertTrue(pending.isCancelled)
    }

    @Test fun invalidStrengthDoesNotUploadImage() = runBlocking {
        val result = repo.protectImage(request.copy(strength = Float.NaN), byteArrayOf(1))
        assertTrue(result.isFailure)
        assertEquals(0, server.requestCount)
    }
}
