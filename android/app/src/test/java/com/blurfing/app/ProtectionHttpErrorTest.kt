package com.blurfing.app

import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.repository.ApiProtectionRepository
import com.blurfing.app.repository.ProtectionHttpException
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.MockResponse
import org.junit.Assert.*
import org.junit.Test

class ProtectionHttpErrorTest {
    @Test fun preservesCorrelatedErrorCodeWithoutExposingRemoteMessage()=runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setResponseCode(504).setBody("""{"request_id":"local-test","code":"PROCESSING_TIMEOUT","retryable":true,"message":"PRIVATE_PATH_TOKEN"}"""))
            val error=ApiProtectionRepository(server.url("/").toString()).protectImage(ProtectionRequest("local-test"),byteArrayOf(1)).exceptionOrNull() as ProtectionHttpException
            assertEquals(504,error.statusCode); assertEquals("PROCESSING_TIMEOUT",error.errorCode)
            assertTrue(error.retryable); assertFalse(error.message!!.contains("PRIVATE_PATH_TOKEN"))
        }
    }
    @Test fun wrongRequestAndPermanentErrorsDoNotTrustRemoteRetryFlag()=runBlocking {
        MockWebServer().use { server ->
            val repo=ApiProtectionRepository(server.url("/").toString())
            server.enqueue(MockResponse().setResponseCode(400).setBody("""{"request_id":"other","code":"FAKE","retryable":true}"""))
            val error=repo.protectImage(ProtectionRequest("local-test"),byteArrayOf(1)).exceptionOrNull() as ProtectionHttpException
            assertNull(error.errorCode); assertFalse(error.retryable)
            server.enqueue(MockResponse().setResponseCode(409))
            val conflict=repo.protectImage(ProtectionRequest("new-test"),byteArrayOf(1)).exceptionOrNull() as ProtectionHttpException
            assertTrue(conflict.retryable); assertTrue(conflict.message!!.contains("처리 중"))
        }
    }
}
