package com.blurfing.app

import android.net.Uri
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.experimental.*
import java.io.File
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ExperimentalPhotoRunTimingTest {
    private val store=ViewModelStore()
    private val fixtures=ExperimentalPhotoDecoderTest()
    private val source by lazy { fixtures.source() }
    private var clock=1000L
    @Before fun setup() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun cleanup() { store.clear();Dispatchers.resetMain() }
    private fun model(): ExperimentalPhotoViewModel {
        val api=object: ExperimentalPhotoService {
            override fun cancel(requestId: String)=Unit
            override suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto {
                clock+=85_000
                val base=fixtures.response(source)
                val response=if(engine==ExperimentalPhotoEngine.SYNTHETIC)base.copy(requestId=requestId,
                    photoEngine=engine.id,method=engine.method,
                    warnings=base.warnings+listOf("AUTOMATIC_VISIBILITY_UNCALIBRATED","SYNTHETIC_REPLACEMENT_V23")) else base.copy(requestId=requestId)
                return ExperimentalPhotoDecoder.decode(response,source,engine,requestId,checkMemory=false)
            }
        }
        return ExperimentalPhotoViewModel({api},{_,_->clock+=1000;source},monotonicMs={clock})
            .also { store.put("timing",it) }
    }
    @Test fun automaticRunIncludesImportAndOnlyVerifiedSaveCompletesTarget()=runBlocking {
        val vm=model();vm.setEngine(ExperimentalPhotoEngine.SYNTHETIC)
        vm.select(RuntimeEnvironment.getApplication(),Uri.parse("content://synthetic/input"))
        withTimeout(10_000) { vm.state.first { it.result!=null } }
        val timing=vm.state.value.runTiming!!
        assertTrue(timing.includesImport);assertEquals(86_000L,timing.resultElapsedMs)
        assertNull(timing.withinDemoTarget)
        val ticket=vm.prepareSave()!!
        clock+=5000
        val file=File.createTempFile("demo-timing-", ".png",RuntimeEnvironment.getApplication().cacheDir)
        try {
            vm.finishSave(RuntimeEnvironment.getApplication(),Uri.fromFile(file),ticket)
            withTimeout(10_000) { vm.state.first { it.savedResultRequestId!=null } }
            assertArrayEquals(vm.state.value.result!!.png,file.readBytes())
            assertEquals(91_000L,vm.state.value.runTiming!!.savedElapsedMs)
            assertEquals(true,vm.state.value.runTiming!!.withinDemoTarget)
        } finally { file.delete() }
    }
    @Test fun manualRetryHasNewRequestAndDoesNotReuseImportTime()=runBlocking {
        val vm=model();vm.select(RuntimeEnvironment.getApplication(),Uri.parse("content://synthetic/input"))
        vm.start();withTimeout(10_000) { vm.state.first { it.result!=null } }
        val first=vm.state.value.runTiming!!
        assertFalse(first.includesImport);assertEquals(85_000L,first.resultElapsedMs)
        vm.start();vm.confirmReplacement(vm.state.value.replacement!!.token)
        withTimeout(10_000) { vm.state.first { it.result!=null && it.runTiming!!.requestId!=first.requestId } }
        assertEquals(85_000L,vm.state.value.runTiming!!.resultElapsedMs)
        vm.cancel();assertNull(vm.state.value.runTiming)
    }
    @Test fun timeTargetCannotBeRecordedBeforeReadbackOrWithBackwardClock() {
        val timing=ExperimentalPhotoRunTiming("request",1000,true)
        assertThrows(IllegalArgumentException::class.java) { timing.saved(2000) }
        assertThrows(IllegalArgumentException::class.java) { timing.resultReady(999) }
        val late=timing.resultReady(110_000).saved(121_001)
        assertEquals(false,late.withinDemoTarget)
        assertEquals(late,late.saved(200_000))
    }
}
