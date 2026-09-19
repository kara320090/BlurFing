package com.blurfing.app.repository

import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/**
 * contracts/protection-api.md 규격을 준수하는 백엔드 API 연동 어댑터 (BF-07).
 *
 * 담당: 이봉헌 (Android 앱 및 시스템 통합)
 * 연동 대상: 한윤섭 (백엔드 API 및 서버 모듈)
 *
 * 주요 처리 사항:
 * - 동적 base URL 구성 (로컬 에뮬레이터 10.0.2.2:8000 또는 실제 호스트)
 * - 설정 가능한 타임아웃 (기본 30초)
 * - 연결 실패, 시간 초과, 취소 처리
 * - 클라이언트 측 request_id 기반 늦은 응답 무시
 * - 최대 파일 크기 (기본 15MB) 사전 검사
 */
class ApiProtectionRepository(
    private val baseUrl: String = "http://10.0.2.2:8000",
    private val maxImageSizeBytes: Long = 15 * 1024 * 1024L, // 15MB
    private val timeoutSeconds: Long = 30L,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .readTimeout(timeoutSeconds, TimeUnit.SECONDS)
        .writeTimeout(timeoutSeconds, TimeUnit.SECONDS)
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

        // 1. 취소 여부 확인
        if (cancelledRequestIds.contains(requestId)) {
            return@withContext Result.failure(CancellationException("요청이 취소되었습니다: $requestId"))
        }

        // 2. 용량 검사 (15MB 초과 시 서버 전송 전 차단)
        if (imageBytes.size > maxImageSizeBytes) {
            return@withContext Result.failure(
                IllegalArgumentException("이미지 용량이 너무 큽니다 (${imageBytes.size / (1024 * 1024)}MB). 최대 15MB 이하만 전송 가능합니다.")
            )
        }

        // 3. Multipart 요청 바디 생성
        val multipartBuilder = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("request_id", requestId)
            .addFormDataPart("method", request.method.apiValue)
            .addFormDataPart("strength", request.strength.toString())
            .addFormDataPart(
                "image",
                "upload.png",
                imageBytes.toRequestBody("image/png".toMediaType())
            )

        request.regions?.let { regions ->
            val regionsJson = json.encodeToString(
                kotlinx.serialization.builtins.ListSerializer(NormalizedRegion.serializer()),
                regions
            )
            multipartBuilder.addFormDataPart("regions", regionsJson)
        }

        val httpRequest = Request.Builder()
            .url("$baseUrl/v1/protect")
            .post(multipartBuilder.build())
            .build()

        val call = client.newCall(httpRequest)
        activeCalls[requestId] = call

        try {
            val response = call.execute()
            activeCalls.remove(requestId)

            // 늦은 응답 검사 (호출 완료 시점에 이미 취소된 경우)
            if (cancelledRequestIds.contains(requestId)) {
                return@withContext Result.failure(CancellationException("요청 취소 후 도착한 응답을 폐기했습니다: $requestId"))
            }

            if (!response.isSuccessful) {
                val errorBody = response.body?.string() ?: ""
                val errorMessage = when (response.code) {
                    400 -> "잘못된 요청 파라미터 또는 영역 좌표입니다: $errorBody"
                    413 -> "서버 허용 파일 용량을 초과했습니다."
                    500 -> "서버 내부 처리 오류가 발생했습니다: $errorBody"
                    503 -> "보호 처리 서비스를 일시적으로 사용할 수 없습니다."
                    else -> "서버 오류 (HTTP ${response.code}): $errorBody"
                }
                return@withContext Result.failure(IOException(errorMessage))
            }

            val bodyString = response.body?.string()
                ?: return@withContext Result.failure(IOException("서버 응답 바디가 비어 있습니다."))

            val protectionResponse = json.decodeFromString<ProtectionResponse>(bodyString)
            Result.success(protectionResponse)
        } catch (e: IOException) {
            activeCalls.remove(requestId)
            if (call.isCanceled() || cancelledRequestIds.contains(requestId)) {
                Result.failure(CancellationException("요청이 취소되었습니다: $requestId"))
            } else {
                Result.failure(IOException("서버 연결 실패 또는 타임아웃 ($baseUrl): ${e.localizedMessage}", e))
            }
        } catch (e: Exception) {
            activeCalls.remove(requestId)
            Result.failure(e)
        }
    }

    override fun cancelRequest(requestId: String) {
        cancelledRequestIds.add(requestId)
        activeCalls.remove(requestId)?.cancel()
    }
}
