package com.blurfing.app.experimental

import android.content.ContentProvider
import android.content.ContentValues
import android.content.pm.ProviderInfo
import android.database.Cursor
import android.net.Uri
import android.os.Bundle
import android.os.ParcelFileDescriptor
import androidx.lifecycle.ViewModelStore
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
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowContentResolver
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Synthetic validated RGB/masks and a real file-backed controlled provider; no AI inference. */
@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ExperimentalPhotoExitTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private val store = ViewModelStore()
    private val fixtures = ExperimentalPhotoDecoderTest()
    private lateinit var vm: ExperimentalPhotoViewModel
    private lateinit var source: ExperimentalPhotoUpload
    private lateinit var provider: SaveProvider

    @Before fun setUp() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        source = fixtures.source()
        provider = SaveProvider(File.createTempFile("synthetic-v2-exit-", ".png", context.cacheDir))
        provider.attachInfo(context, ProviderInfo().apply { authority = SaveProvider.AUTHORITY })
        ShadowContentResolver.registerProviderInternal(SaveProvider.AUTHORITY, provider)
        val service = object : ExperimentalPhotoService {
            override fun cancel(requestId: String) = Unit
            override suspend fun protect(source: ExperimentalPhotoUpload, engine: ExperimentalPhotoEngine,
                                         requestId: String): ValidatedExperimentalPhoto =
                ExperimentalPhotoDecoder.decode(fixtures.response(source).copy(requestId = requestId),
                    source, engine, requestId, checkMemory = false)
        }
        vm = ExperimentalPhotoViewModel({ service }, { _, _ -> source })
        store.put("exit", vm)
        vm.select(context, Uri.parse("content://synthetic/one"))
        vm.start()
        assertNotNull(vm.state.value.result)
    }

    @After fun tearDown() {
        store.clear()
        provider.file.delete()
        provider.corrupt.delete()
        Dispatchers.resetMain()
    }

    private suspend fun save() {
        val ticket = vm.prepareSave()
        assertNotNull(ticket)
        assertTrue(vm.state.value.awaitingSave)
        assertTrue(vm.state.value.requiresExitConfirmation)
        vm.finishSave(context, provider.uri, ticket)
        withTimeout(10_000) { vm.state.first { !it.saving && !it.awaitingSave } }
    }

    @Test fun verifiedSaveClearsWarningAndNewExecutionGetsItsOwnUnsavedState() = runBlocking {
        val original = source.png.clone()
        assertTrue(vm.state.value.hasUnsavedResult)
        val id = vm.state.value.result!!.requestId
        save()
        assertArrayEquals(vm.state.value.result!!.png, provider.file.readBytes())
        assertArrayEquals(original, source.png)
        assertEquals(id, vm.state.value.savedResultRequestId)
        assertFalse(vm.state.value.requiresExitConfirmation)
        vm.start()
        assertNotEquals(id, vm.state.value.result!!.requestId)
        assertNull(vm.state.value.savedResultRequestId)
        assertTrue(vm.state.value.hasUnsavedResult)
    }

    @Test fun cancellingDocumentPickerKeepsCurrentResultUnsavedAndDoesNotWrite() {
        val result = vm.state.value.result
        val ticket = vm.prepareSave()
        assertTrue(vm.state.value.hasActiveWork)
        vm.finishSave(context, null, ticket)
        assertSame(result, vm.state.value.result)
        assertTrue(vm.state.value.hasUnsavedResult)
        assertFalse(vm.state.value.hasActiveWork)
        assertEquals(0, provider.writes)
        assertNull(vm.state.value.savedResultRequestId)
    }

    @Test fun readbackMismatchCannotClearWarningAndRemovesOnlyIncompleteCopy() = runBlocking {
        provider.badReadback = true
        save()
        assertNull(vm.state.value.savedResultRequestId)
        assertTrue(vm.state.value.requiresExitConfirmation)
        assertTrue(vm.state.value.message!!.contains("저장하지 못했습니다"))
        assertTrue("Incomplete-copy cleanup must finish", provider.removed.await(5, TimeUnit.SECONDS))
        assertEquals(1, provider.deletes)
        assertFalse(provider.file.exists())
        source.verify()
    }

    @Test fun staleSaveTicketCannotMarkAnotherPhotoOrResultSaved() {
        val previousId = vm.state.value.result!!.requestId
        val ticket = vm.prepareSave()
        vm.cancel() // Explicit cancellation invalidates the outstanding picker before replacement.
        vm.select(context, Uri.parse("content://synthetic/two"))
        vm.confirmReplacement(vm.state.value.replacement!!.token)
        vm.start()
        val next = vm.state.value.result!!
        assertNotEquals(previousId, next.requestId)
        vm.finishSave(context, provider.uri, ticket)
        assertSame(next, vm.state.value.result)
        assertTrue(vm.state.value.hasUnsavedResult)
        assertNull(vm.state.value.savedResultRequestId)
        assertFalse(vm.state.value.awaitingSave)
        assertEquals(0, provider.writes)
    }

    @Test fun cancellingASecondSaveKeepsEarlierVerifiedCopyState() = runBlocking {
        save()
        val id = vm.state.value.savedResultRequestId
        val ticket = vm.prepareSave()
        assertTrue(vm.state.value.requiresExitConfirmation)
        vm.finishSave(context, null, ticket)
        assertEquals(id, vm.state.value.savedResultRequestId)
        assertFalse(vm.state.value.requiresExitConfirmation)
        assertEquals(1, provider.writes)
    }

    @Test fun savedResultSurvivesSelectingTheSameEngineAndNewPhotoNeedsNoDiscard() = runBlocking {
        save()
        val before = vm.state.value
        vm.setEngine(before.engine)
        assertSame(before, vm.state.value)
        vm.select(context, Uri.parse("content://synthetic/two"))
        assertNull(vm.state.value.replacement)
        assertNull(vm.state.value.result)
        assertSame(source, vm.state.value.source)
        assertFalse(vm.state.value.hasUnsavedResult)
        assertArrayEquals(before.result!!.png, provider.file.readBytes())
    }

    @Test fun cancellationKeepsAnUnsavedResultAndEngineChangeClearsItsSaveIdentity() = runBlocking {
        vm.cancel()
        assertTrue(vm.state.value.hasUnsavedResult)
        save()
        vm.setEngine(ExperimentalPhotoEngine.POSE)
        assertNull(vm.state.value.result)
        assertNull(vm.state.value.savedResultRequestId)
        assertFalse(vm.state.value.requiresExitConfirmation)
        assertSame(source, vm.state.value.source)
    }

    @Test fun noResultOrOriginalReturnNeedsNoDiscardButEveryActivePhaseDoes() {
        val result = vm.state.value.result!!
        val rejected = ValidatedExperimentalPhoto(result.requestId, result.engine, result.returned,
            result.png, result.accepted, result.rejected,
            result.presentation.copy(canSaveChangedCopy = false, originalReturned = true),
            2, 0, 2, 0, result.regions, result.preview, result.overlayPreview)
        assertFalse(ExperimentalPhotoState().requiresExitConfirmation)
        assertFalse(ExperimentalPhotoState(result = rejected).requiresExitConfirmation)
        for (state in listOf(ExperimentalPhotoState(busy = true), ExperimentalPhotoState(importing = true),
            ExperimentalPhotoState(saving = true), ExperimentalPhotoState(awaitingSave = true))) {
            assertTrue(state.requiresExitConfirmation)
        }
    }

    private class SaveProvider(val file: File) : ContentProvider() {
        companion object { const val AUTHORITY = "com.blurfing.synthetic.documents" }
        val uri: Uri = Uri.parse("content://$AUTHORITY/document/synthetic-result")
        val corrupt = File(file.parentFile, file.name + ".corrupt").apply { writeBytes(byteArrayOf(1, 2, 3)) }
        var writes = 0
        var deletes = 0
        var badReadback = false
        val removed = CountDownLatch(1)
        override fun onCreate() = true
        override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
            assertEquals(this.uri, uri)
            return if (mode == "r") ParcelFileDescriptor.open(if (badReadback) corrupt else file, ParcelFileDescriptor.MODE_READ_ONLY)
            else {
                writes++
                ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_WRITE_ONLY or
                    ParcelFileDescriptor.MODE_CREATE or ParcelFileDescriptor.MODE_TRUNCATE)
            }
        }
        override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int {
            assertEquals(this.uri, uri)
            deletes++
            file.delete()
            removed.countDown()
            return 1
        }
        override fun call(method: String, arg: String?, extras: Bundle?): Bundle? {
            if (method == "android:deleteDocument") {
                delete(uri, null, null)
                return Bundle()
            }
            return super.call(method, arg, extras)
        }
        override fun query(uri: Uri, projection: Array<out String>?, selection: String?, selectionArgs: Array<out String>?, sortOrder: String?): Cursor? = null
        override fun getType(uri: Uri) = "image/png"
        override fun insert(uri: Uri, values: ContentValues?): Uri? = null
        override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?) = 0
    }
}
