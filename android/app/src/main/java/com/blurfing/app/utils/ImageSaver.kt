package com.blurfing.app.utils

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.OutputStream
import java.text.SimpleDateFormat
import java.util.*

/**
 * 보호된 이미지를 별도 사본 파일로 저장하는 유틸리티 (BF-06).
 * 원본 이미지를 절대 덮어쓰지 않으며, 'Pictures/BlurFing' 디렉터리에 새 파일로 저장합니다.
 */
object ImageSaver {

    suspend fun saveProtectedCopy(
        context: Context,
        bitmap: Bitmap,
        format: Bitmap.CompressFormat = Bitmap.CompressFormat.PNG
    ): Result<Uri> = withContext(Dispatchers.IO) {
        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
        val extension = if (format == Bitmap.CompressFormat.JPEG) "jpg" else "png"
        val mimeType = if (format == Bitmap.CompressFormat.JPEG) "image/jpeg" else "image/png"
        val fileName = "BlurFing_$timestamp.$extension"

        val contentValues = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
            put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.MediaColumns.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/BlurFing")
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
        }

        val resolver = context.contentResolver
        val collectionUri = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        } else {
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        }

        val itemUri = resolver.insert(collectionUri, contentValues)
            ?: return@withContext Result.failure(IllegalStateException("MediaStore 항목을 생성하지 못했습니다."))

        try {
            val outputStream: OutputStream? = resolver.openOutputStream(itemUri)
            requireNotNull(outputStream) { "출력 스트림을 열 수 없습니다: $itemUri" }

            outputStream.use { stream ->
                val success = bitmap.compress(format, 100, stream)
                if (!success) {
                    throw IllegalStateException("비트맵 압축 및 저장에 실패했습니다.")
                }
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                contentValues.clear()
                contentValues.put(MediaStore.MediaColumns.IS_PENDING, 0)
                resolver.update(itemUri, contentValues, null, null)
            }

            Result.success(itemUri)
        } catch (e: Exception) {
            // 저장 실패 시 미완성 MediaStore 항목 정리
            resolver.delete(itemUri, null, null)
            Result.failure(e)
        }
    }
}
