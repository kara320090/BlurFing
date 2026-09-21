package com.blurfing.app.repository

import com.blurfing.app.model.ProtectionResponse
import java.io.IOException

object ProtectionResponseValidator {
    fun validate(response: ProtectionResponse, requestId: String) {
        if (response.requestId != requestId) {
            throw IOException("요청과 응답의 식별자가 달라 결과를 적용하지 않았습니다.")
        }
        if (response.status == "no_regions") {
            throw IOException("처리할 지문 영역이 없습니다. 손끝 영역을 확인해 주세요.")
        }
        if (response.status != "succeeded") {
            throw IOException("서버가 보호 처리를 완료하지 못했습니다.")
        }
        if (response.resultKind !in setOf("mock", "real")) {
            throw IOException("알 수 없는 처리 결과 형식입니다.")
        }
        if (response.resultKind == "real") {
            if (response.imageBase64.isNullOrBlank()) {
                throw IOException("서버의 처리 이미지가 없습니다. 결과를 저장할 수 없습니다.")
            }
            if (response.mimeType !in setOf("image/png", "image/jpeg")) {
                throw IOException("지원하지 않는 처리 이미지 형식입니다.")
            }
        }
    }
}
