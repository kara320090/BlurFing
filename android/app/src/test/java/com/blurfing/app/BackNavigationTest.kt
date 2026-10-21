package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.repository.MockProtectionRepository
import com.blurfing.app.repository.ProtectionRepository
import com.blurfing.app.utils.DraftSession
import com.blurfing.app.viewmodel.BackNavigationResult
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

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class BackNavigationTest {
    private val store = ViewModelStore()
    @Before fun setup() {
        prepareNativeGraphicsFixture()
        Dispatchers.setMain(Dispatchers.Unconfined)
    }
    @After fun cleanup() { store.clear(); Dispatchers.resetMain() }

    private suspend fun load(vm: BlurFingViewModel): UiState.Ready {
        store.put("back", vm)
        val context = RuntimeEnvironment.getApplication()
        val source = File.createTempFile("back-synthetic-", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(16, 16, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        try {
            source.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
            vm.onImageSelected(Uri.fromFile(source), context)
            withTimeout(5000) { vm.uiState.first { it is UiState.Ready } }
            vm.addRegion()
            return vm.uiState.value as UiState.Ready
        } finally { bitmap.recycle(); source.delete() }
    }

    /** Deliberately ignores cancellation until released to exercise late responses. */
    private class HoldingRepository : ProtectionRepository {
        val entered = CompletableDeferred<ProtectionRequest>()
        val release = CompletableDeferred<Unit>()
        val finished = CompletableDeferred<Unit>()
        var cancelledId: String? = null
        override suspend fun protectImage(request: ProtectionRequest, imageBytes: ByteArray): Result<ProtectionResponse> {
            entered.complete(request)
            try {
                withContext(NonCancellable) { release.await() }
                return MockProtectionRepository(0).protectImage(request, imageBytes)
            } finally { finished.complete(Unit) }
        }
        override fun cancelRequest(requestId: String) { cancelledId = requestId }
    }

    @Test fun firstScreenLeavesBackToTheOperatingSystem() {
        val vm = BlurFingViewModel()
        store.put("back", vm)
        assertEquals(BackNavigationResult.UNHANDLED, vm.onBackRequested())
        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test fun settingsBackPreservesEditsAndEditorBackClearsOnlyTheDraft() = runBlocking {
        val draft = DraftSession(RuntimeEnvironment.getApplication(), SavedStateHandle())
        val vm = BlurFingViewModel(draftSession = draft)
        val loaded = load(vm)
        vm.updateSettings(ProcessingSettings(strength = .7f))
        vm.navigateToStep(ScreenStep.PROCESSING)
        assertEquals(BackNavigationResult.NAVIGATED, vm.onBackRequested())
        val editor = vm.uiState.value as UiState.Ready
        assertEquals(ScreenStep.REGION_EDITOR, editor.step)
        assertSame(loaded.originalBitmap, editor.originalBitmap)
        assertEquals(loaded.regions, editor.regions)
        assertTrue(editor.canUndoRegions)
        assertEquals(.7f, vm.settings.value.strength)
        assertTrue(draft.hasDraft)
        assertEquals(BackNavigationResult.NAVIGATED, vm.onBackRequested())
        assertEquals(UiState.Idle, vm.uiState.value)
        assertFalse(draft.hasDraft)
        assertFalse(loaded.originalBitmap.isRecycled)
    }

    @Test fun comparisonBackPreservesPhotoAndRegionsWithoutStartingAnotherRequest() = runBlocking {
        val vm = BlurFingViewModel(MockProtectionRepository(0))
        val loaded = load(vm)
        vm.startProtection()
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready && it.step == ScreenStep.COMPARISON } }
        assertEquals(BackNavigationResult.NAVIGATED, vm.onBackRequested())
        val editor = vm.uiState.value as UiState.Ready
        assertEquals(ScreenStep.REGION_EDITOR, editor.step)
        assertSame(loaded.originalBitmap, editor.originalBitmap)
        assertEquals(loaded.regions, editor.regions)
        assertFalse(editor.isProcessing)
        assertFalse(editor.isSaving)
        assertNull(editor.pendingShare)
        assertNull(editor.savePermissionRequestId)
    }

    @Test fun backDuringProcessingRequestsConfirmationAndCanContinueToComparison() = runBlocking {
        val repository = HoldingRepository()
        val vm = BlurFingViewModel(repository)
        load(vm)
        vm.startProtection()
        withTimeout(5000) { repository.entered.await() }
        try {
            val before = vm.uiState.value
            assertEquals(BackNavigationResult.CONFIRM_PROCESSING_CANCEL, vm.onBackRequested())
            assertSame(before, vm.uiState.value)
            assertNull(repository.cancelledId)
        } finally { repository.release.complete(Unit) }
        val completed = withTimeout(5000) {
            vm.uiState.first { it is UiState.Ready && it.step == ScreenStep.COMPARISON } as UiState.Ready
        }
        assertEquals("mock", completed.protectionResponse!!.resultKind)
        assertNull(completed.processingError)
    }

    @Test fun confirmedCancelPreservesEditsAndRejectsALateResponse() = runBlocking {
        val repository = HoldingRepository()
        val vm = BlurFingViewModel(repository)
        val loaded = load(vm)
        vm.startProtection()
        val request = withTimeout(5000) { repository.entered.await() }
        try {
            assertEquals(BackNavigationResult.CONFIRM_PROCESSING_CANCEL, vm.onBackRequested())
            vm.cancelProtection()
            assertEquals(request.requestId, repository.cancelledId)
        } finally { repository.release.complete(Unit) }
        withTimeout(5000) { repository.finished.await() }
        yield()
        val cancelled = vm.uiState.value as UiState.Ready
        assertEquals(ScreenStep.PROCESSING, cancelled.step)
        assertFalse(cancelled.isProcessing)
        assertSame(loaded.originalBitmap, cancelled.originalBitmap)
        assertEquals(loaded.regions, cancelled.regions)
        assertNull(cancelled.protectedBitmap)
        assertNull(cancelled.protectionResponse)
        assertNull(cancelled.processingTiming)
    }
}
