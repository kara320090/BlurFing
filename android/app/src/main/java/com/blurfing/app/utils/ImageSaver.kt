package com.blurfing.app.utils

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.OutputStream
import java.text.SimpleDateFormat
import java.util.*
import kotlin.coroutines.coroutineContext

/**
 * 보호된 이미지를 별도 사본 파일로 저장하는 유틸리티 (BF-06).
 * 원본 이미지를 절대 덮어쓰지 않으며, 'Pictures/BlurFing' 디렉터리에 새 파일로 저장합니다.
 */
object ImageSaver {

    suspend fun saveProtectedCopy(
        context: Context,
        bitmap: Bitmap,
        format: Bitmap.CompressFormat = Bitmap.CompressFormat.PNG,
        jpegQuality: Int = 95
    ): Result<Uri> = withContext(Dispatchers.IO) {
        val resolver = context.contentResolver
        var itemUri: Uri? = null
        try {
            require(format == Bitmap.CompressFormat.PNG || format == Bitmap.CompressFormat.JPEG) {
                "PNG 또는 JPEG 형식으로 저장해 주세요."
            }
            require(jpegQuality in 1..100) { "JPEG 품질을 확인해 주세요." }
            coroutineContext.ensureActive()
            val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
            val extension = if (format == Bitmap.CompressFormat.JPEG) "jpg" else "png"
            val mimeType = if (format == Bitmap.CompressFormat.JPEG) "image/jpeg" else "image/png"
            val fileName = "BlurFing_${timestamp}_${UUID.randomUUID().toString().take(8)}.$extension"

            val contentValues = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    put(MediaStore.MediaColumns.RELATIVE_PATH, "${Environment.DIRECTORY_PICTURES}/BlurFing")
                    put(MediaStore.MediaColumns.IS_PENDING, 1)
                }
            }

            val collectionUri = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            } else {
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI
            }

            val createdUri = resolver.insert(collectionUri, contentValues)
                ?: throw IllegalStateException("MediaStore 항목을 생성하지 못했습니다.")
            itemUri = createdUri

            val outputStream: OutputStream? = resolver.openOutputStream(createdUri)
            requireNotNull(outputStream) { "출력 스트림을 열 수 없습니다." }

            outputStream.use { stream ->
                val success = bitmap.compress(format, if(format==Bitmap.CompressFormat.JPEG) jpegQuality else 100, stream)
                if (!success) {
                    throw IllegalStateException("비트맵 압축 및 저장에 실패했습니다.")
                }
            }

            // 취소된 작업은 완성 파일로 공개하기 전에 미완성 항목을 정리한다.
            coroutineContext.ensureActive()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                contentValues.clear()
                contentValues.put(MediaStore.MediaColumns.IS_PENDING, 0)
                check(resolver.update(createdUri, contentValues, null, null) == 1) {
                    "저장한 사본을 갤러리에 표시하지 못했습니다."
                }
            }

            Result.success(createdUri)
        } catch (e: Exception) {
            // 이 호출이 만든 항목만 정리하고, 정리 실패가 최초 오류를 덮지 않게 한다.
            itemUri?.let { uri ->
                try {
                    check(resolver.delete(uri, null, null) == 1) {
                        "미완성 사본을 정리하지 못했습니다."
                    }
                } catch (cleanupError: Exception) {
                    if (cleanupError !== e) e.addSuppressed(cleanupError)
                }
            }
            if (e is CancellationException) throw e
            Result.failure(e)
        }
    }
}
