package com.blurfing.app.repository

import java.io.IOException
import kotlinx.serialization.json.*
import okhttp3.Response

class ProtectionHttpException(val statusCode: Int, val errorCode: String?, val retryable: Boolean,
    message: String) : IOException(message)

object ProtectionHttpError {
    fun from(response: Response, requestId: String): ProtectionHttpException {
        val code = response.code
        var serverCode: String? = null
        var retry = code in listOf(409,429,500,502,503,504)
        runCatching {
            val source = requireNotNull(response.body?.source())
            source.request(65_537)
            require(source.buffer.size <= 65_536)
            val body = Json.parseToJsonElement(source.buffer.readUtf8()).jsonObject
            if(body["request_id"]?.jsonPrimitive?.content == requestId) {
                serverCode = body["code"]?.jsonPrimitive?.content?.takeIf { it.matches(Regex("[A-Z0-9_]{1,80}")) }
                // A server may prohibit retry but cannot turn a permanent input error into a retry loop.
                if(body["retryable"]?.jsonPrimitive?.booleanOrNull == false) retry=false
            }
        }
        val message = when(code) {
            400,422 -> "사진, 보호 설정 또는 영역 좌표를 확인해 주세요."
            404 -> "서버에 보호 API가 아직 준비되지 않았습니다. 백엔드 담당자에게 확인해 주세요."
            409 -> "같은 요청이 서버에서 처리 중입니다. 완료될 때까지 기다린 뒤 다시 시도해 주세요."
            413 -> "서버 허용 파일 용량을 초과했습니다."
            415 -> "서버에서 지원하지 않는 이미지 형식입니다. PNG 또는 JPEG 파일을 사용해 주세요."
            429 -> "서버 요청이 많습니다. 잠시 기다린 뒤 다시 시도해 주세요."
            500 -> "서버 내부 처리 오류가 발생했습니다."
            501 -> "서버의 이미지 보호 기능이 아직 준비되지 않았습니다. 로컬 Mock 프리뷰로 확인하거나 서버 준비 후 다시 시도해 주세요."
            502 -> "보호 처리 서버의 연결을 확인해 주세요."
            503 -> "보호 처리 서비스를 일시적으로 사용할 수 없습니다."
            504 -> "서버의 보호 처리 시간이 초과되었습니다. 잠시 기다린 뒤 다시 시도해 주세요."
            in 300..399 -> "서버 주소가 변경되었습니다. 사용할 서버 주소를 직접 확인해 주세요."
            else -> "서버 오류가 발생했습니다 (HTTP $code)."
        }
        // The remote message, image, paths and arbitrary fields are never displayed.
        return ProtectionHttpException(code,serverCode,retry,message)
    }
}
