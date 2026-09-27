package com.blurfing.app.utils

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.IOException
import kotlin.coroutines.coroutineContext

/** Known input errors are safe to display; provider paths and exception details remain in the cause. */
class PhotoImportException(message: String, cause: Throwable? = null) : IOException(message, cause)

/** Read one bounded snapshot so pixels, dimensions and EXIF belong to the same selected photo. */
object SelectedImageLoader {
    internal const val MAX_IMAGE_BYTES = 15 * 1024 * 1024
    internal const val MAX_IMAGE_PIXELS = 20_000_000L

    suspend fun load(context: Context, uri: Uri): Bitmap = withContext(Dispatchers.IO) {
        try {
            val bytes = context.contentResolver.openInputStream(uri)?.use { stream ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                while (true) {
                    coroutineContext.ensureActive()
                    val count = stream.read(buffer)
                    if (count == -1) break
                    if (output.size() + count > MAX_IMAGE_BYTES) {
                        throw PhotoImportException("사진 파일이 15MB를 초과합니다. 더 작은 파일을 선택해 주세요.")
                    }
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            } ?: throw PhotoImportException("사진 파일을 열 수 없습니다. 사진을 다시 선택해 주세요.")

            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            validateDimensions(bounds.outWidth, bounds.outHeight)
            coroutineContext.ensureActive()
            val raw = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                ?: throw PhotoImportException("사진이 손상되었거나 지원하지 않는 형식입니다.")
            val normalized = try {
                val orientation = try {
                    bytes.inputStream().use { input ->
                        ExifInterface(input).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
                    }
                } catch (_: IOException) {
                    ExifInterface.ORIENTATION_NORMAL
                }
                ExifNormalizer.normalize(raw, orientation)
            } catch (e: Exception) {
                raw.recycle()
                throw e
            }
            if (normalized !== raw) raw.recycle()
            try {
                coroutineContext.ensureActive()
            } catch (e: CancellationException) {
                normalized.recycle()
                throw e
            }
            normalized
        } catch (e: CancellationException) {
            throw e
        } catch (e: PhotoImportException) {
            throw e
        } catch (e: Exception) {
            throw PhotoImportException("사진을 읽을 수 없습니다. 접근 권한을 확인하거나 다른 사진을 선택해 주세요.", e)
        }
    }

    internal fun validateDimensions(width: Int, height: Int) {
        if (width <= 0 || height <= 0) {
            throw PhotoImportException("사진이 손상되었거나 지원하지 않는 형식입니다.")
        }
        if (width.toLong() * height.toLong() > MAX_IMAGE_PIXELS) {
            throw PhotoImportException("사진이 2,000만 화소를 초과합니다. 해상도가 더 작은 사진을 선택해 주세요.")
        }
    }
}
