package com.blurfing.app.experimental

import android.graphics.Bitmap
import com.blurfing.app.model.ExperimentalPhotoMetadata
import com.blurfing.app.model.ExperimentalPhotoOutcome
import com.blurfing.app.model.ExperimentalPhotoPresentation
import kotlinx.serialization.json.JsonNull
import java.security.MessageDigest
import kotlin.math.abs
import kotlin.math.round

class ValidatedExperimentalPhoto internal constructor(
    val requestId: String, val engine: ExperimentalPhotoEngine, val returned: Bitmap,
    internal val png: ByteArray, val accepted: CompactPermissionMask, val rejected: CompactPermissionMask,
    val presentation: ExperimentalPhotoPresentation, val candidateComponents: Int,
    val transformedComponents: Int, val rejectedComponents: Int, val changedPixels: Long,
    val regions: List<ExperimentalRegionBounds>, val preview: Bitmap, val overlayPreview: Bitmap,
    internal var recoveryResponse: ExperimentalPhotoResponse? = null
)

/** Validates real returned pixels and full-resolution masks. Boxes are display metadata only. */
object ExperimentalPhotoDecoder {
    private fun metadata(r: ExperimentalPhotoResponse)=ExperimentalPhotoMetadata(r.contractVersion,r.resultKind,r.requestId,
        r.sourceSha256,r.photoEngine,r.coordinateSystem,r.sourceExifOrientation,r.imageWidth,r.imageHeight,r.status,
        r.candidateComponents,r.transformedComponents,r.rejectedComponents,r.changedRgbPixels,
        r.privacyValidated,r.productionApproved,r.completePhotoProtectionVerified,r.independentFinalTest)

    fun decode(r: ExperimentalPhotoResponse,source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,
               requestId: String,checkActive: ()->Unit = {},checkMemory: Boolean=true): ValidatedExperimentalPhoto {
        require(requestId.isNotBlank() && requestId.length<=200)
        source.verify(checkActive)
        val raster=ExperimentalPhotoMemory.dimensions(r.imageWidth,r.imageHeight)
        require(r.imageWidth==source.width && r.imageHeight==source.height)
        require(r.contractVersion=="photo-experimental-v2" && r.resultKind=="experimental")
        require(r.requestId==requestId && r.method==engine.method && r.photoEngine==engine.id)
        require(r.mimeType=="image/png" && r.coordinateSystem=="encoded_original_pixels" && r.sourceExifOrientation==1)
        require(r.sourceSha256==source.sourceSha256 && r.sourceRgbSha256==source.rgbSha256)
        ExperimentalPngCodec.requireHash(r.returnedRgbSha256)
        require(!r.privacyValidated && !r.productionApproved && !r.completePhotoProtectionVerified && !r.independentFinalTest)
        require(r.evaluation==null || r.evaluation==JsonNull)
        require(r.processingMs>=0 && r.boundsAreNotFilledPermission)
        require(r.candidateComponents in 0..256 && r.transformedComponents in 0..256 && r.rejectedComponents in 0..256)
        require(r.transformedComponents+r.rejectedComponents==r.candidateComponents)
        require(r.changedRgbPixels in 0..raster)
        val warnings=setOf("EXPERIMENTAL_UNAPPROVED","UNDETECTED_FINGERPRINTS_POSSIBLE","COUNTS_ARE_PERMISSION_COMPONENTS_NOT_FINGERS")+
            (if(r.rejectedComponents>0)setOf("REJECTED_REGIONS_RETAIN_ORIGINAL_PIXELS") else emptySet())+
            (when(engine) { ExperimentalPhotoEngine.DISTAL->setOf("GEOMETRY_BOUNDARIES_REQUIRE_REVIEW_ACCURACY_REGRESSION_OBSERVED")
                ExperimentalPhotoEngine.POSE->setOf("POSE_GEOMETRY_BOUNDARIES_REQUIRE_REVIEW");else->emptySet() })
        require(r.warnings.size<=32 && r.warnings.toSet()==warnings && r.warnings.size==warnings.size)
        val base64Chars=r.imageBase64.length.toLong()+r.acceptedPermissionMask.imageBase64.length+r.rejectedPermissionMask.imageBase64.length
        val returnedSize=(r.imageBase64.length.toLong()/4*3).coerceAtMost(ExperimentalPhotoMemory.MAX_PNG_BYTES.toLong()).toInt()
        if(checkMemory) ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.decode(source.width,source.height,source.png.size,returnedSize,base64Chars))
        val accepted=mask(r.acceptedPermissionMask,source.width,source.height,checkActive)
        val rejected=mask(r.rejectedPermissionMask,source.width,source.height,checkActive)
        var acceptedPixels=0L;var rejectedPixels=0L
        repeat(accepted.size) { i -> if(i%source.width==0)checkActive();require(!(accepted[i] && rejected[i]));if(accepted[i])acceptedPixels++;if(rejected[i])rejectedPixels++ }
        regions(r,acceptedPixels,rejectedPixels,raster)
        val returnedPng=ExperimentalPngCodec.base64(r.imageBase64)
        val header=ExperimentalPngCodec.parse(returnedPng,2)
        require(header.width==source.width && header.height==source.height)
        val returned=Bitmap.createBitmap(source.width,source.height,Bitmap.Config.ARGB_8888).apply { setHasAlpha(false) }
        try {
            val outRow=IntArray(source.width)
            val returnedDigest=MessageDigest.getInstance("SHA-256")
            var changed=0L;var changedOutside=0L
            ExperimentalPngCodec.rowReader(ExperimentalPngCodec.parse(source.png,2),checkActive).use { original ->
            ExperimentalPngCodec.rows(header,checkActive) { y,row ->
                val sourceRow=original.next();returnedDigest.update(row)
                repeat(source.width) { x ->
                    val c=0xff000000.toInt() or ((row[3*x].toInt() and 255) shl 16) or ((row[3*x+1].toInt() and 255) shl 8) or (row[3*x+2].toInt() and 255)
                    outRow[x]=c
                    if(row[3*x]!=sourceRow[3*x] || row[3*x+1]!=sourceRow[3*x+1] || row[3*x+2]!=sourceRow[3*x+2]) { changed++;if(!accepted[y*source.width+x])changedOutside++ }
                };returned.setPixels(outRow,0,source.width,0,y,source.width,1)
            }
            original.finish()
            }
            require(ExperimentalPngCodec.hex(returnedDigest.digest())==r.returnedRgbSha256)
            val presentation=ExperimentalPhotoOutcome.validateAndPresent(metadata(r),requestId,source.sourceSha256,engine.id,
                source.width,source.height,acceptedPixels,rejectedPixels,changed,changedOutside)
            val preview=preview(returned)
            return ValidatedExperimentalPhoto(requestId,engine,returned,returnedPng,accepted,rejected,presentation,r.candidateComponents,
                r.transformedComponents,r.rejectedComponents,changed,r.regionDisplayBounds,preview,overlay(preview,accepted,rejected,checkActive),r)
        } catch(e: Throwable) { returned.recycle();throw e }
    }

    private fun mask(value: ExperimentalPermissionMask,w: Int,h: Int,active: ()->Unit): CompactPermissionMask {
        require(value.encoding=="png_uint8_0_255" && value.pixels in 0..w.toLong()*h)
        ExperimentalPngCodec.requireHash(value.pngSha256);ExperimentalPngCodec.requireHash(value.booleanPixelSha256)
        val bytes=ExperimentalPngCodec.base64(value.imageBase64);require(ExperimentalPngCodec.hash(bytes)==value.pngSha256)
        val header=ExperimentalPngCodec.parse(bytes,0);require(header.width==w && header.height==h)
        val result=CompactPermissionMask(w,h);val digest=MessageDigest.getInstance("SHA-256");val boolRow=ByteArray(w);var count=0L
        ExperimentalPngCodec.rows(header,active) { y,row ->
            repeat(w) { x -> val v=row[x].toInt() and 255;require(v==0 || v==255);boolRow[x]=if(v==0)0 else 1
                if(v==255) { result.set(y*w+x);count++ }
            };digest.update(boolRow)
        }
        require(count==value.pixels && ExperimentalPngCodec.hex(digest.digest())==value.booleanPixelSha256)
        return result
    }

    private fun regions(r: ExperimentalPhotoResponse,a: Long,rejected: Long,raster: Long) {
        val regions=r.regionDisplayBounds;require(regions.size==r.candidateComponents && regions.map { it.regionId }.toSet().size==regions.size)
        var acceptedPixels=0L;var rejectedPixels=0L;var changed=0L;var transformed=0
        regions.forEach { v ->
            require(v.regionId in 1..65535 && v.boundsAreNotFilledPermission && v.maskPixels in 1..raster)
            ExperimentalPngCodec.requireHash(v.permissionBooleanSha256)
            require(listOf(v.x,v.y,v.width,v.height).all { it.isFinite() && it in 0.0..1.0 })
            require(v.width>0 && v.height>0 && v.x+v.width<=1.0+1e-12 && v.y+v.height<=1.0+1e-12)
            // Bounds must describe integral source-coordinate edges; they never create permission pixels.
            listOf(v.x*r.imageWidth,v.y*r.imageHeight,v.width*r.imageWidth,v.height*r.imageHeight).forEach { require(abs(it-round(it))<=1e-6) }
            require(v.maskPixels<=(round(v.width*r.imageWidth)*round(v.height*r.imageHeight)).toLong())
            when(v.status) {
                "transformed" -> { require(v.reasonCode=="TRANSFORMED" && v.changedRgbPixels in 1..v.maskPixels);acceptedPixels+=v.maskPixels;transformed++ }
                "rejected" -> { require(v.reasonCode.matches(Regex("REJECT_[A-Z0-9_]{1,80}")) && v.changedRgbPixels==0L);rejectedPixels+=v.maskPixels }
                else -> throw IllegalArgumentException("알 수 없는 후보 결과입니다.")
            };changed+=v.changedRgbPixels
        }
        require(acceptedPixels==a && rejectedPixels==rejected && changed==r.changedRgbPixels && transformed==r.transformedComponents)
        // Individual region SHA values are metadata. Only union A/R masks are transmitted and independently verified here.
    }

    private fun overlay(base: Bitmap,a: CompactPermissionMask,r: CompactPermissionMask,active: ()->Unit): Bitmap {
        val overlay=base.copy(Bitmap.Config.ARGB_8888,true);val row=IntArray(base.width)
        repeat(base.height) { y -> active();base.getPixels(row,0,base.width,0,y,base.width,1)
            repeat(base.width) { x ->
                val index=minOf((a.height-1).toLong(),y.toLong()*a.height/base.height).toInt()*a.width+minOf((a.width-1).toLong(),x.toLong()*a.width/base.width).toInt()
                val tint=if(a[index])0x0030cc60 else if(r[index])0x00ffa020 else -1
                if(tint>=0) { val c=row[x];row[x]=0xff000000.toInt() or ((((c ushr 16 and 255)+(tint ushr 16 and 255))/2) shl 16) or
                    ((((c ushr 8 and 255)+(tint ushr 8 and 255))/2) shl 8) or ((c and 255)+(tint and 255))/2 }
            };overlay.setPixels(row,0,base.width,0,y,base.width,1)
        };return overlay
    }
}
