package com.blurfing.app

import android.Manifest
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.repository.ProtectionRepository
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/** Permission state and save intent tests; the real system permission dialog is tested on a device separately. */
@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class SavePermissionTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private val store = ViewModelStore()
    private val savedBitmaps = mutableListOf<Bitmap>()
    private lateinit var vm: BlurFingViewModel

    @Before fun setUp() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        shadowOf(context).denyPermissions(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        val repository = object : ProtectionRepository {
            override suspend fun protectImage(request: ProtectionRequest, imageBytes: ByteArray) =
                Result.success(ProtectionResponse(request.requestId, "succeeded", "mock",
                    appliedRegions = request.regions.orEmpty(), warnings = listOf("MOCK_RESULT")))
            override fun cancelRequest(requestId: String) {}
        }
        prepareNativeGraphicsFixture()
        vm = BlurFingViewModel(repository, saveImage = { _, bitmap ->
            savedBitmaps.add(bitmap)
            Result.success(Uri.parse("content://media/external/images/media/801"))
        })
        store.put("permission-test", vm)
    }

    @After fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
    }

    private suspend fun load(color: Int = Color.BLUE): UiState.Ready {
        val input = File.createTempFile("blurfing-permission-", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888).apply { eraseColor(color) }
        try {
            input.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            vm.onImageSelected(Uri.fromFile(input), context)
            withTimeout(5000) { vm.uiState.first { it is UiState.Ready } }
            vm.addRegion()
            vm.addRegion()
            return vm.uiState.value as UiState.Ready
        } finally {
            bitmap.recycle()
            input.delete()
        }
    }

    private suspend fun prepare(): UiState.Ready {
        load()
        vm.startProtection()
        return withTimeout(5000) {
            vm.uiState.first { it is UiState.Ready && it.step == ScreenStep.COMPARISON } as UiState.Ready
        }
    }

    private fun grantPermission() = shadowOf(context).grantPermissions(Manifest.permission.WRITE_EXTERNAL_STORAGE)

    @Test fun legacySaveWaitsForPermissionAndDoesNotRepeatRequest() = runBlocking {
        val before = prepare()
        val requestId = vm.saveProtectedImage(context)
        assertNotNull(requestId)
        assertEquals(requestId, (vm.uiState.value as UiState.Ready).savePermissionRequestId)
        assertNull(vm.saveProtectedImage(context))
        assertTrue(savedBitmaps.isEmpty())
        assertSame(before.protectedBitmap, (vm.uiState.value as UiState.Ready).protectedBitmap)
    }

    @Config(sdk = [26])
    @Test fun androidEightAlsoRequiresPermissionBeforeWriting() = runBlocking {
        prepare()
        assertNotNull(vm.saveProtectedImage(context))
        assertTrue(savedBitmaps.isEmpty())
    }

    @Test fun grantedPermissionResumesSameCopyExactlyOnce() = runBlocking {
        val before = prepare()
        val id = vm.saveProtectedImage(context)!!
        grantPermission()
        vm.onSavePermissionResult(context, id, true)
        vm.onSavePermissionResult(context, id, true)
        assertEquals(1, savedBitmaps.size)
        assertSame(before.protectedBitmap, savedBitmaps.single())
        val completed = vm.uiState.value as UiState.Ready
        assertNull(completed.savePermissionRequestId)
        assertNull(completed.saveError)
        assertNotNull(completed.saveMessage)
        assertFalse(completed.isSaving)
    }

    @Test fun deniedPermissionKeepsComparisonAndAllowsRetry() = runBlocking {
        val before = prepare()
        val id = vm.saveProtectedImage(context)!!
        vm.onSavePermissionResult(context, id, false)
        val denied = vm.uiState.value as UiState.Ready
        assertEquals(ScreenStep.COMPARISON, denied.step)
        assertSame(before.originalBitmap, denied.originalBitmap)
        assertSame(before.protectedBitmap, denied.protectedBitmap)
        assertEquals(before.regions, denied.regions)
        assertNull(denied.savePermissionRequestId)
        assertNull(denied.saveMessage)
        assertTrue(denied.saveError.orEmpty().contains("권한"))
        assertTrue(savedBitmaps.isEmpty())
        val retryId = vm.saveProtectedImage(context)
        assertNotNull(retryId)
        assertNotEquals(id, retryId)
    }

    @Test fun grantCallbackWithoutActualPermissionDoesNotWrite() = runBlocking {
        prepare()
        val id = vm.saveProtectedImage(context)!!
        vm.onSavePermissionResult(context, id, true)
        assertTrue(savedBitmaps.isEmpty())
        assertNotNull((vm.uiState.value as UiState.Ready).saveError)
        assertNull((vm.uiState.value as UiState.Ready).savePermissionRequestId)
    }

    @Test fun alreadyGrantedLegacyPermissionSavesWithoutNewPrompt() = runBlocking {
        prepare()
        grantPermission()
        assertNull(vm.saveProtectedImage(context))
        assertEquals(1, savedBitmaps.size)
    }

    @Config(sdk = [29])
    @Test fun androidTenSavesOwnMediaWithoutLegacyPermission() = runBlocking {
        prepare()
        assertNull(vm.saveProtectedImage(context))
        assertEquals(1, savedBitmaps.size)
        assertNotNull((vm.uiState.value as UiState.Ready).saveMessage)
    }

    @Test fun resetInvalidatesPendingPermissionResult() = runBlocking {
        prepare()
        val id = vm.saveProtectedImage(context)!!
        vm.resetToIdle()
        grantPermission()
        vm.onSavePermissionResult(context, id, true)
        assertEquals(UiState.Idle, vm.uiState.value)
        assertTrue(savedBitmaps.isEmpty())
    }

    @Test fun replacementPhotoCannotBeSavedByOldPermissionResult() = runBlocking {
        prepare()
        val id = vm.saveProtectedImage(context)!!
        val replacement = load(Color.GREEN)
        grantPermission()
        vm.onSavePermissionResult(context, id, true)
        assertSame(replacement, vm.uiState.value)
        assertTrue(savedBitmaps.isEmpty())
    }

    @Test fun editorNavigationInvalidatesPermissionAndKeepsEdits() = runBlocking {
        prepare()
        val id = vm.saveProtectedImage(context)!!
        vm.navigateToStep(ScreenStep.REGION_EDITOR)
        vm.deleteRegion(1)
        val edited = vm.uiState.value as UiState.Ready
        assertNull(edited.savePermissionRequestId)
        grantPermission()
        vm.onSavePermissionResult(context, id, true)
        assertSame(edited, vm.uiState.value)
        assertTrue(savedBitmaps.isEmpty())
    }

    @Test fun staleCallbackCannotConsumeANewerPermissionRequest() = runBlocking {
        prepare()
        val oldId = vm.saveProtectedImage(context)!!
        vm.onSavePermissionResult(context, oldId, false)
        val currentId = vm.saveProtectedImage(context)!!
        grantPermission()
        vm.onSavePermissionResult(context, oldId, true)
        assertTrue(savedBitmaps.isEmpty())
        assertEquals(currentId, (vm.uiState.value as UiState.Ready).savePermissionRequestId)
        vm.onSavePermissionResult(context, currentId, true)
        assertEquals(1, savedBitmaps.size)
    }

    @Test fun newProcessingResultIsNotSavedByPreviousPermissionRequest() = runBlocking {
        prepare()
        val id = vm.saveProtectedImage(context)!!
        vm.startProtection()
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready && !it.isProcessing } }
        val current = vm.uiState.value as UiState.Ready
        assertNull(current.savePermissionRequestId)
        grantPermission()
        vm.onSavePermissionResult(context, id, true)
        assertSame(current, vm.uiState.value)
        assertTrue(savedBitmaps.isEmpty())
    }
}
