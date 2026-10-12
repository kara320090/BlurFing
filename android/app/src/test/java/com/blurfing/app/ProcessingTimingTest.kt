package com.blurfing.app

import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.model.ProcessingTiming
import com.blurfing.app.repository.MockProtectionRepository
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
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
import java.util.concurrent.atomic.AtomicInteger

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ProcessingTimingTest {
    private val store = ViewModelStore()
    @Before fun setup() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun cleanup() { store.clear(); Dispatchers.resetMain() }

    @Test fun timingUsesMonotonicDifferencesAndRejectsReversedClock() {
        assertEquals(ProcessingTiming(10, 40, 5, 55), ProcessingTiming.between(100, 110, 150, 155))
        assertEquals(ProcessingTiming(0, 0, 0, 0), ProcessingTiming.between(100, 100, 100, 100))
        try { ProcessingTiming.between(100, 90, 150, 155); fail("Reversed clock must not produce a duration") }
        catch (_: IllegalArgumentException) {}
    }

    @Test fun successCapturesActualRunAndEditingInvalidatesTiming() = runBlocking {
        val tick = AtomicInteger()
        val times = longArrayOf(100, 110, 150, 155)
        val vm = BlurFingViewModel(MockProtectionRepository(0), monotonicMs = { times[tick.getAndIncrement()] })
        store.put("timing", vm)
        val context = RuntimeEnvironment.getApplication()
        val file = File.createTempFile("timing-synthetic-", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888)
        try {
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            vm.onImageSelected(Uri.fromFile(file), context)
            withTimeout(5000) { vm.uiState.first { it is UiState.Ready } }
            vm.addRegion()
            vm.startProtection(strength = 0.7f)
            val success = withTimeout(5000) { vm.uiState.first { it is UiState.Ready && it.step == ScreenStep.COMPARISON } as UiState.Ready }
            assertEquals(ProcessingTiming(10, 40, 5, 55), success.processingTiming)
            assertEquals(0.7f, success.processingRun!!.strength)
            assertFalse(success.processingRun!!.useServer)
            vm.navigateToStep(ScreenStep.REGION_EDITOR)
            vm.clearRegions()
            val edited = vm.uiState.value as UiState.Ready
            assertNull(edited.processingTiming)
            assertNull(edited.processingRun)
            assertNull(edited.protectedBitmap)
        } finally { file.delete(); bitmap.recycle() }
    }
}
