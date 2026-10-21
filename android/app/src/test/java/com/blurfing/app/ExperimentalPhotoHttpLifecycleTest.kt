package com.blurfing.app.experimental

import android.net.Uri
import androidx.lifecycle.ViewModelStore
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
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
import org.robolectric.annotation.GraphicsMode
import java.util.concurrent.TimeUnit

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ExperimentalPhotoHttpLifecycleTest {
    @Test fun readinessAndProcessingReuseConnectionAndAddressChangeUsesTheNewServer()=runBlocking {
        Dispatchers.setMain(Dispatchers.Unconfined);val store=ViewModelStore()
        try {
            MockWebServer().use { first -> MockWebServer().use { second ->
                val source=fixtures.source();val created=mutableListOf<String>()
                val ready=ExperimentalServerReadiness("ready","photo-experimental-v2","experimental",listOf("native_v12"),false)
                for(server in listOf(first,second)) {
                    server.dispatcher=object: okhttp3.mockwebserver.Dispatcher() {
                        override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse {
                            if(request.path=="/v2/ready")return json(Json.encodeToString(ready))
                            val id=request.body.readUtf8().substringAfter("name=\"request_id\"")
                                .substringAfter("\r\n\r\n").substringBefore("\r\n")
                            return json(Json.encodeToString(fixtures.response(source).copy(requestId=id)))
                        }
                    };server.start()
                }
                val vm=ExperimentalPhotoViewModel({ address ->
                    created+=address
                    ExperimentalPhotoRepository(address,allowLocalHttp=true,checkMemory=false)
                },{ _,_->source });store.put("connection",vm)
                vm.setAddress(first.url("/").toString())
                vm.select(RuntimeEnvironment.getApplication(),Uri.parse("content://synthetic/connection"))
                vm.checkServer()
                withTimeout(5000) { vm.state.first { !it.checkingServer } }
                assertNotNull(vm.state.value.readiness)
                vm.start()
                withTimeout(5000) { vm.state.first { !it.busy } }
                val firstId=vm.state.value.result!!.requestId
                assertEquals(1,created.size)
                assertEquals(0,first.takeRequest().sequenceNumber)
                assertEquals(1,first.takeRequest().sequenceNumber)
                vm.setAddress(second.url("/").toString());vm.start()
                vm.confirmReplacement(vm.state.value.replacement!!.token)
                withTimeout(5000) { vm.state.first { !it.busy } }
                assertNotNull(vm.state.value.result);assertNotEquals(firstId,vm.state.value.result!!.requestId)
                assertEquals(listOf(first.url("/").toString(),second.url("/").toString()),created)
                assertEquals("/v2/photo/protect",second.takeRequest().path)
                assertEquals(2,first.requestCount)
            } }
        } finally { store.clear();Dispatchers.resetMain() }
    }
    @Test fun experimentDefaultsToPublicOriginAndKeepsLocalDevelopmentAddresses() {
        assertEquals(com.blurfing.app.repository.BackendAddress.DEFAULT_SERVER,ExperimentalPhotoState().serverAddress)
        assertEquals("http://10.0.2.2:8001",EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT)
        assertEquals("http://10.0.2.2:8000",com.blurfing.app.repository.BackendAddress.EMULATOR_DEFAULT)
    }
    private val fixtures=ExperimentalPhotoDecoderTest()
    private fun wire(source: ExperimentalPhotoUpload)=Json.encodeToString(fixtures.response(source))
    private fun json(body: String)=MockResponse().setHeader("Content-Type","application/json").setBody(body)
    private suspend fun rejects(block: suspend ()->Unit) { try { block();fail("Invalid request/result accepted") } catch(_: IllegalArgumentException) { } catch(_: ExperimentalPhotoException) { } }

    @Test fun actualMultipartIsExplicitV2ExactPngAndLongRunningTimeoutOnly()=runBlocking {
        MockWebServer().use { server ->
            server.start();val source=fixtures.source();server.enqueue(json(wire(source)))
            val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true,checkMemory=false)
            val result=repo.protect(source,ExperimentalPhotoEngine.NATIVE,"synthetic")
            assertEquals(1L,result.changedPixels)
            val request=server.takeRequest(2,TimeUnit.SECONDS)!!;assertEquals("/v2/photo/protect",request.path)
            val raw=request.body.readByteArray();val body=raw.toString(Charsets.ISO_8859_1)
            for(field in listOf("name=\"request_id\"","name=\"method\"","photo_native_v12_experimental","name=\"scope\"","automatic_photo","name=\"strength\"","0.5"))assertTrue(body.contains(field))
            assertFalse(body.contains("name=\"photo_engine\""));assertFalse(body.contains("gaussian_blur"));assertFalse(body.contains("regions"))
            assertTrue(body.contains(source.png.toString(Charsets.ISO_8859_1)))
            assertTrue(repo.client.readTimeoutMillis>=600000 && repo.client.callTimeoutMillis>=600000)
        }
    }
    @Test fun staleIdentityDuplicateKeysAndUnknownFlagsRejectWithoutFallback()=runBlocking {
        MockWebServer().use { server ->
            server.start();val s=fixtures.source();val r=fixtures.response(s)
            val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true,checkMemory=false)
            val body=wire(s)
            val invalid=listOf(Json.encodeToString(r.copy(requestId="other")),Json.encodeToString(r.copy(photoEngine="unknown")),
                body.replace("\"status\":", "\"status\":\"success\",\"status\":"),
                body.replace("\"encoding\":", "\"encoding\":\"bad\",\"encoding\":"),
                body.replace("\"privacy_validated\":false", "\"privacy_validated\":true,\"privacy\\u005fvalidated\":false"))
            for(value in invalid) { server.enqueue(json(value));rejects { repo.protect(s,ExperimentalPhotoEngine.NATIVE,"synthetic") } }
            assertEquals(invalid.size,server.requestCount)
        }
    }
    @Test fun httpFailureRedirectAndOversizedDeclaredBodyKeepNoFallback()=runBlocking {
        MockWebServer().use { server ->
            server.start();val s=fixtures.source();val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true,checkMemory=false)
            server.enqueue(MockResponse().setResponseCode(503));server.enqueue(MockResponse().setResponseCode(302).setHeader("Location",server.url("/v1/protect")))
            server.enqueue(json("x").setHeader("Content-Length",ExperimentalPhotoRepository.MAX_RESPONSE_BYTES+1))
            repeat(3) { rejects { repo.protect(s,ExperimentalPhotoEngine.NATIVE,"synthetic") } }
            assertEquals(3,server.requestCount)
        }
    }
    @Test fun cancellationClosesTheActualCallWithoutWaitingForTheServer()=runBlocking {
        MockWebServer().use { server ->
            server.start();server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val repo=ExperimentalPhotoRepository(server.url("/").toString(),allowLocalHttp=true,checkMemory=false)
            val task=launch { repo.protect(fixtures.source(),ExperimentalPhotoEngine.NATIVE,"synthetic") }
            assertNotNull(withContext(Dispatchers.IO) { server.takeRequest(5,TimeUnit.SECONDS) })
            withTimeout(2000) { task.cancelAndJoin() };assertTrue(task.isCancelled)
        }
    }
    @Test fun jsonPreflightRejectsNestedEscapedDuplicatesAndExcessiveNesting() {
        for(value in listOf("{\"a\":1,\"a\":2}","{\"a\":{\"x\":1,\"\\u0078\":2}}","[".repeat(33)+"0"+"]".repeat(33))) {
            try { ExperimentalJsonGuard.verify(value);fail() } catch(_: IllegalArgumentException) { }
        }
        ExperimentalJsonGuard.verify("{\"a\":[{\"x\":1},{\"x\":2}],\"s\":\"\\\"quoted\\\"\"}")
    }
    @Test fun cancelledOrNewPhotoJobsCannotPublishLateResultsAndSaveTicketsExpire()=runBlocking {
        Dispatchers.setMain(Dispatchers.Unconfined)
        val store=ViewModelStore()
        try {
            val source=fixtures.source();val waiting=CompletableDeferred<Unit>();val called=CompletableDeferred<String>()
            val service=object: ExperimentalPhotoService {
                var cancelled=false
                override fun cancel(requestId: String) { cancelled=true }
                override suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto {
                    called.complete(requestId)
                    return withContext(NonCancellable) { waiting.await();ExperimentalPhotoDecoder.decode(fixtures.response(source).copy(requestId=requestId),source,engine,requestId,checkMemory=false) }
                }
            }
            val vm=ExperimentalPhotoViewModel({ service },{ _,_->source });store.put("test",vm)
            val context=RuntimeEnvironment.getApplication();vm.select(context,Uri.parse("content://synthetic/one"));assertSame(source,vm.state.value.source)
            vm.start();called.await();vm.cancel();assertTrue(service.cancelled);assertSame(source,vm.state.value.source)
            waiting.complete(Unit);yield();assertNull(vm.state.value.result);assertFalse(vm.state.value.busy)
            assertNull(vm.prepareSave())
            vm.select(context,Uri.parse("content://synthetic/two"));assertSame(source,vm.state.value.source)
            vm.finishSave(context,null,"old");assertNull(vm.state.value.result)
        } finally { store.clear();Dispatchers.resetMain() }
    }
    @Test fun failureRetainsOriginalAndARealRetryCanPresentResultThenExpireSaveTicket()=runBlocking {
        Dispatchers.setMain(Dispatchers.Unconfined);val store=ViewModelStore()
        try {
            val source=fixtures.source();var calls=0
            val service=object: ExperimentalPhotoService {
                override fun cancel(requestId: String)=Unit
                override suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto {
                    if(++calls==1)throw ExperimentalPhotoException("synthetic failure")
                    return ExperimentalPhotoDecoder.decode(fixtures.response(source).copy(requestId=requestId),source,engine,requestId,checkMemory=false)
                }
            }
            val context=RuntimeEnvironment.getApplication();val vm=ExperimentalPhotoViewModel({ service },{ _,_->source });store.put("test",vm)
            vm.select(context,Uri.parse("content://synthetic/one"));vm.start();assertSame(source,vm.state.value.source);assertNull(vm.state.value.result)
            vm.start();assertNotNull(vm.state.value.result);val ticket=vm.prepareSave();assertNotNull(ticket)
            vm.cancel();vm.select(context,Uri.parse("content://synthetic/two"))
            vm.confirmReplacement(vm.state.value.replacement!!.token);vm.finishSave(context,null,ticket)
            assertFalse(vm.state.value.awaitingSave);assertFalse(vm.state.value.saving);assertNull(vm.state.value.result)
        } finally { store.clear();Dispatchers.resetMain() }
    }
}
