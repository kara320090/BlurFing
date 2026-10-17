package com.blurfing.app.experimental

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ColorSpace
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import com.blurfing.app.utils.ExifNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import kotlin.coroutines.coroutineContext
import kotlin.math.roundToInt

/** The preview is for display only. Full-resolution RGB and exact upload bytes are retained. */
class ExperimentalPhotoUpload internal constructor(
    internal val png: ByteArray, val width: Int, val height: Int, val sourceSha256: String,
    val rgbSha256: String, val preview: Bitmap
) {
    fun verify(checkActive: ()->Unit = {}) {
        require(ExperimentalPngCodec.hash(png)==sourceSha256)
        val header=ExperimentalPngCodec.parse(png,2)
        require(header.width==width && header.height==height)
        val digest=MessageDigest.getInstance("SHA-256")
        ExperimentalPngCodec.rows(header,checkActive) { _,row -> digest.update(row) }
        require(ExperimentalPngCodec.hex(digest.digest())==rgbSha256)
    }
    companion object {
        suspend fun load(context: Context, uri: Uri): ExperimentalPhotoUpload = withContext(Dispatchers.IO) {
            val contextJob=coroutineContext
            val active={ contextJob.ensureActive() }
            val input=context.contentResolver.openInputStream(uri)?.use { stream ->
                val output=ByteArrayOutputStream();val buffer=ByteArray(8192)
                while(true) { active();val n=stream.read(buffer);if(n<0)break
                    require(output.size().toLong()+n<=ExperimentalPhotoMemory.MAX_PNG_BYTES) { "사진 파일이 15MiB를 초과합니다." }
                    output.write(buffer,0,n)
                };output.toByteArray()
            } ?: throw ExperimentalPhotoException("사진을 열 수 없습니다.")
            val bounds=BitmapFactory.Options().apply { inJustDecodeBounds=true;inScaled=false }
            BitmapFactory.decodeByteArray(input,0,input.size,bounds)
            ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.importPhoto(bounds.outWidth,bounds.outHeight,input.size))
            active()
            val orientation=input.inputStream().use { ExifInterface(it).getAttributeInt(ExifInterface.TAG_ORIENTATION,1) }
            require(orientation in 1..8) { "사진 방향 정보를 확인할 수 없습니다." }
            val options=BitmapFactory.Options().apply { inScaled=false;inPreferredConfig=Bitmap.Config.ARGB_8888
                inPreferredColorSpace=ColorSpace.get(ColorSpace.Named.SRGB) }
            val raw=BitmapFactory.decodeByteArray(input,0,input.size,options)
                ?: throw ExperimentalPhotoException("사진이 손상되었거나 지원하지 않는 형식입니다.")
            val upright=try { ExifNormalizer.normalize(raw,orientation) } catch(e: Throwable) { raw.recycle();throw e }
            if(upright!==raw)raw.recycle()
            try { active();fromUpright(upright,active) } finally { upright.recycle() }
        }
        fun fromUpright(source: Bitmap,checkActive: ()->Unit = {},checkMemory: Boolean=true): ExperimentalPhotoUpload {
            if(checkMemory) {
                ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.upload(source.width,source.height))
            }
            val pixels=IntArray(source.width)
            val encoded=ExperimentalPngCodec.encodeRgb(source.width,source.height,checkActive) { y,row ->
                source.getPixels(pixels,0,source.width,0,y,source.width,1)
                pixels.forEachIndexed { x,c ->
                    val a=c ushr 24 and 255
                    fun channel(shift: Int)=(((c ushr shift and 255)*a+255*(255-a)+127)/255)
                    val r=channel(16);val g=channel(8);val b=channel(0)
                    row[3*x]=r.toByte();row[3*x+1]=g.toByte();row[3*x+2]=b.toByte()
                }
            }
            val scaled=preview(source)
            val small=scaled.copy(Bitmap.Config.ARGB_8888,true)
            if(scaled!==source)scaled.recycle()
            val smallRow=IntArray(small.width)
            repeat(small.height) { y -> checkActive();small.getPixels(smallRow,0,small.width,0,y,small.width,1)
                smallRow.forEachIndexed { x,c -> val a=c ushr 24 and 255
                    fun channel(shift: Int)=(((c ushr shift and 255)*a+255*(255-a)+127)/255)
                    smallRow[x]=0xff000000.toInt() or (channel(16) shl 16) or (channel(8) shl 8) or channel(0)
                };small.setPixels(smallRow,0,small.width,0,y,small.width,1)
            };small.setHasAlpha(false)
            return ExperimentalPhotoUpload(encoded.png,source.width,source.height,ExperimentalPngCodec.hash(encoded.png),encoded.rgbSha256,small)
        }
        /** Only a canonical wire PNG; validates raw pixels while retaining a bounded preview. */
        fun fromCanonicalPng(bytes: ByteArray,checkActive: ()->Unit = {},checkMemory: Boolean=true): ExperimentalPhotoUpload {
            val header=ExperimentalPngCodec.parse(bytes,2)
            if(checkMemory)ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.canonical(header.width,header.height,bytes.size))
            val digest=MessageDigest.getInstance("SHA-256")
            ExperimentalPngCodec.rows(header,checkActive) { _,row -> digest.update(row) }
            var sample=1;while(maxOf(header.width,header.height)/sample>1024)sample*=2
            val options=BitmapFactory.Options().apply { inScaled=false;inSampleSize=sample;inPreferredConfig=Bitmap.Config.ARGB_8888;inPreferredColorSpace=ColorSpace.get(ColorSpace.Named.SRGB) }
            val small=BitmapFactory.decodeByteArray(bytes,0,bytes.size,options) ?: throw ExperimentalPhotoException("PNG 미리보기를 만들 수 없습니다.")
            return ExperimentalPhotoUpload(bytes,header.width,header.height,ExperimentalPngCodec.hash(bytes),ExperimentalPngCodec.hex(digest.digest()),small)
        }
    }
}

internal fun preview(bitmap: Bitmap): Bitmap {
    if(maxOf(bitmap.width,bitmap.height)<=1024)return bitmap
    val scale=minOf(1.0,1024.0/maxOf(bitmap.width,bitmap.height))
    // A separate bounded preview never replaces the validated/uploaded full raster.
    return Bitmap.createScaledBitmap(bitmap,maxOf(1,(bitmap.width*scale).roundToInt()),maxOf(1,(bitmap.height*scale).roundToInt()),true)
}

internal fun bitmapRgbHash(bitmap: Bitmap,checkActive: ()->Unit = {}): String {
    val digest=MessageDigest.getInstance("SHA-256");val pixels=IntArray(bitmap.width);val row=ByteArray(3*bitmap.width)
    repeat(bitmap.height) { y ->
        checkActive();bitmap.getPixels(pixels,0,bitmap.width,0,y,bitmap.width,1)
        pixels.forEachIndexed { x,c -> require(c ushr 24==255);row[3*x]=(c ushr 16).toByte();row[3*x+1]=(c ushr 8).toByte();row[3*x+2]=c.toByte() }
        digest.update(row)
    };return ExperimentalPngCodec.hex(digest.digest())
}
