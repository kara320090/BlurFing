package com.blurfing.app.experimental

import android.graphics.BitmapFactory
import android.graphics.ColorSpace
import android.net.Uri
import android.content.ContentValues
import android.os.Build
import android.provider.MediaStore
import androidx.lifecycle.ViewModelStore
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** Optional local-only fixture inputs are adb-staged at runtime. No photo/weight is bundled in APKs. */
@RunWith(AndroidJUnit4::class)
class ExperimentalWireInstrumentedTest {
    private val instrumentation get()=InstrumentationRegistry.getInstrumentation()
    private val context get()=instrumentation.targetContext
    private val arguments get()=InstrumentationRegistry.getArguments()
    private fun input(): Pair<File,String> {
        val name=arguments.getString("private_input");val hash=arguments.getString("expected_rgb_sha256")
        assumeTrue(name!=null && hash!=null)
        val root=context.filesDir.canonicalFile;val file=File(root,name!!).canonicalFile
        require(file.path.startsWith(root.path+File.separator) && file.isFile && file.length() in 1..ExperimentalPhotoMemory.MAX_PNG_BYTES)
        return file to hash!!
    }
    private fun readSource(file: File,expectedRgb: String): ExperimentalPhotoUpload {
        val source=ExperimentalPhotoUpload.fromCanonicalPng(file.readBytes())
        assertEquals(expectedRgb,source.rgbSha256);source.verify();return source
    }
    private fun saveTarget(fallback: File): Uri = if(Build.VERSION.SDK_INT>=29) {
        context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME,"BlurFing-instrumented-private.png")
            put(MediaStore.Images.Media.MIME_TYPE,"image/png")
            put(MediaStore.Images.Media.IS_PENDING,1)
        }) ?: error("provider could not create a private pending image")
    } else Uri.fromFile(fallback)
    private fun copyAndVerifyProvider(uri: Uri,file: File,expected: ByteArray) {
        try {
            context.contentResolver.openInputStream(uri)!!.use { input -> file.outputStream().use { output -> input.copyTo(output) } }
            assertEquals(ExperimentalPngCodec.hash(expected),ExperimentalPngCodec.hash(file.readBytes()))
        } finally { if(uri.scheme=="content")context.contentResolver.delete(uri,null,null) }
    }
    @Test fun realInputEncodingIsRgbLosslessAndBelow15MiBWithoutDownscale() {
        // This is the general photo import boundary, which may contain a P3/ICC profile.
        // The expected raw-P3 fixture SHA is deliberately not compared with decoded sRGB pixels.
        val (file,rawReference)=input();val bytes=file.readBytes()
        val bounds=BitmapFactory.Options().apply { inJustDecodeBounds=true;inScaled=false }
        BitmapFactory.decodeByteArray(bytes,0,bytes.size,bounds)
        ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.importPhoto(bounds.outWidth,bounds.outHeight,bytes.size))
        val options=BitmapFactory.Options().apply { inScaled=false;inPreferredConfig=android.graphics.Bitmap.Config.ARGB_8888;inPreferredColorSpace=ColorSpace.get(ColorSpace.Named.SRGB) }
        val raw=BitmapFactory.decodeByteArray(bytes,0,bytes.size,options)!!
        val decodedSrgb=bitmapRgbHash(raw)
        val encoded=ExperimentalPhotoUpload.fromUpright(raw)
        try {
            // Persist diagnostics before assertions so a failed conversion/size test remains inspectable.
            File(context.filesDir,"android-encoded-upload.private.png").writeBytes(encoded.png)
            File(context.filesDir,"android-encoded-upload.private.json").writeText("""{"width":${encoded.width},"height":${encoded.height},"PNG_bytes":${encoded.png.size},"input_bytes_sha256":"${ExperimentalPngCodec.hash(bytes)}","pre_normalization_raw_RGB_sha256_reference":"$rawReference","BitmapFactory_decoded_sRGB_sha256":"$decodedSrgb","RGB_sha256":"${encoded.rgbSha256}","PNG_sha256":"${encoded.sourceSha256}","max_heap":${Runtime.getRuntime().maxMemory()},"canonical_color_contract":"normalized_sRGB8_no_color_chunks","lossless_from_decoded_sRGB":${decodedSrgb==encoded.rgbSha256},"downscale":false}""")
            assertEquals(decodedSrgb,encoded.rgbSha256);assertEquals(raw.width,encoded.width);assertEquals(raw.height,encoded.height)
            assertTrue(encoded.png.size<=ExperimentalPhotoMemory.MAX_PNG_BYTES);encoded.verify()
        } finally { encoded.preview.recycle();raw.recycle() }
    }
    @Test fun actualHttpFixtureDecodesValidatesAndSavesExactPngReadback()=runBlocking {
        val responseName=arguments.getString("private_response");assumeTrue(responseName!=null)
        val (file,hash)=input();val source=readSource(file,hash)
        val responseFile=File(context.filesDir,responseName!!).canonicalFile
        require(responseFile.path.startsWith(context.filesDir.canonicalPath+File.separator) && responseFile.length() in 1..ExperimentalPhotoRepository.MAX_RESPONSE_BYTES)
        ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.responseRead(source.width,source.height,source.png.size,responseFile.length()))
        val text=responseFile.readText();ExperimentalJsonGuard.verify(text);val dto=Json.decodeFromString<ExperimentalPhotoResponse>(text)
        val engine=ExperimentalPhotoEngine.fromId(dto.photoEngine)
        val result=ExperimentalPhotoDecoder.decode(dto,source,engine,dto.requestId)
        val saveFile=File(context.filesDir,"android-saved-return.private.png")
        val service=object: ExperimentalPhotoService {
            override fun cancel(requestId: String)=Unit
            override suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto =
                ValidatedExperimentalPhoto(requestId,engine,result.returned,result.png,result.accepted,result.rejected,result.presentation,
                    result.candidateComponents,result.transformedComponents,result.rejectedComponents,result.changedPixels,result.regions,result.preview,result.overlayPreview)
        }
        val store=ViewModelStore()
        val vm=ExperimentalPhotoViewModel({service},{_,_->source})
        try {
            withContext(Dispatchers.Main) { store.put("fixture",vm);vm.setEngine(engine);vm.select(context,Uri.fromFile(file)) }
            withTimeout(10000) { vm.state.first { it.source!=null && !it.importing } }
            withContext(Dispatchers.Main) { vm.start() }
            withTimeout(10000) { vm.state.first { it.result!=null && !it.busy } }
            if(result.changedPixels>0) {
                val uri=saveTarget(saveFile)
                withContext(Dispatchers.Main) { val ticket=vm.prepareSave();assertNotNull(ticket);vm.finishSave(context,uri,ticket) }
                val saved=withTimeout(20000) { vm.state.first { !it.saving } }
                assertTrue(saved.message!!.contains("저장했습니다"));copyAndVerifyProvider(uri,saveFile,result.png)
            } else assertNull(withContext(Dispatchers.Main) { vm.prepareSave() })
            File(context.filesDir,"android-wire-validation.private.json").writeText("""{"engine":"${engine.id}","status":"${dto.status}","candidate_components":${result.candidateComponents},"transformed_components":${result.transformedComponents},"rejected_components":${result.rejectedComponents},"changed_RGB_pixels":${result.changedPixels},"source_RGB_sha256":"$hash","returned_RGB_sha256":"${dto.returnedRgbSha256}","source_bytes_sha256":"${source.sourceSha256}","saved_PNG_sha256":"${ExperimentalPngCodec.hash(result.png)}","max_heap":${Runtime.getRuntime().maxMemory()},"actual_full_resolution_validation":true,"readback_exact":${result.changedPixels>0},"privacy_validated":false}""")
        } finally { withContext(Dispatchers.Main) { store.clear() } }
    }
    @Test fun optionalRealRepositoryHttpAiAndProviderSave()=runBlocking {
        val url=arguments.getString("real_backend_url");assumeTrue(url!=null)
        val (file,hash)=input();val source=readSource(file,hash)
        val engine=ExperimentalPhotoEngine.fromId(arguments.getString("photo_engine") ?: "pose_v14")
        val repo=ExperimentalPhotoRepository(url!!,allowLocalHttp=true,responseObserver={
            File(context.filesDir,"android-http-response.private.json").writeText(it)
        })
        val store=ViewModelStore();val vm=ExperimentalPhotoViewModel({repo},{_,_->source})
        val started=android.os.SystemClock.elapsedRealtime()
        try {
            withContext(Dispatchers.Main) { store.put("actual-http",vm);vm.setEngine(engine);vm.select(context,Uri.fromFile(file)) }
            withTimeout(10000) { vm.state.first { it.source!=null && !it.importing } }
            withContext(Dispatchers.Main) { vm.start() }
            val final=withTimeout(750000) { vm.state.first { !it.busy } }
            assertNull(final.message);val result=final.result!!
            val saveFile=File(context.filesDir,"android-actual-http-return.private.png")
            if(result.changedPixels>0) {
                val uri=saveTarget(saveFile)
                withContext(Dispatchers.Main) { val ticket=vm.prepareSave();assertNotNull(ticket);vm.finishSave(context,uri,ticket) }
                val saved=withTimeout(20000) { vm.state.first { !it.saving } }
                assertTrue(saved.message!!.contains("저장했습니다"));copyAndVerifyProvider(uri,saveFile,result.png)
            } else assertNull(withContext(Dispatchers.Main) { vm.prepareSave() })
            File(context.filesDir,"android-actual-http-validation.private.json").writeText("""{"request_id":"${result.requestId}","engine":"${engine.id}","source_RGB_sha256":"$hash","source_bytes_sha256":"${source.sourceSha256}","returned_RGB_sha256":"${bitmapRgbHash(result.returned)}","candidate_components":${result.candidateComponents},"transformed_components":${result.transformedComponents},"rejected_components":${result.rejectedComponents},"changed_RGB_pixels":${result.changedPixels},"saved_PNG_sha256":"${ExperimentalPngCodec.hash(result.png)}","max_heap":${Runtime.getRuntime().maxMemory()},"elapsed_ms":${android.os.SystemClock.elapsedRealtime()-started},"actual_full_resolution_validation":true,"actual_Repository_HTTP":true,"readback_exact":${result.changedPixels>0},"privacy_validated":false}""")
        } finally { withContext(Dispatchers.Main) { store.clear() } }
    }
}
