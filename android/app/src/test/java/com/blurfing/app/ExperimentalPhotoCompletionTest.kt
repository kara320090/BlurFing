package com.blurfing.app.experimental

import android.content.Intent
import android.net.Uri
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.utils.CameraCaptureFiles
import com.blurfing.app.utils.ComparisonCrop
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ExperimentalPhotoCompletionTest {
    private val context get()=RuntimeEnvironment.getApplication()
    private val store=ViewModelStore()
    private val fixtures=ExperimentalPhotoDecoderTest()
    private val source by lazy { fixtures.source() }
    private val result get()=ExperimentalPhotoDecoder.decode(fixtures.response(source),source,ExperimentalPhotoEngine.NATIVE,"synthetic",checkMemory=false)
    private val ready=ExperimentalServerReadiness("ready","photo-experimental-v2","experimental",listOf("native_v12"),false)
    private var calls=0
    private val service=object: ExperimentalPhotoService {
        override fun cancel(requestId: String)=Unit
        override suspend fun readiness()=ready
        override suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto {
            calls++;return ExperimentalPhotoDecoder.decode(fixtures.response(source).copy(requestId=requestId),source,engine,requestId,checkMemory=false)
        }
    }
    @Before fun setup() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        context.getSharedPreferences("experimental-photo-settings",0).edit().clear().commit()
    }
    @After fun cleanup() { store.clear();Dispatchers.resetMain() }
    private fun vm(state: SavedStateHandle=SavedStateHandle(),api: ExperimentalPhotoService=service,
        load: suspend (android.content.Context,Uri)->ExperimentalPhotoUpload={_,_->source}): ExperimentalPhotoViewModel =
        ExperimentalPhotoViewModel({api},load,state).also { store.put("vm-${store.keys().size}",it) }
    private suspend fun idle(vm: ExperimentalPhotoViewModel) = withTimeout(10000) { vm.state.first { !it.hasActiveWork } }
    private fun copy(state: SavedStateHandle)=SavedStateHandle(state.keys().associateWith { state.get<Any>(it) })

    @Test fun v2AddressAndEnginePersistIndependentlyAndInitializeOnlyOnce() {
        val first=vm();first.initialize(context);first.setAddress("https://example.org/photo");first.setEngine(ExperimentalPhotoEngine.POSE)
        first.initialize(context);assertEquals("https://example.org/photo",first.state.value.serverAddress)
        val second=vm();second.initialize(context)
        assertEquals(first.state.value.serverAddress,second.state.value.serverAddress)
        assertEquals(ExperimentalPhotoEngine.POSE,second.state.value.engine)
        assertFalse(context.getSharedPreferences("processing-settings",0).contains("photo-engine"))
    }
    @Test fun corruptSettingsFallBackWithoutReusingV1() {
        context.getSharedPreferences("experimental-photo-settings",0).edit().putInt("address",123).commit()
        val loaded=ExperimentalPhotoSettings(context).load()
        assertEquals(ExperimentalPhotoEngine.NATIVE,loaded.engine)
        assertEquals(EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT,loaded.address)
    }
    @Test fun unavailableEngineBlocksUploadAndAddressEditClearsReadiness() {
        val model=vm();model.select(context,Uri.parse("content://synthetic/photo"));model.setEngine(ExperimentalPhotoEngine.POSE)
        model.checkServer();assertEquals(ready,model.state.value.readiness)
        model.start();assertEquals(0,calls);assertSame(source,model.state.value.source)
        model.setAddress("https://example.org/new");assertNull(model.state.value.readiness)
    }
    @Test fun cancelledLateReadyResponseCannotOverwriteNewAddress()=runBlocking {
        val gate=CompletableDeferred<Unit>()
        val late=object: ExperimentalPhotoService by service {
            override suspend fun readiness()=withContext(NonCancellable) { gate.await();ready }
        }
        val model=vm(api=late);model.checkServer();assertTrue(model.state.value.checkingServer)
        model.cancel();model.setAddress("https://example.org/new");gate.complete(Unit);yield()
        assertNull(model.state.value.readiness);assertEquals("https://example.org/new",model.state.value.serverAddress)
    }
    @Test fun readyCheckPreservesUnsavedResultAndDoesNotStartAnotherUpload() {
        val model=vm();model.select(context,Uri.parse("content://synthetic/photo"));model.start()
        val previous=model.state.value.result;model.checkServer()
        assertSame(previous,model.state.value.result);assertTrue(model.state.value.hasUnsavedResult);assertEquals(1,calls)
    }
    @Test fun privateSnapshotRestoresVerifiedPixelsMasksAndSavedIdentityWithSmallBundle()=runBlocking {
        val state=SavedStateHandle();val session=ExperimentalPhotoSession(context,state);val expected=result
        session.attach(session.write(source,expected));session.markSaved(expected.requestId)
        try {
            val restored=ExperimentalPhotoSession(context,copy(state)).restore()
            assertArrayEquals(source.png,restored.source.png);assertArrayEquals(expected.png,restored.result!!.png)
            assertEquals(expected.changedPixels,restored.result!!.changedPixels);assertTrue(restored.result!!.accepted[19])
            assertEquals(expected.requestId,restored.savedId)
            assertTrue(state.keys().all { state.get<Any>(it) is String || state.get<Any>(it) is Long || state.get<Any>(it)==null })
        } finally { session.clear() }
    }
    @Test fun modifiedSnapshotCannotBecomeAValidResult()=runBlocking {
        val state=SavedStateHandle();val session=ExperimentalPhotoSession(context,state)
        session.attach(session.write(source,result))
        val file=File(context.cacheDir,"experimental-photo-drafts/${state.get<String>(ExperimentalPhotoSession.GROUP)}/${state.get<String>(ExperimentalPhotoSession.TOKEN)}/response.json")
        file.appendText("private corruption")
        try { session.restore();fail("Corrupt result restored") } catch(_: IllegalArgumentException) { } finally { session.clear() }
    }
    @Test fun expiredOrTraversalSnapshotIsRejected()=runBlocking {
        val state=SavedStateHandle();val session=ExperimentalPhotoSession(context,state)
        session.attach(session.write(source,null));state["photo-v2-created"]=System.currentTimeMillis()-ExperimentalPhotoSession.MAX_AGE-1
        try { session.restore();fail() } catch(_: IllegalArgumentException) { } finally { session.clear() }
        state[ExperimentalPhotoSession.TOKEN]="../outside";state["photo-v2-created"]=System.currentTimeMillis()
        try { session.restore();fail() } catch(_: IllegalArgumentException) { } finally { session.clear() }
    }
    @Test fun snapshotWithUpdatedHashStillMustPassTheFullPixelAndApprovalContract()=runBlocking {
        val state=SavedStateHandle();val session=ExperimentalPhotoSession(context,state)
        session.attach(session.write(source,result))
        val file=File(context.cacheDir,"experimental-photo-drafts/${state.get<String>(ExperimentalPhotoSession.GROUP)}/${state.get<String>(ExperimentalPhotoSession.TOKEN)}/response.json")
        val invalid=Json.decodeFromString<ExperimentalPhotoResponse>(file.readText()).copy(privacyValidated=true)
        val bytes=Json.encodeToString(invalid).toByteArray()
        file.writeBytes(bytes);state["photo-v2-response-sha"]=ExperimentalPngCodec.hash(bytes)
        try { session.restore();fail("Unapproved cached result accepted") } catch(_: IllegalArgumentException) { } finally { session.clear() }
    }
    @Test fun freshViewModelRestoresResultWithoutRerunningNetworkOrOldSaveTicket()=runBlocking {
        val state=SavedStateHandle();val cache=ExperimentalPhotoSession(context,state)
        cache.attach(cache.write(source,result))
        val model=vm(copy(state));model.initialize(context);idle(model)
        assertNotNull(model.state.value.result);assertTrue(model.state.value.hasUnsavedResult)
        model.finishSave(context,null,"obsolete-ticket")
        assertFalse(model.state.value.awaitingSave);assertEquals(0,calls)
        model.discardSession();assertNull(model.state.value.pendingShare);cache.clear()
    }
    @Test fun backgroundCompletionDoesNotDeleteTheSnapshotReferencedByAnOlderOsBundle()=runBlocking {
        val state=SavedStateHandle();val cache=ExperimentalPhotoSession(context,state)
        cache.attach(cache.write(source,null));val stoppedBundle=copy(state)
        cache.attach(cache.write(source,result))
        try {
            val old=ExperimentalPhotoSession(context,stoppedBundle).restore()
            assertArrayEquals(source.png,old.source.png);assertNull(old.result)
            assertNotNull(ExperimentalPhotoSession(context,copy(state)).restore().result)
        } finally { cache.clear() }
        assertFalse(File(context.cacheDir,"experimental-photo-drafts/${state.get<String>(ExperimentalPhotoSession.GROUP)}").exists())
    }
    @Test fun completedCameraInputIsRemovedAfterImportAndDismissedReplacement() {
        fun output()=CameraCaptureFiles.create(context) { file -> Uri.parse("content://${context.packageName}.camera/camera/${file.name}") }
        val model=vm();val captured=output();val file=CameraCaptureFiles.ownedFile(context,captured)!!
        file.writeBytes(byteArrayOf(1));model.select(context,captured);assertFalse(file.exists())
        model.start();val other=output();val otherFile=CameraCaptureFiles.ownedFile(context,other)!!;otherFile.writeBytes(byteArrayOf(2))
        model.select(context,other);assertTrue(otherFile.exists())
        model.dismissReplacement(model.state.value.replacement!!.token);assertFalse(otherFile.exists())
        assertNotNull(model.state.value.result)
    }
    @Test fun exactPngShareIsReadOnlyAndNeverContainsOriginalOrMasks()=runBlocking {
        val expected=result;var file: File?=null
        val share=ExperimentalPhotoShareFiles.prepare(context,expected) { output -> file=output
            Uri.parse("content://${context.packageName}.protected-share/processed/${output.name}") }
        try {
            assertArrayEquals(expected.png,file!!.readBytes())
            val intent=ExperimentalPhotoShareFiles.intent(share)
            assertEquals("image/png",intent.type);assertEquals(Intent.ACTION_SEND,intent.action)
            assertEquals(share.uri,intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))
            assertEquals(0,intent.flags and Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            assertTrue(intent.getStringExtra(Intent.EXTRA_TEXT)!!.contains("전체 보호는 검증되지"))
            assertEquals(1,intent.clipData!!.itemCount)
        } finally { ExperimentalPhotoShareFiles.discard(context,share) }
        assertFalse(file!!.exists())
    }
    @Test fun failedSharePreparationDeletesItsNewFile()=runBlocking {
        var file: File?=null
        try { ExperimentalPhotoShareFiles.prepare(context,result) { output -> file=output;throw IllegalStateException("synthetic") };fail() }
        catch(_: IllegalStateException) { }
        assertNotNull(file);assertFalse(file!!.exists())
    }
    @Test fun shareCancelledAtTheDispatcherHandoffRemovesThePreparedFile()=runBlocking {
        var file: File?=null
        val operation=async {
            val ownJob=coroutineContext[Job]!!
            ExperimentalPhotoShareFiles.prepare(context,result) { output ->
                file=output;ownJob.cancel();Uri.parse("content://synthetic/cancelled.png")
            }
        }
        try { operation.await();fail() } catch(_: CancellationException) { }
        operation.join()
        assertNotNull(file);assertFalse(file!!.exists())
    }
    @Test fun regionPreviewUsesFullResolutionCoordinatesAndOverlayOnlyChangesDisplay() {
        val expected=result;val bytes=expected.png.clone();val crop=ComparisonCrop(1,2,3,2)
        val original=experimentalRegionPreview(source.png,crop)
        val returned=experimentalRegionPreview(expected.png,crop)
        val tinted=experimentalRegionPreview(expected.png,crop,expected)
        assertEquals(source.preview.getPixel(1,2),original.getPixel(0,0))
        assertEquals(expected.returned.getPixel(1,2),returned.getPixel(0,0))
        assertNotEquals(returned.getPixel(0,0),tinted.getPixel(0,0));assertArrayEquals(bytes,expected.png)
        original.recycle();returned.recycle();tinted.recycle()
    }
    @Test fun regionPreviewRejectsOutsideCoordinates() {
        try { experimentalRegionPreview(source.png,ComparisonCrop(-1,0,2,2));fail() } catch(_: IllegalArgumentException) { }
    }
}
