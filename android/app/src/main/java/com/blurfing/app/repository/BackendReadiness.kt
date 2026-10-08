package com.blurfing.app.repository

import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.*
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

enum class ReadinessKind { IDLE, CHECKING, READY, UNAVAILABLE, UNSUPPORTED, ERROR }
data class BackendReadiness(val kind: ReadinessKind, val message: String) {
    companion object {
        val Idle = BackendReadiness(ReadinessKind.IDLE,"준비 상태를 아직 확인하지 않았습니다.")
        val Checking = BackendReadiness(ReadinessKind.CHECKING,"서버 준비 상태를 확인하는 중…")
    }
}

/** GET /ready sends no images, coordinates, or photo identifiers. Redirects are not followed. */
class BackendReadinessClient(private val client: OkHttpClient = OkHttpClient.Builder()
    .callTimeout(5,TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false).build()) {
    suspend fun check(address: String): BackendReadiness = suspendCancellableCoroutine { continuation ->
        val call = client.newCall(Request.Builder().url("${address.trimEnd('/')}/ready").get().build())
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, error: IOException) {
                if(continuation.isActive) continuation.resume(BackendReadiness(ReadinessKind.ERROR,
                    "서버에 연결하지 못했습니다. 주소와 네트워크를 확인해 주세요."))
            }
            override fun onResponse(call: Call, response: Response) {
                val result = response.use {
                    when(it.code) {
                        200 -> runCatching {
                            val source = requireNotNull(it.body?.source())
                            source.request(16_385)
                            require(source.buffer.size <= 16_384)
                            val json = Json.parseToJsonElement(source.buffer.readUtf8()).jsonObject
                            require(json["status"]?.jsonPrimitive?.content == "ready")
                            BackendReadiness(ReadinessKind.READY,"서버 처리 모듈이 연결돼 있습니다. 실제 보호 효과는 별도 검증이 필요합니다.")
                        }.getOrElse { BackendReadiness(ReadinessKind.ERROR,"서버 준비 응답 형식을 확인해 주세요.") }
                        503 -> BackendReadiness(ReadinessKind.UNAVAILABLE,"서버는 응답하지만 보호 처리 모듈이 준비되지 않았습니다.")
                        404 -> BackendReadiness(ReadinessKind.UNSUPPORTED,"이 서버는 준비 상태 확인을 지원하지 않습니다. 담당자에게 실행 상태를 확인해 주세요.")
                        else -> BackendReadiness(ReadinessKind.ERROR,"서버 준비 상태를 확인하지 못했습니다 (HTTP ${it.code}).")
                    }
                }
                if(continuation.isActive) continuation.resume(result)
            }
        })
    }
}
