package com.blurfing.app

import com.blurfing.app.repository.BackendReadinessClient
import com.blurfing.app.repository.ReadinessKind
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class BackendReadinessTest {
    @Test fun readinessUsesGetAndNeverUploadsPhoto()= runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"status":"ready"}"""))
            val result=BackendReadinessClient().check(server.url("/").toString())
            assertEquals(ReadinessKind.READY,result.kind)
            val request=server.takeRequest()
            assertEquals("GET",request.method); assertEquals("/ready",request.path)
            assertEquals(0L,request.bodySize)
        }
    }
    @Test fun handlesUnreadyOldServerAndInvalidPayload()= runBlocking {
        MockWebServer().use { server ->
            val client=BackendReadinessClient()
            for((response,expected) in listOf(
                MockResponse().setResponseCode(503) to ReadinessKind.UNAVAILABLE,
                MockResponse().setResponseCode(404) to ReadinessKind.UNSUPPORTED,
                MockResponse().setBody("{broken}") to ReadinessKind.ERROR,
                MockResponse().setBody("x".repeat(16_385)) to ReadinessKind.ERROR)) {
                server.enqueue(response)
                assertEquals(expected,client.check(server.url("/").toString()).kind)
            }
        }
    }
}
