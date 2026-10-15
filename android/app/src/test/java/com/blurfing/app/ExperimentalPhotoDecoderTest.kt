package com.blurfing.app.experimental

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.security.MessageDigest
import java.util.Base64

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ExperimentalPhotoDecoderTest {
    private fun fixture(name: String)=javaClass.getResourceAsStream("/experimental-png/$name")!!.use { it.readBytes() }
    internal fun source(): ExperimentalPhotoUpload {
        val bytes=fixture("RGB-pillow.png");val bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.size)
        return ExperimentalPhotoUpload.fromUpright(bitmap,checkMemory=false).also { bitmap.recycle() }
    }
    internal fun response(source: ExperimentalPhotoUpload): ExperimentalPhotoResponse = Json.decodeFromString<ExperimentalPhotoResponse>(fixture("response-pillow.json").toString(Charsets.UTF_8)).copy(sourceSha256=source.sourceSha256)
    private fun decode(r: ExperimentalPhotoResponse,s: ExperimentalPhotoUpload)=ExperimentalPhotoDecoder.decode(r,s,ExperimentalPhotoEngine.NATIVE,"synthetic",checkMemory=false)
    private fun rejects(action: ()->Unit) { try { action();fail("Invalid V2 result accepted") } catch(_: IllegalArgumentException) { } }

    @Test fun independentPillowResponseValidatesRealPixelsMasksHashesAndPartialWarning() {
        val s=source();val result=decode(response(s),s)
        assertEquals(1L,result.changedPixels);assertTrue(result.accepted[2*9+1]);assertFalse(result.rejected[2*9+1])
        assertTrue(result.rejected[3*9+5]);assertEquals(s.width,result.returned.width)
        assertTrue(result.presentation.detail.contains("원본 지문이 남아"));assertFalse(result.presentation.mayClaimCompleteProtection)
        assertEquals(s.preview.getPixel(5,3),result.returned.getPixel(5,3))
    }
    @Test fun sourcePixelsAreOpaqueWhiteCompositedAndEncodedAsRgbNotRgba() {
        val bitmap=Bitmap.createBitmap(2,1,Bitmap.Config.ARGB_8888);bitmap.setPixel(0,0,0x00000000);bitmap.setPixel(1,0,0xff123456.toInt())
        val s=ExperimentalPhotoUpload.fromUpright(bitmap,checkMemory=false)
        assertEquals(0xffffffff.toInt(),s.preview.getPixel(0,0));assertEquals(0xff123456.toInt(),s.preview.getPixel(1,0))
        assertEquals(2,ExperimentalPngCodec.parse(s.png,2).colorType);s.verify()
    }
    @Test fun staleSourceMethodEngineAndDimensionsCannotBeRelabeled() {
        val s=source();val r=response(s)
        for(v in listOf(r.copy(requestId="old"),r.copy(sourceSha256="0".repeat(64)),r.copy(sourceRgbSha256="0".repeat(64)),
            r.copy(photoEngine="pose_v14"),r.copy(method="gaussian_blur"),r.copy(imageWidth=7),r.copy(sourceExifOrientation=6),r.copy(coordinateSystem="upright_pixels")))rejects { decode(v,s) }
        rejects { ExperimentalPhotoEngine.fromId("unknown") }
    }
    @Test fun approvalMissingFlagUnknownFieldAndFakeStatusReject() {
        val s=source();val r=response(s)
        for(v in listOf(r.copy(privacyValidated=true),r.copy(productionApproved=true),r.copy(completePhotoProtectionVerified=true),r.copy(independentFinalTest=true),r.copy(status="success"),r.copy(transformedComponents=0),r.copy(warnings=emptyList()),r.copy(boundsAreNotFilledPermission=false)))rejects { decode(v,s) }
        val wire=fixture("response-pillow.json").toString(Charsets.UTF_8)
        rejects { Json.decodeFromString<ExperimentalPhotoResponse>(wire.replace("\"privacy_validated\": false,", "")) }
        rejects { Json.decodeFromString<ExperimentalPhotoResponse>(wire.replace("\"evaluation\": null", "\"evaluation\": null, \"unknown\": 1")) }
    }
    @Test fun acceptedRejectedOverlapAndNonbinaryOrWrongMaskHashesReject() {
        val s=source();val r=response(s)
        rejects { decode(r.copy(rejectedPermissionMask=r.acceptedPermissionMask),s) }
        rejects { decode(r.copy(acceptedPermissionMask=r.acceptedPermissionMask.copy(pixels=11)),s) }
        rejects { decode(r.copy(acceptedPermissionMask=r.acceptedPermissionMask.copy(pngSha256="0".repeat(64))),s) }
        rejects { decode(r.copy(acceptedPermissionMask=r.acceptedPermissionMask.copy(booleanPixelSha256="0".repeat(64))),s) }
        val bytes=fixture("RGB-filter0.png")
        rejects { decode(r.copy(acceptedPermissionMask=r.acceptedPermissionMask.copy(imageBase64=Base64.getEncoder().encodeToString(bytes),pngSha256=ExperimentalPngCodec.hash(bytes))),s) }
        val nonbinary=fixture("L-nonbinary.png")
        rejects { decode(r.copy(acceptedPermissionMask=r.acceptedPermissionMask.copy(imageBase64=Base64.getEncoder().encodeToString(nonbinary),pngSha256=ExperimentalPngCodec.hash(nonbinary))),s) }
    }
    @Test fun actualChangeOutsideAcceptedCannotPassEvenWithMatchingReturnHashAndCount() {
        val s=source();val r=response(s)
        val encoded=ExperimentalPngCodec.encodeRgb(9,7) { y,row ->
            val pixels=IntArray(9);s.preview.getPixels(pixels,0,9,0,y,9,1)
            repeat(9) { x -> row[3*x]=(pixels[x] ushr 16).toByte();row[3*x+1]=(pixels[x] ushr 8).toByte();row[3*x+2]=pixels[x].toByte() }
            if(y==0)row[0]=(row[0].toInt() xor 128).toByte()
        }
        rejects { decode(r.copy(imageBase64=Base64.getEncoder().encodeToString(encoded.png),returnedRgbSha256=encoded.rgbSha256),s) }
        rejects { decode(r.copy(changedRgbPixels=2),s) }
    }
    @Test fun malformedRegionCountsBoundsAndFabricatedMetadataReject() {
        val s=source();val r=response(s);val a=r.regionDisplayBounds.first()
        for(regions in listOf(emptyList(),listOf(a,a),r.regionDisplayBounds.map { it.copy(maskPixels=1) },
            r.regionDisplayBounds.map { it.copy(x=Double.NaN) },r.regionDisplayBounds.map { it.copy(width=0.1) },
            r.regionDisplayBounds.map { it.copy(boundsAreNotFilledPermission=false) }))rejects { decode(r.copy(regionDisplayBounds=regions),s) }
    }
    @Test fun sourceMutationIsDetectedBeforeAResultCanBeAccepted() {
        val s=source();val r=response(s);s.png[s.png.lastIndex]=(s.png.last().toInt() xor 1).toByte();rejects { decode(r,s) }
    }
    @Test fun smallPreviewAliasNeverRecyclesPublishedCanonicalPixels() {
        val raw=Bitmap.createBitmap(4,3,Bitmap.Config.ARGB_8888).apply { eraseColor(0xff1254a7.toInt()) }
        val s=ExperimentalPhotoUpload.fromUpright(raw,checkMemory=false);raw.recycle()
        assertNotSame(raw,s.preview);assertFalse(s.preview.isRecycled);assertEquals(0xff1254a7.toInt(),s.preview.getPixel(0,0));s.verify()
    }
    @Test fun everyEngineRequiresItsOwnMethodAndBoundaryWarnings() {
        val s=source();val base=response(s)
        for(engine in ExperimentalPhotoEngine.entries) {
            val warning=when(engine) { ExperimentalPhotoEngine.NATIVE->emptyList();ExperimentalPhotoEngine.DISTAL->listOf("GEOMETRY_BOUNDARIES_REQUIRE_REVIEW_ACCURACY_REGRESSION_OBSERVED")
                ExperimentalPhotoEngine.POSE->listOf("POSE_GEOMETRY_BOUNDARIES_REQUIRE_REVIEW") }
            val dto=base.copy(photoEngine=engine.id,method=engine.method,warnings=base.warnings+warning)
            assertEquals(engine,ExperimentalPhotoDecoder.decode(dto,s,engine,"synthetic",checkMemory=false).engine)
            if(engine!=ExperimentalPhotoEngine.NATIVE)rejects { ExperimentalPhotoDecoder.decode(dto.copy(warnings=base.warnings),s,engine,"synthetic",checkMemory=false) }
        }
    }
}
