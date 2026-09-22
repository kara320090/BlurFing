package com.blurfing.app.repository

import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume

/** Android 담당의 통신 어댑터. 서버 구현은 backend/ 담당자가 제공한다. */
class ApiProtectionRepository(
    private val baseUrl: String = BackendAddress.EMULATOR_DEFAULT,
    private val maxImageSizeBytes: Long = 15 * 1024 * 1024L,
    private val timeoutSeconds: Long = 30L,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .readTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .writeTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .callTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .followRedirects(false)
        .followSslRedirects(false)
        .build()
) : ProtectionRepository {
    private val json = Json { ignoreUnknownKeys = true }
    private val activeCalls = ConcurrentHashMap<String, Call>()
    private val cancelledRequestIds = ConcurrentHashMap.newKeySet<String>()

    override suspend fun protectImage(
        request: ProtectionRequest,
        imageBytes: ByteArray
    ): Result<ProtectionResponse> = withContext(Dispatchers.IO) {
        val requestId = request.requestId
        if (cancelledRequestIds.remove(requestId)) {
            return@withContext Result.failure(CancellationException("요청이 취소되었습니다."))
        }
        if (imageBytes.size > maxImageSizeBytes) {
            return@withContext Result.failure(
                IllegalArgumentException("이미지 용량이 너무 큽니다. 최대 ${maxImageSizeBytes / 1024}KB까지 전송할 수 있습니다.")
            )
        }
        if (imageBytes.isEmpty() || !request.strength.isFinite() || request.strength !in 0f..1f) {
            return@withContext Result.failure(IllegalArgumentException("사진과 보호 강도를 확인해 주세요."))
        }

        try {
            val multipart = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("request_id", requestId)
                .addFormDataPart("method", request.method.apiValue)
                .addFormDataPart("strength", request.strength.toString())
                .addFormDataPart("image", "upload.png", imageBytes.toRequestBody("image/png".toMediaType()))
            request.regions?.let {
                multipart.addFormDataPart("regions", json.encodeToString(ListSerializer(NormalizedRegion.serializer()), it))
            }
            val httpRequest = Request.Builder()
                .url("${baseUrl.trimEnd('/')}/v1/protect")
                .post(multipart.build())
                .build()
            val call = client.newCall(httpRequest)
            if (activeCalls.putIfAbsent(requestId, call) != null) {
                return@withContext Result.failure(IllegalArgumentException("같은 요청이 이미 진행 중입니다."))
            }
            try {
                if (cancelledRequestIds.contains(requestId)) call.cancel()
                awaitResult(call, requestId)
            } finally {
                activeCalls.remove(requestId, call)
                cancelledRequestIds.remove(requestId)
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private suspend fun awaitResult(call: Call, requestId: String): Result<ProtectionResponse> =
        suspendCancellableCoroutine { continuation ->
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    val error = if (cancelledRequestIds.contains(requestId)) {
                        CancellationException("요청이 취소되었습니다.")
                    } else {
                        IOException("서버에 연결하지 못했거나 응답 시간이 초과되었습니다. 주소와 서버 상태를 확인해 주세요.", e)
                    }
                    if (continuation.isActive) continuation.resume(Result.failure(error))
                }

                override fun onResponse(call: Call, response: Response) {
                    // 취소·파싱 실패를 포함해 모든 경로에서 본문과 소켓을 정리한다.
                    val result = runCatching {
                        response.use {
                            if (call.isCanceled() || cancelledRequestIds.contains(requestId)) {
                                throw CancellationException("취소된 응답을 적용하지 않았습니다.")
                            }
                            if (!it.isSuccessful) throw IOException(httpError(it.code))
                            val source = it.body?.source() ?: throw IOException("서버 응답이 비어 있습니다.")
                            source.request(MAX_RESPONSE_BYTES + 1)
                            if (source.buffer.size > MAX_RESPONSE_BYTES) throw IOException("서버 응답의 크기 제한을 초과했습니다.")
                            val bytes = source.buffer.readByteArray()
                            val parsed = json.decodeFromString<ProtectionResponse>(bytes.toString(Charsets.UTF_8))
                            ProtectionResponseValidator.validate(parsed, requestId)
                            parsed
                        }
                    }
                    val finalResult = when {
                        cancelledRequestIds.contains(requestId) ->
                            Result.failure(CancellationException("취소된 응답을 적용하지 않았습니다."))
                        call.isCanceled() ->
                            Result.failure(IOException("서버 응답 시간이 초과되었습니다. 다시 시도해 주세요."))
                        else -> result
                    }
                    if (continuation.isActive) continuation.resume(finalResult)
                }
            })
        }

    override fun cancelRequest(requestId: String) {
        cancelledRequestIds.add(requestId)
        activeCalls[requestId]?.cancel()
    }

    private fun httpError(code: Int): String = when (code) {
        400, 422 -> "사진, 보호 설정 또는 영역 좌표를 확인해 주세요."
        404 -> "서버에 보호 API가 아직 준비되지 않았습니다. 백엔드 담당자에게 확인해 주세요."
        413 -> "서버 허용 파일 용량을 초과했습니다."
        415 -> "서버에서 지원하지 않는 이미지 형식입니다. PNG 또는 JPEG 파일을 사용해 주세요."
        500 -> "서버 내부 처리 오류가 발생했습니다."
        501 -> "서버의 이미지 보호 기능이 아직 준비되지 않았습니다. 로컬 Mock 프리뷰로 확인하거나 서버 준비 후 다시 시도해 주세요."
        503 -> "보호 처리 서비스를 일시적으로 사용할 수 없습니다."
        in 300..399 -> "서버 주소가 변경되었습니다. 사용할 서버 주소를 직접 확인해 주세요."
        else -> "서버 오류가 발생했습니다 (HTTP $code)."
    }

    companion object {
        private const val MAX_RESPONSE_BYTES = 24 * 1024 * 1024L
    }
}
