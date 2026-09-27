package com.blurfing.app.utils

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import java.io.InputStream

/**
 * EXIF Orientation을 비트맵 픽셀에 직접 적용하여 회전각을 정규화하는 유틸리티.
 * contracts/protection-api.md 준수:
 * "앱은 EXIF 방향을 픽셀에 반영하고 방향 정보를 정규화한 사진을 보낸다. 영역 좌표는 이 정규화된 원본의 좌상단 기준이다."
 */
object ExifNormalizer {

    /**
     * URI로부터 EXIF 회전 정보를 읽어 픽셀 자체를 정규화한 비트맵을 반환합니다.
     */
    fun getNormalizedBitmap(context: Context, uri: Uri, sourceBitmap: Bitmap): Bitmap {
        return normalize(sourceBitmap, getExifOrientation(context, uri))
    }

    /** Apply orientation already read from the same bytes as the decoded pixels. */
    fun normalize(sourceBitmap: Bitmap, orientation: Int): Bitmap {
        if (orientation == ExifInterface.ORIENTATION_NORMAL || orientation == ExifInterface.ORIENTATION_UNDEFINED) {
            return sourceBitmap
        }

        val matrix = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> matrix.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> matrix.postScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> {
                matrix.postRotate(90f)
                matrix.postScale(-1f, 1f)
            }
            ExifInterface.ORIENTATION_TRANSVERSE -> {
                matrix.postRotate(270f)
                matrix.postScale(-1f, 1f)
            }
            else -> return sourceBitmap
        }

        return Bitmap.createBitmap(
            sourceBitmap,
            0,
            0,
            sourceBitmap.width,
            sourceBitmap.height,
            matrix,
            true
        )
    }

    private fun getExifOrientation(context: Context, uri: Uri): Int {
        return try {
            val inputStream: InputStream? = context.contentResolver.openInputStream(uri)
            inputStream?.use { stream ->
                val exifInterface = ExifInterface(stream)
                exifInterface.getAttributeInt(
                    ExifInterface.TAG_ORIENTATION,
                    ExifInterface.ORIENTATION_NORMAL
                )
            } ?: ExifInterface.ORIENTATION_NORMAL
        } catch (e: Exception) {
            ExifInterface.ORIENTATION_NORMAL
        }
    }
}
