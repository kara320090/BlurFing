package com.blurfing.app.utils

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import com.blurfing.app.model.ProtectionResponse
import java.io.IOException
import java.util.Base64

/** 서버 결과는 그대로 표시한다. 로컬 프리뷰는 명시적인 Mock 결과에만 적용한다. */
object ProtectedImageDecoder {
    private const val MAX_IMAGE_BYTES = 15 * 1024 * 1024
    private const val MAX_ENCODED_CHARS = ((MAX_IMAGE_BYTES + 2) / 3) * 4

    fun decode(response: ProtectionResponse, original: Bitmap, strength: Float): Bitmap {
        if (response.resultKind == "mock") {
            if (response.appliedRegions.isEmpty()) {
                throw IOException("처리할 영역이 없습니다. 손끝 영역을 추가해 주세요.")
            }
            return LocalBlurProcessor.applyBlur(original, response.appliedRegions, strength)
        }
        if (response.resultKind != "real") throw IOException("알 수 없는 처리 결과입니다.")
        val encoded = response.imageBase64
            ?: throw IOException("서버의 처리 이미지가 없습니다.")
        if (encoded.length > MAX_ENCODED_CHARS) throw IOException("처리 이미지가 15MB를 초과합니다.")
        val bytes = try {
            Base64.getDecoder().decode(encoded)
        } catch (e: IllegalArgumentException) {
            throw IOException("서버의 이미지 데이터를 읽을 수 없습니다.", e)
        }
        if (bytes.size > MAX_IMAGE_BYTES) throw IOException("처리 이미지가 15MB를 초과합니다.")

        // 큰 이미지를 할당하기 전에 방향·해상도·실제 파일 형식을 확인한다.
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        if (bounds.outWidth != original.width || bounds.outHeight != original.height) {
            throw IOException("처리 이미지의 크기가 원본과 다릅니다. 서버의 출력 규격을 확인해 주세요.")
        }
        if (bounds.outMimeType !in setOf("image/png", "image/jpeg") ||
            bounds.outMimeType != response.mimeType) {
            throw IOException("처리 이미지의 실제 형식과 서버 응답이 다릅니다.")
        }
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            ?: throw IOException("서버의 처리 이미지를 열 수 없습니다.")
    }
}
