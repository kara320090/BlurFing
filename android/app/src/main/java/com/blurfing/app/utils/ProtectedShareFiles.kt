package com.blurfing.app.utils

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.core.content.FileProvider
import com.blurfing.app.model.ProcessingSettings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID
import kotlin.coroutines.coroutineContext

class ProtectedShareProvider : FileProvider()

data class ProtectedShare(val uri: Uri, val mimeType: String, val isMock: Boolean)

object ProtectedShareFiles {
    private const val RETENTION_MS = 24 * 60 * 60 * 1000L

    /** Re-encode the processed bitmap only; never include the source URI or metadata. */
    suspend fun prepare(context: Context, bitmap: Bitmap, settings: ProcessingSettings, isMock: Boolean,
        uriFactory: (File) -> Uri = { FileProvider.getUriForFile(context, "${context.packageName}.protected-share", it) }
    ): ProtectedShare = withContext(Dispatchers.IO) {
        val directory = File(context.cacheDir, "protected-shares").apply { check(mkdirs() || isDirectory) }
        val expiry = System.currentTimeMillis() - RETENTION_MS
        directory.listFiles()?.filter { it.isFile && it.lastModified() < expiry }?.forEach { it.delete() }
        val format = settings.exportFormat
        val file = File(directory, "copy-${UUID.randomUUID()}.${format.extension}")
        try {
            file.outputStream().use { stream ->
                check(bitmap.compress(format.compression, settings.jpegQuality.coerceIn(80, 100), stream))
            }
            coroutineContext.ensureActive()
            ProtectedShare(uriFactory(file), format.mimeType, isMock)
        } catch (error: Throwable) {
            file.delete()
            throw error
        }
    }

    fun intent(share: ProtectedShare): Intent = Intent(Intent.ACTION_SEND).apply {
        type = share.mimeType
        putExtra(Intent.EXTRA_STREAM, share.uri)
        clipData = ClipData.newRawUri(if (share.isMock) "BlurFing Mock 프리뷰" else "BlurFing 처리 사본", share.uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
}
