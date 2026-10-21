package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
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
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class AutomaticDetectionStateTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private val store = ViewModelStore()
    private val files = mutableListOf<File>()
    private var registered: BlurFingViewModel? = null
    private val pad = NormalizedRegion(.15f,.2f,.1f,.2f)
    @Before fun before() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun after() { store.clear(); files.forEach { it.delete() }; Dispatchers.resetMain() }
    private fun photo(vm: BlurFingViewModel) {
        if (registered !== vm) { store.put("vm",vm); registered = vm }
        val file = File.createTempFile("automatic-synthetic-",".png",context.cacheDir)
        files.add(file)
        file.outputStream().use { stream ->
            val bitmap = Bitmap.createBitmap(16,16,Bitmap.Config.ARGB_8888)
            try { bitmap.eraseColor(Color.BLUE); bitmap.compress(Bitmap.CompressFormat.PNG,100,stream) }
            finally { bitmap.recycle() }
        }
        vm.onImageSelected(Uri.fromFile(file),context)
    }
    private suspend fun finished(vm: BlurFingViewModel) =
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready && !it.isDetecting } } as UiState.Ready
    private suspend fun pending(vm: BlurFingViewModel) =
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready && it.isDetecting } } as UiState.Ready

    @Test fun photoImportAddsDetectedPadsAndTheyCanBeUndone() = runBlocking {
        val gate = CompletableDeferred<List<NormalizedRegion>>()
        val vm = BlurFingViewModel(detectFingertips = { _,_ -> gate.await() },
            apiRepositoryFactory = { error("Detection must not upload the photograph") })
        photo(vm); pending(vm); gate.complete(listOf(pad))
        assertEquals(listOf(pad),finished(vm).regions)
        vm.undoRegions(); assertTrue((vm.uiState.value as UiState.Ready).regions.isEmpty())
        vm.redoRegions(); assertEquals(listOf(pad),(vm.uiState.value as UiState.Ready).regions)
    }
    @Test fun editingWhileDetectionIsPendingPreservesManualSelection() = runBlocking {
        val gate = CompletableDeferred<List<NormalizedRegion>>()
        val vm = BlurFingViewModel(detectFingertips = { _,_ -> withContext(NonCancellable) { gate.await() } })
        photo(vm); pending(vm); vm.addRegion()
        val manual = (vm.uiState.value as UiState.Ready).regions
        gate.complete(listOf(pad))
        assertEquals(manual,finished(vm).regions)
    }
    @Test fun resetDiscardsALateDetection() = runBlocking {
        val gate = CompletableDeferred<List<NormalizedRegion>>()
        val vm = BlurFingViewModel(detectFingertips = { _,_ -> withContext(NonCancellable) { gate.await() } })
        photo(vm); pending(vm); vm.resetToIdle(); gate.complete(listOf(pad))
        assertEquals(UiState.Idle,vm.uiState.value)
    }
    @Test fun aNewPhotoCannotReceiveThePreviousPhotosLatePads() = runBlocking {
        val old = CompletableDeferred<List<NormalizedRegion>>()
        val fresh = CompletableDeferred<List<NormalizedRegion>>()
        var calls = 0
        val vm = BlurFingViewModel(detectFingertips = { _,_ ->
            val gate = if (++calls == 1) old else fresh
            withContext(NonCancellable) { gate.await() }
        })
        photo(vm); val first = pending(vm)
        photo(vm)
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready && it.originalBitmap !== first.originalBitmap && it.isDetecting } }
        val newPad = pad.copy(x=.65f)
        fresh.complete(listOf(newPad)); assertEquals(listOf(newPad),finished(vm).regions)
        old.complete(listOf(pad)); assertEquals(listOf(newPad),(vm.uiState.value as UiState.Ready).regions)
    }
    @Test fun noDetectionKeepsPhotoAndManualEditingAvailable() = runBlocking {
        val vm = BlurFingViewModel(detectFingertips = { _,_ -> emptyList() })
        photo(vm)
        val ready = finished(vm)
        assertTrue(ready.regions.isEmpty()); assertFalse(ready.originalBitmap.isRecycled)
        assertTrue(ready.detectionMessage!!.contains("찾지 못"))
        vm.addRegion(); assertEquals(1,(vm.uiState.value as UiState.Ready).regions.size)
    }
    @Test fun detectorFailureNeverBecomesAFakeDefaultRegionAndRetryWorks() = runBlocking {
        var calls = 0
        val vm = BlurFingViewModel(detectFingertips = { _,_ ->
            if (++calls == 1) throw IllegalStateException("synthetic model failure") else listOf(pad)
        })
        photo(vm)
        assertTrue(finished(vm).regions.isEmpty())
        vm.detectRegions(context)
        assertEquals(listOf(pad),finished(vm).regions)
    }
    @Test fun rescanKeepsEditsAndDeduplicates() = runBlocking {
        val vm = BlurFingViewModel(detectFingertips = { _,_ -> listOf(pad) })
        photo(vm); finished(vm); vm.addRegion()
        val edited = (vm.uiState.value as UiState.Ready).regions
        vm.detectRegions(context)
        assertEquals(edited,finished(vm).regions)
    }
}
