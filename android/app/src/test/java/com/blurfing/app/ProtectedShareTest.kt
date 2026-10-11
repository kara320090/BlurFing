package com.blurfing.app

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.model.ExportFormat
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.utils.ProtectedShare
import com.blurfing.app.utils.ProtectedShareFiles
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
class ProtectedShareTest {
    private val context: Context get() = RuntimeEnvironment.getApplication()
    private val store = ViewModelStore()
    @Before fun setup() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun cleanup() { store.clear(); Dispatchers.resetMain() }

    @Test fun shareHasOnlyReadGrantAndOneProcessedStream() {
        val uri = Uri.parse("content://com.blurfing.app.protected-share/processed/copy.png")
        val intent = ProtectedShareFiles.intent(ProtectedShare(uri, "image/png", true))
        assertEquals(Intent.ACTION_SEND, intent.action)
        assertEquals(uri, intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))
        assertEquals("image/png", intent.type)
        assertEquals(Intent.FLAG_GRANT_READ_URI_PERMISSION, intent.flags)
        assertEquals(uri, intent.clipData!!.getItemAt(0).uri)
        assertTrue(intent.clipData!!.description.label.toString().contains("Mock"))
        assertFalse(intent.hasExtra(Intent.EXTRA_TEXT))
    }

    @Test fun jpegIsReencodedAndExpiredCleanupStaysInOwnedDirectory() = runBlocking {
        val owned = File(context.cacheDir, "protected-shares").apply { mkdirs() }
        val expired = File(owned, "copy-expired.png").apply { writeText("old"); setLastModified(1L) }
        val unrelated = File(context.cacheDir, "source-must-remain.png").apply { writeText("original"); setLastModified(1L) }
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        var file: File? = null
        try {
            val share = ProtectedShareFiles.prepare(context, bitmap,
                ProcessingSettings(exportFormat = ExportFormat.JPEG), false) { result -> file = result; Uri.fromFile(result) }
            assertFalse(expired.exists())
            assertTrue(unrelated.exists())
            assertEquals("image/jpeg", share.mimeType)
            assertEquals(owned.canonicalFile, file!!.parentFile.canonicalFile)
            val bytes = file!!.readBytes()
            assertEquals(0xff, bytes[0].toInt() and 0xff)
            assertEquals(0xd8, bytes[1].toInt() and 0xff)
            assertFalse(file!!.name.contains("source"))
        } finally { bitmap.recycle(); file?.delete(); unrelated.delete() }
    }

    @Test fun uriFailureDeletesNewCopy() = runBlocking {
        val owned = File(context.cacheDir, "protected-shares").apply { mkdirs() }
        val before = owned.listFiles().orEmpty().map { it.name }.toSet()
        val bitmap = Bitmap.createBitmap(4, 4, Bitmap.Config.ARGB_8888)
        try {
            try {
                ProtectedShareFiles.prepare(context, bitmap, ProcessingSettings(), true) { error("unavailable provider") }
                fail("Provider failure must propagate")
            } catch (_: IllegalStateException) {}
            assertEquals(before, owned.listFiles().orEmpty().map { it.name }.toSet())
        } finally { bitmap.recycle() }
    }

    private suspend fun prepare(vm: BlurFingViewModel) {
        store.put("share-test", vm)
        val file = File.createTempFile("share-synthetic-", ".png", context.cacheDir)
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        try {
            file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            vm.onImageSelected(Uri.fromFile(file), context)
            withTimeout(5000) { vm.uiState.first { it is UiState.Ready } }
            vm.addRegion()
            vm.startProtection()
            withTimeout(5000) { vm.uiState.first { it is UiState.Ready && it.step == ScreenStep.COMPARISON } }
        } finally { file.delete(); bitmap.recycle() }
    }

    @Test fun shareUsesProtectedBitmapAndDuplicateTapIsIgnored() = runBlocking {
        val release = CompletableDeferred<Unit>()
        var calls = 0
        var supplied: Bitmap? = null
        val share = ProtectedShare(Uri.parse("content://test/processed"), "image/png", true)
        val vm = BlurFingViewModel(prepareShare = { _, bitmap, _, mock ->
            calls++; supplied = bitmap; assertTrue(mock); release.await(); share
        })
        prepare(vm)
        val ready = vm.uiState.value as UiState.Ready
        vm.shareProtectedImage(context)
        vm.shareProtectedImage(context)
        assertEquals(1, calls)
        assertSame(ready.protectedBitmap, supplied)
        release.complete(Unit)
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready && it.pendingShare != null } }
        vm.consumeShare(share, false)
        val failed = vm.uiState.value as UiState.Ready
        assertNotNull(failed.shareError)
        assertSame(ready.protectedBitmap, failed.protectedBitmap)
    }

    @Test fun resetIgnoresLateShareCompletion() = runBlocking {
        val release = CompletableDeferred<Unit>()
        val finished = CompletableDeferred<Unit>()
        val vm = BlurFingViewModel(prepareShare = { _, _, _, _ ->
            try { withContext(NonCancellable) { release.await() }; ProtectedShare(Uri.parse("content://late"), "image/png", true) }
            finally { finished.complete(Unit) }
        })
        prepare(vm)
        vm.shareProtectedImage(context)
        vm.resetToIdle()
        release.complete(Unit)
        withTimeout(5000) { finished.await() }
        yield()
        assertEquals(UiState.Idle, vm.uiState.value)
    }
}
