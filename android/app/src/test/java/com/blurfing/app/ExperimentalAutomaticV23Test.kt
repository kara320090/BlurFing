package com.blurfing.app

import android.net.Uri
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.experimental.*
import kotlinx.coroutines.*
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
class ExperimentalAutomaticV23Test {
    private val dispatcher=StandardTestDispatcher()
    private val store=ViewModelStore()
    private val fixtures=ExperimentalPhotoDecoderTest()
    private val source by lazy { fixtures.source() }
    private var calls=0
    private fun response(id: String)=fixtures.response(source).copy(
        requestId=id,photoEngine="synthetic_v23",method="photo_synthetic_v23_automatic_experimental",
        warnings=fixtures.response(source).warnings+listOf("AUTOMATIC_VISIBILITY_UNCALIBRATED","SYNTHETIC_REPLACEMENT_V23"))
    private val service=object: ExperimentalPhotoService {
        override fun cancel(requestId: String)=Unit
        override suspend fun protect(source: ExperimentalPhotoUpload,engine: ExperimentalPhotoEngine,requestId: String): ValidatedExperimentalPhoto {
            calls++
            return ExperimentalPhotoDecoder.decode(response(requestId),source,engine,requestId,checkMemory=false)
        }
    }
    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { store.clear();Dispatchers.resetMain() }
    private fun model()=ExperimentalPhotoViewModel({service},{_,_->source}).also { store.put("test",it) }

    @Test fun selectingPhotoAutomaticallyAppliesV23OnceAndKeepsUnverifiedStatus()=runTest(dispatcher) {
        val model=model();model.setEngine(ExperimentalPhotoEngine.SYNTHETIC)
        model.select(RuntimeEnvironment.getApplication(),Uri.parse("content://synthetic/input"))
        advanceUntilIdle()
        assertEquals(1,calls)
        assertEquals(ExperimentalPhotoEngine.SYNTHETIC,model.state.value.result!!.engine)
        assertFalse(model.state.value.result!!.presentation.mayClaimCompleteProtection)
        assertTrue(model.state.value.hasUnsavedResult)
    }
    @Test fun cancelDuringImportPreventsAutomaticSubmission()=runTest(dispatcher) {
        val model=model();model.setEngine(ExperimentalPhotoEngine.SYNTHETIC)
        model.select(RuntimeEnvironment.getApplication(),Uri.parse("content://synthetic/input"))
        model.cancel();advanceUntilIdle()
        assertEquals(0,calls);assertNull(model.state.value.result)
    }
    @Test fun oldEnginesStillRequireExplicitRun()=runTest(dispatcher) {
        val model=model()
        model.select(RuntimeEnvironment.getApplication(),Uri.parse("content://synthetic/input"))
        advanceUntilIdle();assertEquals(0,calls)
    }
    @Test fun missingAutomaticWarningCannotBeDecodedAsOrdinarySuccess() {
        val value=response("automatic").copy(warnings=fixtures.response(source).warnings)
        try {
            ExperimentalPhotoDecoder.decode(value,source,ExperimentalPhotoEngine.SYNTHETIC,"automatic",checkMemory=false)
            fail("Missing policy warning accepted")
        } catch(_: IllegalArgumentException) { }
    }

    @Test fun surfaceReplacementIsExplicitlyDisplayedWithoutClaimingRidgeObservation() {
        val base=response("surface")
        val value=base.copy(warnings=base.warnings+"PRECAUTIONARY_SURFACE_WITHOUT_RIDGE_CONFIRMATION",
            regionDisplayBounds=base.regionDisplayBounds.map {
                if(it.status=="transformed")it.copy(reasonCode="TRANSFORMED_PRECAUTIONARY_SURFACE") else it
            })
        val result=ExperimentalPhotoDecoder.decode(value,source,ExperimentalPhotoEngine.SYNTHETIC,"surface",checkMemory=false)
        assertTrue(result.presentation.detail.contains("지문선 확인 없이"))
        assertFalse(result.presentation.mayClaimCompleteProtection)
        assertTrue(result.regions.first { it.status=="transformed" }.userExplanation().contains("확인되지 않음"))
        assertEquals(1L,result.changedPixels)
        assertTrue(result.accepted[2*9+1])
        assertTrue(result.rejected[3*9+5])
        for(invalid in listOf(value.copy(warnings=base.warnings),
            value.copy(photoEngine="native_v12",method="photo_native_v12_experimental"))) {
            try {
                val engine=ExperimentalPhotoEngine.fromId(invalid.photoEngine)
                ExperimentalPhotoDecoder.decode(invalid,source,engine,"surface",checkMemory=false)
                fail("Hidden or foreign-engine surface replacement accepted")
            } catch(_: IllegalArgumentException) { }
        }
    }
}
