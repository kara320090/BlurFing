package com.blurfing.app.experimental

import com.blurfing.app.BuildConfig
import com.blurfing.app.repository.BackendAddress
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlin.coroutines.coroutineContext
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

interface ExperimentalPhotoService {
    suspend fun readiness(): ExperimentalServerReadiness = throw ExperimentalPhotoException("서버 준비 상태 확인을 지원하지 않습니다.")
    suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto
    fun cancel(requestId: String)
}

/** V2 is explicit and never falls back to Gaussian, mock, another engine or a cached result. */
class ExperimentalPhotoRepository(
    serverAddress: String,
    internal val client: OkHttpClient=OkHttpClient.Builder().connectTimeout(30,TimeUnit.SECONDS)
        .readTimeout(660,TimeUnit.SECONDS).writeTimeout(660,TimeUnit.SECONDS).callTimeout(720,TimeUnit.SECONDS)
        .followRedirects(false).followSslRedirects(false).build(),
    allowLocalHttp: Boolean=BuildConfig.DEBUG,
    private val checkMemory: Boolean=true,
    private val responseObserver: ((String)->Unit)?=null
): ExperimentalPhotoService {
    private val baseUrl=try { BackendAddress.normalize(serverAddress,allowLocalHttp) }
        catch(e: IllegalArgumentException) { throw ExperimentalPhotoException(e.message ?: "사진 AI 서버 주소를 확인해 주세요.",e) }
    private val calls=ConcurrentHashMap<String,Call>()
    private val json=Json { ignoreUnknownKeys=false;isLenient=false;coerceInputValues=false }
    override fun cancel(requestId: String) { calls.remove(requestId)?.cancel() }
    override suspend fun readiness(): ExperimentalServerReadiness = withContext(Dispatchers.IO) {
        val probeClient = client.newBuilder().callTimeout(30,TimeUnit.SECONDS).readTimeout(30,TimeUnit.SECONDS).build()
        val call = probeClient.newCall(Request.Builder().url("$baseUrl/ready").get().build())
        val text = suspendCancellableCoroutine<String> { continuation ->
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object: Callback {
                override fun onFailure(call: Call,e: IOException) {
                    if(continuation.isActive)continuation.resumeWithException(ExperimentalPhotoException("서버에 연결하지 못했습니다. 주소·네트워크·서버 실행 상태를 확인해 주세요.",e))
                }
                override fun onResponse(call: Call,response: Response) {
                    try {
                        val value=response.use { r ->
                            if(!r.isSuccessful)throw experimentalHttpFailure(r.code)
                            require(r.header("Content-Type")?.substringBefore(';')?.trim()?.lowercase()=="application/json")
                            val body=requireNotNull(r.body)
                            require(body.contentLength()==-1L || body.contentLength() in 1..32768)
                            val output=ByteArrayOutputStream()
                            body.byteStream().use { input ->
                                val buffer=ByteArray(4096)
                                while(true) {
                                    if(!continuation.isActive)throw IOException("cancelled")
                                    val n=input.read(buffer);if(n<0)break
                                    require(output.size()+n<=32768);output.write(buffer,0,n)
                                }
                            }
                            require(output.size()>0 && (body.contentLength()<0 || output.size().toLong()==body.contentLength()))
                            output.toString(Charsets.UTF_8.name())
                        }
                        if(continuation.isActive)continuation.resume(value)
                    } catch(e: Exception) { if(continuation.isActive)continuation.resumeWithException(e) }
                }
            })
        }
        coroutineContext.ensureActive()
        try {
            ExperimentalJsonGuard.verify(text)
            json.decodeFromString<ExperimentalServerReadiness>(text).verify()
        } catch(e: Exception) { throw ExperimentalPhotoException("사진 AI V2 준비 응답을 확인하지 못했습니다. 서버 주소와 버전을 확인해 주세요.",e) }
    }
    override suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto = withContext(Dispatchers.IO) {
        require(requestId.isNotBlank() && requestId.length<=200 && requestId.all { it.code in 33..126 })
        val context=coroutineContext
        source.verify { context.ensureActive() }
        val request=Request.Builder().url("$baseUrl/v2/photo/protect").post(MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("image","upload.RGB.EXIF1.png",source.png.toRequestBody("image/png".toMediaType()))
            .addFormDataPart("request_id",requestId).addFormDataPart("method",engine.method)
            .addFormDataPart("scope","automatic_photo").addFormDataPart("strength","0.5").build()).build()
        val call=client.newCall(request)
        require(calls.putIfAbsent(requestId,call)==null)
        try {
            val text=suspendCancellableCoroutine<String> { continuation ->
                continuation.invokeOnCancellation { call.cancel() }
                call.enqueue(object: Callback {
                    override fun onFailure(call: Call,e: IOException) { if(continuation.isActive)continuation.resumeWithException(ExperimentalPhotoException("AI 서버에 연결하지 못했습니다. 원본은 유지됩니다.",e)) }
                    override fun onResponse(call: Call,response: Response) {
                        try {
                            val value=response.use { r ->
                                if(!r.isSuccessful)throw experimentalHttpFailure(r.code)
                                require(r.header("Content-Type")?.substringBefore(';')?.trim()=="application/json")
                                val body=r.body ?: throw IOException("empty body")
                                val length=body.contentLength();require(length==-1L || length in 1..MAX_RESPONSE_BYTES)
                                fun budget(n: Long) { if(checkMemory)ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.responseRead(source.width,source.height,source.png.size,n)) }
                                if(length>=0)budget(length)
                                body.byteStream().use { input ->
                                    val output=ByteArrayOutputStream();val buffer=ByteArray(8192)
                                    while(true) {
                                        if(!continuation.isActive)throw IOException("cancelled")
                                        val n=input.read(buffer);if(n<0)break
                                        val next=output.size().toLong()+n;require(next<=MAX_RESPONSE_BYTES);budget(if(length>=0)length else next)
                                        output.write(buffer,0,n)
                                    }
                                    require(output.size()>0 && (length<0 || output.size().toLong()==length))
                                    output.toString(Charsets.UTF_8.name())
                                }
                            }
                            if(continuation.isActive)continuation.resume(value)
                        } catch(e: Exception) { if(continuation.isActive)continuation.resumeWithException(e) }
                        catch(e: OutOfMemoryError) { if(continuation.isActive)continuation.resumeWithException(ExperimentalPhotoException("메모리가 부족해 응답을 중단했습니다. 원본은 유지됩니다.",e)) }
                    }
                })
            }
            context.ensureActive()
            responseObserver?.invoke(text)
            ExperimentalJsonGuard.verify(text)
            val dto=json.decodeFromString<ExperimentalPhotoResponse>(text)
            ExperimentalPhotoDecoder.decode(dto,source,engine,requestId,{context.ensureActive()},checkMemory)
        } finally { calls.remove(requestId,call);call.cancel() }
    }
    companion object { const val MAX_RESPONSE_BYTES=64L*1024*1024 }
}
