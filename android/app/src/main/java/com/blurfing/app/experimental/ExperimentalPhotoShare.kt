package com.blurfing.app.experimental

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID
import kotlin.coroutines.coroutineContext

data class ExperimentalPhotoShare(val uri: Uri, val requestId: String)

internal object ExperimentalPhotoShareFiles {
    suspend fun prepare(context: Context, result: ValidatedExperimentalPhoto,
        uriFactory: (File)->Uri = { FileProvider.getUriForFile(context,"${context.packageName}.protected-share",it) }
    ): ExperimentalPhotoShare {
        var createdFile: File?=null
        return try { withContext(Dispatchers.IO) {
        require(result.presentation.canSaveChangedCopy)
        val directory=File(context.cacheDir,"protected-shares").apply { check(mkdirs() || isDirectory) }
        directory.listFiles()?.filter { it.name.startsWith("experimental-") && it.isFile &&
            System.currentTimeMillis()-it.lastModified()>24L*60*60*1000 }?.forEach { it.delete() }
        val file=File(directory,"experimental-${UUID.randomUUID()}.png")
        createdFile=file
        try {
            file.outputStream().use { output ->
                var at=0
                while(at<result.png.size) { coroutineContext.ensureActive();val n=minOf(8192,result.png.size-at)
                    output.write(result.png,at,n);at+=n }
            }
            coroutineContext.ensureActive()
            require(file.length()==result.png.size.toLong() && file.inputStream().use {
                val digest=java.security.MessageDigest.getInstance("SHA-256");val buffer=ByteArray(8192)
                while(true) { coroutineContext.ensureActive();val n=it.read(buffer);if(n<0)break;digest.update(buffer,0,n) }
                ExperimentalPngCodec.hex(digest.digest())
            }==ExperimentalPngCodec.hash(result.png))
            ExperimentalPhotoShare(uriFactory(file),result.requestId)
        } catch(e: Throwable) { file.delete();throw e }
        } } catch(e: Throwable) { createdFile?.delete();throw e }
    }
    fun intent(share: ExperimentalPhotoShare)=Intent(Intent.ACTION_SEND).apply {
        type="image/png";putExtra(Intent.EXTRA_STREAM,share.uri)
        putExtra(Intent.EXTRA_TEXT,"BlurFing 실험 처리본: 미검출·거절 영역에 원본 지문이 남을 수 있습니다. 전체 보호는 검증되지 않았습니다.")
        clipData=ClipData.newRawUri("BlurFing 실험 처리 PNG",share.uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    fun discard(context: Context, share: ExperimentalPhotoShare) {
        val uri=share.uri
        if(uri.scheme!="content" || uri.authority!="${context.packageName}.protected-share" || uri.query!=null || uri.fragment!=null)return
        val segments=uri.pathSegments
        if(segments.size!=2 || segments[0]!="processed" || !segments[1].matches(Regex("experimental-[a-f0-9-]{36}\\.png")))return
        val root=File(context.cacheDir,"protected-shares").canonicalFile
        val file=File(root,segments[1]).canonicalFile
        if(file.parentFile==root)file.delete()
    }
}
