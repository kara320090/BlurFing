package com.blurfing.app.experimental

import kotlinx.coroutines.*
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import android.content.Context
import com.blurfing.app.repository.BackendAddress
import java.util.concurrent.TimeUnit

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
class ExperimentalPhotoReadinessTest {
    private val ready=ExperimentalServerReadiness("ready","photo-experimental-v2","experimental",listOf("native_v12","pose_v14"),false)
    private fun response(text: String)=MockResponse().setHeader("Content-Type","application/json").setBody(text)
    private suspend fun rejects(action: suspend ()->Unit): String {
        try { action();fail("Invalid ready response accepted") } catch(e: Exception) { return e.message.orEmpty() }
        error("unreachable")
    }
    @Test fun actualReadyGetUsesConfiguredPrefixAndNeverTransmitsAPhoto()=runBlocking {
        MockWebServer().use { server ->
            server.start();server.enqueue(response(Json.encodeToString(ready)))
            val repo=ExperimentalPhotoRepository(server.url("/photo/").toString(),allowLocalHttp=true)
            assertEquals(ready,repo.readiness())
            val request=server.takeRequest(2,TimeUnit.SECONDS)!!
            assertEquals("GET",request.method);assertEquals("/photo/v2/ready",request.path)
            assertEquals(0L,request.bodySize);assertEquals(1,server.requestCount)
        }
    }
    @Test fun standaloneV2UsesLegacyReadyOnlyAfterNamespaced404()=runBlocking {
        MockWebServer().use { server ->
            server.start()
            server.enqueue(MockResponse().setResponseCode(404))
            server.enqueue(response(Json.encodeToString(ready)))
            val repo=ExperimentalPhotoRepository(server.url("/photo/").toString(),allowLocalHttp=true)
            assertEquals(ready,repo.readiness())
            assertEquals("/photo/v2/ready",server.takeRequest(2,TimeUnit.SECONDS)!!.path)
            assertEquals("/photo/ready",server.takeRequest(2,TimeUnit.SECONDS)!!.path)
            assertEquals(2,server.requestCount)
        }
    }
    @Test fun unavailableAiNeverFallsBackToMockReadiness()=runBlocking {
        MockWebServer().use { server ->
            server.start()
            server.enqueue(MockResponse().setResponseCode(503))
            server.enqueue(response("{\"status\":\"ready\"}"))
            val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true)
            assertTrue(rejects { repo.readiness() }.contains("준비되지"))
            assertEquals("/v2/ready",server.takeRequest(2,TimeUnit.SECONDS)!!.path)
            assertEquals(1,server.requestCount)
        }
    }
    @Test fun v1ReadyIsNotAcceptedAsAnAiServer()=runBlocking {
        MockWebServer().use { server ->
            server.start()
            server.enqueue(MockResponse().setResponseCode(404))
            server.enqueue(response("{\"status\":\"ready\"}"))
            val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true)
            assertTrue(rejects { repo.readiness() }.contains("V2"))
            assertEquals(2,server.requestCount)
        }
    }
    @Test fun defaultUsesTunnelAndKeepsAnExplicitlySavedServer() {
        val context=RuntimeEnvironment.getApplication()
        val preferences=context.getSharedPreferences("experimental-photo-settings",Context.MODE_PRIVATE)
        preferences.edit().clear().commit()
        try {
            val settings=ExperimentalPhotoSettings(context)
            assertEquals(BackendAddress.DEFAULT_SERVER,settings.load().address)
            assertEquals(BackendAddress.DEFAULT_SERVER,ExperimentalPhotoState().serverAddress)
            settings.save(EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT,ExperimentalPhotoEngine.SYNTHETIC)
            assertEquals(EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT,settings.load().address)
            assertEquals(ExperimentalPhotoEngine.SYNTHETIC,settings.load().engine)
        } finally { preferences.edit().clear().commit() }
    }
    @Test fun invalidContractApprovalEngineListsAndDuplicateJsonAreRejected()=runBlocking {
        MockWebServer().use { server ->
            server.start();val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true)
            val invalid=listOf(ready.copy(contractVersion="v1"),ready.copy(productionApproved=true),
                ready.copy(resultKind="mock"),ready.copy(photoEngines=emptyList()),ready.copy(photoEngines=listOf("pose_v14","pose_v14")),
                ready.copy(photoEngines=listOf("other"))).map { Json.encodeToString(it) }+
                listOf("{\"status\":\"ready\",\"status\":\"ready\"}","<html>private path</html>")
            invalid.forEach { server.enqueue(response(it));assertTrue(rejects { repo.readiness() }.contains("V2")) }
            assertEquals(invalid.size,server.requestCount)
        }
    }
    @Test fun redirectAndOversizedChunkedReadyResponseDoNotFallBack()=runBlocking {
        MockWebServer().use { server ->
            server.start();val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true)
            server.enqueue(MockResponse().setResponseCode(302).setHeader("Location",server.url("/v1/protect")))
            assertTrue(rejects { repo.readiness() }.contains("HTTPS"))
            server.enqueue(response("x".repeat(32769)).setChunkedBody("x".repeat(32769),1024))
            rejects { repo.readiness() };assertEquals(2,server.requestCount)
        }
    }
    @Test fun actualReadyCallCancelsPromptly()=runBlocking {
        MockWebServer().use { server ->
            server.start();server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true)
            val job=launch { repo.readiness() }
            assertNotNull(withContext(Dispatchers.IO) { server.takeRequest(5,TimeUnit.SECONDS) })
            withTimeout(2000) { job.cancelAndJoin() };assertTrue(job.isCancelled)
        }
    }
    @Test fun httpGuidanceIsLocalAndDoesNotExposeResponseText()=runBlocking {
        MockWebServer().use { server ->
            server.start();val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true)
            val expected=mapOf(404 to "V2",429 to "다른 사진",503 to "준비되지",504 to "시간",413 to "용량",403 to "접근 권한")
            expected.forEach { (code,hint) ->
                if(code==404)server.enqueue(MockResponse().setResponseCode(404))
                server.enqueue(MockResponse().setResponseCode(code).setBody("PRIVATE_SERVER_PATH /home/private/token"))
                val message=rejects { repo.readiness() };assertTrue(message.contains(hint));assertFalse(message.contains("PRIVATE_SERVER_PATH"))
            }
        }
    }
}
