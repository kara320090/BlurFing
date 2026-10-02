package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.model.ProcessingSettingsStore
import com.blurfing.app.utils.DraftSession
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
class DraftSessionTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private val store = ViewModelStore()
    private val regions = listOf(NormalizedRegion(.1f, .2f, .3f, .4f))
    @Before fun setup() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun cleanup() { store.clear(); Dispatchers.resetMain() }
    private fun bitmap() = Bitmap.createBitmap(6, 8, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
    private fun copyState(state: SavedStateHandle) = SavedStateHandle(state.keys().associateWith { state.get<Any>(it) })
    private suspend fun saved(state: SavedStateHandle): DraftSession {
        val session = DraftSession(context, state)
        val bitmap = bitmap()
        session.attach(session.create(bitmap), regions)
        bitmap.recycle()
        return session
    }

    @Test fun copiedSavedStateRestoresPixelsAndLatestEditedCoordinates() = runBlocking {
        val state = SavedStateHandle()
        val session = saved(state)
        val edited = listOf(NormalizedRegion(.5f, .1f, .1f, .2f))
        session.updateRegions(edited)
        val restored = DraftSession(context, copyState(state)).restore()
        assertEquals(edited, restored.regions)
        assertEquals(6, restored.bitmap.width)
        assertEquals(8, restored.bitmap.height)
        assertEquals(Color.BLUE, restored.bitmap.getPixel(0, 0))
        assertFalse(state.keys().any { state.get<Any>(it) is Bitmap })
        restored.bitmap.recycle()
        session.clear()
    }

    @Test fun newViewModelRestoresEditorWithoutRestartingProcessingOrSaving() = runBlocking {
        val state = SavedStateHandle()
        val session = saved(state)
        val vm = BlurFingViewModel(draftSession = DraftSession(context, copyState(state)))
        store.put("restored", vm)
        val ready = withTimeout(5000) { vm.uiState.first { it is UiState.Ready } as UiState.Ready }
        assertEquals(ScreenStep.REGION_EDITOR, ready.step)
        assertEquals(regions, ready.regions)
        assertFalse(ready.isProcessing)
        assertFalse(ready.isSaving)
        assertNull(ready.protectedBitmap)
        assertNull(ready.savePermissionRequestId)
        assertTrue(ready.sessionNotice.orEmpty().contains("복원"))
        vm.resetToIdle()
        assertEquals(UiState.Idle, vm.uiState.value)
        session.clear()
    }

    @Test fun missingCacheRecoversWithSafeReselectionMessage() = runBlocking {
        val state = SavedStateHandle()
        val session = saved(state)
        session.discard(state.get<String>("draft-file")!!)
        val vm = BlurFingViewModel(draftSession = session)
        store.put("missing", vm)
        val error = withTimeout(5000) { vm.uiState.first { it is UiState.Error } as UiState.Error }
        assertTrue(error.message.contains("다시 선택"))
        assertFalse(error.message.contains(context.cacheDir.path))
        assertFalse(session.hasDraft)
    }

    @Test fun expiredDraftIsNotRestored() = runBlocking {
        val state = SavedStateHandle()
        val session = saved(state)
        state["draft-created-at"] = System.currentTimeMillis() - 25L * 60 * 60 * 1000
        assertTrue(runCatching { session.restore() }.isFailure)
        session.clear()
    }

    @Test fun pathTraversalCannotReadOrDeleteUnrelatedFile() = runBlocking {
        val outside = File(context.cacheDir, "unrelated.png").apply { writeText("keep") }
        val state = SavedStateHandle(mapOf("draft-file" to "../unrelated.png",
            "draft-created-at" to System.currentTimeMillis(), "draft-regions" to floatArrayOf()))
        val session = DraftSession(context, state)
        assertTrue(runCatching { session.restore() }.isFailure)
        session.clear()
        assertEquals("keep", outside.readText())
        outside.delete()
        Unit
    }

    @Test fun importAndResetOwnOnlyTheirDraftCopy() = runBlocking {
        val state = SavedStateHandle()
        val session = DraftSession(context, state)
        val vm = BlurFingViewModel(draftSession = session)
        store.put("input", vm)
        val source = File(context.cacheDir, "draft-source.png")
        val bitmap = bitmap()
        source.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
        val bytes = source.readBytes()
        vm.onImageSelected(Uri.fromFile(source), context)
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready } }
        vm.deleteRegion(0)
        val restored = session.restore()
        assertEquals((vm.uiState.value as UiState.Ready).regions, restored.regions)
        restored.bitmap.recycle()
        val token = state.get<String>("draft-file")!!
        vm.resetToIdle()
        assertFalse(File(context.cacheDir, "editing-drafts/$token").exists())
        assertFalse(session.hasDraft)
        assertArrayEquals(bytes, source.readBytes())
        source.delete()
        Unit
    }

    @Test fun settingsSurviveNewStoreAndInvalidStrengthIsRejected() {
        val preferences = ProcessingSettingsStore(context)
        val vm = BlurFingViewModel(settingsStore = preferences)
        val custom = ProcessingSettings(strength = .8f, useServer = true, serverAddress = "https://example.org")
        vm.updateSettings(custom)
        assertEquals(custom, ProcessingSettingsStore(context).load())
        vm.updateSettings(custom.copy(strength = Float.NaN))
        assertEquals(custom, vm.settings.value)
    }

    @Test fun corruptPreferencesUseSafeDefaults() {
        context.getSharedPreferences("processing-settings", 0).edit().putFloat("strength", Float.NaN).commit()
        assertEquals(.5f, ProcessingSettingsStore(context).load().strength)
        context.getSharedPreferences("processing-settings", 0).edit().putString("strength", "corrupt").commit()
        assertEquals(ProcessingSettings(), ProcessingSettingsStore(context).load())
    }
}
