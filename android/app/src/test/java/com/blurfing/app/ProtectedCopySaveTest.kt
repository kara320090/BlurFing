package com.blurfing.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.repository.ProtectionRepository
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
import java.io.IOException
import java.util.concurrent.atomic.AtomicInteger

/** 합성 이미지와 제어 가능한 저장 함수로 상태를 검증한다. 실기기 MediaStore 시험과 구분한다. */
@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ProtectedCopySaveTest {
    private val store = ViewModelStore()
    private val context: Context get() = RuntimeEnvironment.getApplication()
    private val savedUri = Uri.parse("content://media/external/images/media/101")

    @Before fun setUp() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
    }

    private fun viewModel(saver: suspend (Context, Bitmap) -> Result<Uri>): BlurFingViewModel {
        val repository = object : ProtectionRepository {
            override suspend fun protectImage(request: ProtectionRequest, imageBytes: ByteArray) =
                Result.success(ProtectionResponse(
                    requestId = request.requestId, status = "succeeded", resultKind = "mock",
                    appliedRegions = request.regions.orEmpty(), warnings = listOf("MOCK_RESULT")
                ))
            override fun cancelRequest(requestId: String) {}
        }
        return BlurFingViewModel(repository, saveImage = saver).also { store.put("save-test", it) }
    }

    private suspend fun load(vm: BlurFingViewModel, color: Int = Color.BLUE): UiState.Ready {
        val file = File.createTempFile("blurfing-save-synthetic-", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888).apply { eraseColor(color) }
        try {
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            vm.onImageSelected(Uri.fromFile(file), context)
            return withTimeout(5000) { vm.uiState.first { it is UiState.Ready } as UiState.Ready }
        } finally {
            bitmap.recycle()
            file.delete()
        }
    }

    private suspend fun prepare(vm: BlurFingViewModel): UiState.Ready {
        load(vm)
        vm.deleteRegion(1)
        vm.startProtection()
        return withTimeout(5000) {
            vm.uiState.first { it is UiState.Ready && it.step == ScreenStep.COMPARISON } as UiState.Ready
        }
    }

    @Test fun failureKeepsComparisonAndCanRetrySameProtectedBitmap() = runBlocking {
        val calls = AtomicInteger()
        val savedBitmaps = mutableListOf<Bitmap>()
        val vm = viewModel { _, bitmap ->
            savedBitmaps.add(bitmap)
            if (calls.incrementAndGet() == 1) Result.failure(IOException("PRIVATE_INTERNAL_PATH"))
            else Result.success(savedUri)
        }
        val before = prepare(vm)
        vm.saveProtectedImage(context)
        val failed = vm.uiState.value
        assertTrue("Save failure must retain the comparison", failed is UiState.Ready)
        failed as UiState.Ready
        assertEquals(ScreenStep.COMPARISON, failed.step)
        assertSame(before.originalBitmap, failed.originalBitmap)
        assertSame(before.protectedBitmap, failed.protectedBitmap)
        assertEquals(before.regions, failed.regions)
        assertSame(before.protectionResponse, failed.protectionResponse)
        assertFalse(failed.isSaving)
        assertNotNull(failed.saveError)
        assertFalse(failed.saveError.orEmpty().contains("PRIVATE_INTERNAL_PATH"))
        assertNull(failed.saveMessage)

        vm.saveProtectedImage(context)
        val completed = vm.uiState.value as UiState.Ready
        assertFalse(completed.isSaving)
        assertNull(completed.saveError)
        assertNotNull(completed.saveMessage)
        assertEquals(2, calls.get())
        savedBitmaps.forEach { assertSame(before.protectedBitmap, it) }
    }

    @Test fun repeatedSaveWhilePendingWritesOnlyOneCopy() = runBlocking {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val calls = AtomicInteger()
        val vm = viewModel { _, _ ->
            calls.incrementAndGet()
            entered.complete(Unit)
            release.await()
            Result.success(savedUri)
        }
        prepare(vm)
        vm.saveProtectedImage(context)
        withTimeout(5000) { entered.await() }
        vm.saveProtectedImage(context)
        try {
            assertEquals("Repeated taps must not start another write", 1, calls.get())
            assertTrue((vm.uiState.value as UiState.Ready).isSaving)
        } finally { release.complete(Unit) }
        val completed = withTimeout(5000) {
            vm.uiState.first { it is UiState.Ready && it.saveMessage != null } as UiState.Ready
        }
        assertFalse(completed.isSaving)
    }

    @Test fun thrownStorageExceptionKeepsPhotoAndReenablesSaving() = runBlocking {
        val vm = viewModel { _, _ -> throw SecurityException("PRIVATE_PROVIDER_DETAIL") }
        val before = prepare(vm)
        vm.saveProtectedImage(context)
        val failed = vm.uiState.value as UiState.Ready
        assertEquals(ScreenStep.COMPARISON, failed.step)
        assertSame(before.originalBitmap, failed.originalBitmap)
        assertSame(before.protectedBitmap, failed.protectedBitmap)
        assertNotNull(failed.saveError)
        assertFalse(failed.saveError.orEmpty().contains("PRIVATE_PROVIDER_DETAIL"))
        assertFalse(failed.isSaving)
    }

    @Test fun editorCannotSavePreviousProcessingResult() = runBlocking {
        val calls = AtomicInteger()
        val vm = viewModel { _, _ -> calls.incrementAndGet(); Result.success(savedUri) }
        prepare(vm)
        vm.navigateToStep(ScreenStep.REGION_EDITOR)
        vm.saveProtectedImage(context)
        assertEquals(0, calls.get())
        assertFalse((vm.uiState.value as UiState.Ready).isSaving)
    }

    @Test fun resetDoesNotRestorePhotoWhenNonCancellableSaveFinishes() = runBlocking {
        val release = CompletableDeferred<Unit>()
        val finished = CompletableDeferred<Unit>()
        val vm = viewModel { _, _ ->
            try {
                withContext(NonCancellable) { release.await() }
                Result.success(savedUri)
            } finally { finished.complete(Unit) }
        }
        prepare(vm)
        vm.saveProtectedImage(context)
        vm.resetToIdle()
        release.complete(Unit)
        withTimeout(5000) { finished.await() }
        yield()
        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test fun replacementPhotoIsNotOverwrittenByOldSaveCompletion() = runBlocking {
        val release = CompletableDeferred<Unit>()
        val finished = CompletableDeferred<Unit>()
        val vm = viewModel { _, _ ->
            try {
                withContext(NonCancellable) { release.await() }
                Result.success(savedUri)
            } finally { finished.complete(Unit) }
        }
        prepare(vm)
        vm.saveProtectedImage(context)
        val replacement = load(vm, Color.GREEN)
        release.complete(Unit)
        withTimeout(5000) { finished.await() }
        yield()
        val current = vm.uiState.value as UiState.Ready
        assertEquals(ScreenStep.REGION_EDITOR, current.step)
        assertSame(replacement.originalBitmap, current.originalBitmap)
        assertNull(current.protectedBitmap)
        assertNull(current.saveMessage)
        assertFalse(current.isSaving)
    }

    @Test fun returnToEditorKeepsNewEditsWhenOldSaveFinishes() = runBlocking {
        val release = CompletableDeferred<Unit>()
        val finished = CompletableDeferred<Unit>()
        val vm = viewModel { _, _ ->
            try {
                withContext(NonCancellable) { release.await() }
                Result.success(savedUri)
            } finally { finished.complete(Unit) }
        }
        prepare(vm)
        vm.saveProtectedImage(context)
        vm.navigateToStep(ScreenStep.REGION_EDITOR)
        val edited = NormalizedRegion(0.1f, 0.1f, 0.2f, 0.2f)
        vm.updateRegion(0, edited)
        release.complete(Unit)
        withTimeout(5000) { finished.await() }
        yield()
        val current = vm.uiState.value as UiState.Ready
        assertEquals(ScreenStep.REGION_EDITOR, current.step)
        assertEquals(listOf(edited), current.regions)
        assertNull(current.saveMessage)
        assertFalse(current.isSaving)
    }
}
