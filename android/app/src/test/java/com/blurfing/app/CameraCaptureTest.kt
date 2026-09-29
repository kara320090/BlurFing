package com.blurfing.app

import android.app.Application
import android.content.ActivityNotFoundException
import android.content.ContentProvider
import android.content.ContentValues
import android.content.pm.ProviderInfo
import android.content.Intent
import android.database.Cursor
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.MediaStore
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.utils.CameraCaptureContract
import com.blurfing.app.utils.CameraCaptureFiles
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.CameraCaptureViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowContentResolver
import org.xmlpull.v1.XmlPullParser
import java.io.File
import java.io.FileNotFoundException

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class CameraCaptureTest {
    private val context: Application get() = RuntimeEnvironment.getApplication()
    private val store = ViewModelStore()
    private val temporaryFiles = mutableListOf<File>()
    private var nextKey = 0

    @Before fun setUp() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        // AndroidX FileProvider uses Android '/' paths; Windows host paths cannot be resolved by it.
        // Model only URI-to-file I/O on Windows; keep the real provider on Linux/macOS.
        if (File.separatorChar == '\\') {
            val provider = HostCameraProvider()
            provider.attachInfo(context, ProviderInfo().apply { authority = "${context.packageName}.camera" })
            ShadowContentResolver.registerProviderInternal("${context.packageName}.camera", provider)
        }
    }

    @After fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
        temporaryFiles.forEach { it.delete() }
    }

    private fun camera(state: SavedStateHandle = SavedStateHandle()): CameraCaptureViewModel =
        CameraCaptureViewModel(context, state, { createOutput() }).also { store.put("camera-${nextKey++}", it) }

    private fun createOutput(): Uri = if (File.separatorChar == '\\') {
        CameraCaptureFiles.create(context) { file ->
            Uri.Builder().scheme("content").authority("${context.packageName}.camera")
                .appendPath("camera").appendPath(file.name).build()
        }
    } else CameraCaptureFiles.create(context)

    private fun importer(): BlurFingViewModel =
        BlurFingViewModel().also { store.put("import-${nextKey++}", it) }

    private fun output(camera: CameraCaptureViewModel): Uri = camera.beginCapture()!!.also {
        temporaryFiles.add(CameraCaptureFiles.ownedFile(context, it)!!)
    }

    private fun writeJpeg(uri: Uri, rotated: Boolean = false) {
        val bitmap = Bitmap.createBitmap(8, 6, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        try {
            context.contentResolver.openOutputStream(uri)!!.use {
                assertTrue(bitmap.compress(Bitmap.CompressFormat.JPEG, 95, it))
            }
        } finally { bitmap.recycle() }
        if (rotated) {
            ExifInterface(CameraCaptureFiles.ownedFile(context, uri)!!.path).apply {
                setAttribute(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_ROTATE_90.toString())
                saveAttributes()
            }
        }
    }

    @Suppress("DEPRECATION")
    @Test fun manifestRestrictsSharingAndIntentGrantsOnlyTheOutput() {
        val uri = createOutput().also {
            temporaryFiles.add(CameraCaptureFiles.ownedFile(context, it)!!)
        }
        val provider = context.packageManager.resolveContentProvider("${context.packageName}.camera", 0)!!
        assertFalse(provider.exported)
        assertTrue(provider.grantUriPermissions)
        val paths = mutableListOf<Triple<String, String?, String?>>()
        context.resources.getXml(R.xml.camera_file_paths).use { parser ->
            while (parser.eventType != XmlPullParser.END_DOCUMENT) {
                if (parser.eventType == XmlPullParser.START_TAG && parser.name != "paths") {
                    paths.add(Triple(parser.name, parser.getAttributeValue(null, "name"), parser.getAttributeValue(null, "path")))
                }
                parser.next()
            }
        }
        assertEquals(listOf(Triple("cache-path", "camera", "camera-captures/")), paths)
        assertEquals("content", uri.scheme)
        val intent = CameraCaptureContract().createIntent(context, uri)
        assertEquals(MediaStore.ACTION_IMAGE_CAPTURE, intent.action)
        assertEquals(uri, intent.getParcelableExtra<Uri>(MediaStore.EXTRA_OUTPUT))
        assertEquals(1, intent.clipData!!.itemCount)
        assertEquals(uri, intent.clipData!!.getItemAt(0).uri)
        assertTrue(intent.flags and Intent.FLAG_GRANT_READ_URI_PERMISSION != 0)
        assertTrue(intent.flags and Intent.FLAG_GRANT_WRITE_URI_PERMISSION != 0)
        if (File.separatorChar != '\\') {
            val outside = File.createTempFile("unrelated-", ".jpg", context.cacheDir).also { temporaryFiles.add(it) }
            assertThrows(IllegalArgumentException::class.java) {
                FileProvider.getUriForFile(context, "${context.packageName}.camera", outside)
            }
        }
    }

    @Test fun duplicateCaptureDoesNotReplacePendingFile() {
        val camera = camera()
        val uri = output(camera)
        assertNull(camera.beginCapture())
        assertEquals(uri.toString(), camera.pendingUri.value)
        assertTrue(CameraCaptureFiles.ownedFile(context, uri)!!.exists())
    }

    @Test fun successfulCaptureLoadsFullImageNormalizesExifAndDeletesTemporaryOutput() = runBlocking {
        val camera = camera()
        val uri = output(camera)
        val file = CameraCaptureFiles.ownedFile(context, uri)!!
        writeJpeg(uri, rotated = true)
        assertEquals(uri, camera.completeCapture(true))
        assertTrue(file.exists()) // Keep the output until the importer consumes it.
        val importer = importer()
        importer.onCameraImageCaptured(uri, context)!!.join()
        val ready = importer.uiState.value as UiState.Ready
        assertEquals(ScreenStep.REGION_EDITOR, ready.step)
        assertEquals(6, ready.originalBitmap.width)
        assertEquals(8, ready.originalBitmap.height)
        assertTrue(Color.blue(ready.originalBitmap.getPixel(0, 0)) > 240)
        assertFalse(ready.originalBitmap.isRecycled)
        assertFalse(file.exists())
        assertNull(camera.pendingUri.value)
    }

    @Test fun cancelledCaptureDeletesPartialOutputAndAllowsAnotherAttempt() {
        val camera = camera()
        val uri = output(camera)
        writeJpeg(uri)
        assertNull(camera.completeCapture(false))
        assertFalse(CameraCaptureFiles.ownedFile(context, uri)!!.exists())
        assertNull(camera.error.value)
        assertNull(camera.pendingUri.value)
        assertNotEquals(uri, output(camera))
    }

    @Test fun unavailableCameraCleansOutputAndOffersGalleryFallback() {
        val camera = camera()
        val uri = output(camera)
        camera.launchFailed(ActivityNotFoundException("PRIVATE_PATH_OR_CAMERA_DETAILS"))
        assertFalse(CameraCaptureFiles.ownedFile(context, uri)!!.exists())
        assertNull(camera.pendingUri.value)
        assertTrue(camera.error.value.orEmpty().contains("갤러리"))
        assertFalse(camera.error.value.orEmpty().contains("PRIVATE_PATH"))
        assertNotNull(output(camera))
        assertNull(camera.error.value)
    }

    @Test fun deniedCameraLaunchDoesNotExposeExceptionDetails() {
        val camera = camera()
        val uri = output(camera)
        camera.launchFailed(SecurityException("PRIVATE_PROVIDER_PATH"))
        assertFalse(CameraCaptureFiles.ownedFile(context, uri)!!.exists())
        assertNull(camera.pendingUri.value)
        assertFalse(camera.error.value.orEmpty().contains("PRIVATE_PROVIDER_PATH"))
        assertTrue(camera.error.value.orEmpty().contains("카메라를 열지"))
    }

    @Test fun emptySuccessIsNotImportedAndItsFileIsRemoved() {
        val camera = camera()
        val uri = output(camera)
        assertNull(camera.completeCapture(true))
        assertFalse(CameraCaptureFiles.ownedFile(context, uri)!!.exists())
        assertTrue(camera.error.value.orEmpty().contains("다시 촬영"))
    }

    @Test fun corruptCaptureReportsImportErrorAndRemovesOnlyItsTemporaryFile() = runBlocking {
        val camera = camera()
        val uri = output(camera)
        val file = CameraCaptureFiles.ownedFile(context, uri)!!
        file.writeText("synthetic invalid camera output")
        assertEquals(uri, camera.completeCapture(true))
        val importer = importer()
        importer.onCameraImageCaptured(uri, context)!!.join()
        assertTrue(importer.uiState.value is UiState.Error)
        assertFalse(file.exists())
    }

    @Test fun savedPendingOutputCanBeCompletedAfterProcessRecreation() = runBlocking {
        val state = SavedStateHandle()
        val uri = output(camera(state))
        writeJpeg(uri)
        val restoredState = SavedStateHandle(state.keys().associateWith { state.get<Any?>(it) })
        val restored = camera(restoredState)
        assertEquals(uri.toString(), restored.pendingUri.value)
        assertEquals(uri, restored.completeCapture(true))
        assertNull(restored.completeCapture(true))
        val importer = importer()
        importer.onCameraImageCaptured(uri, context)!!.join()
        assertTrue(importer.uiState.value is UiState.Ready)
        assertFalse(CameraCaptureFiles.ownedFile(context, uri)!!.exists())
    }

    @Test fun missingRestoredOutputAllowsRetryWithoutCrash() {
        val state = SavedStateHandle()
        val uri = output(camera(state))
        CameraCaptureFiles.ownedFile(context, uri)!!.delete()
        val restored = camera(SavedStateHandle(state.keys().associateWith { state.get<Any?>(it) }))
        assertNull(restored.completeCapture(true))
        assertNull(restored.pendingUri.value)
        assertNotNull(restored.error.value)
        assertNotNull(output(restored))
    }

    @Test fun resetBeforeImportStartsStillCleansCapture() = runTest {
        Dispatchers.setMain(StandardTestDispatcher(testScheduler))
        val camera = camera()
        val uri = output(camera)
        writeJpeg(uri)
        camera.completeCapture(true)
        val importer = importer()
        importer.onCameraImageCaptured(uri, context)
        importer.resetToIdle()
        advanceUntilIdle()
        assertEquals(UiState.Idle, importer.uiState.value)
        assertFalse(CameraCaptureFiles.ownedFile(context, uri)!!.exists())
    }

    @Test fun unrelatedUriIsNeverImportedOrDeletedAsCameraOutput() {
        val outside = File.createTempFile("not-a-capture-", ".jpg", context.cacheDir).also {
            temporaryFiles.add(it)
            it.writeText("keep this unrelated file")
        }
        val importer = importer()
        val unrelatedUri = Uri.fromFile(outside)
        assertNull(importer.onCameraImageCaptured(unrelatedUri, context))
        CameraCaptureFiles.discard(context, unrelatedUri)
        assertTrue(outside.exists())
        assertEquals(UiState.Idle, importer.uiState.value)
        val traversal = Uri.parse("content://${context.packageName}.camera/camera/%2E%2E%2Fnot-a-capture.jpg")
        assertFalse(CameraCaptureFiles.isOwned(context, traversal))
    }

    @Test fun expiredCleanupPreservesActiveRecentAndUnrelatedFiles() {
        val now = System.currentTimeMillis()
        val active = output(camera())
        val expired = output(camera())
        val recent = output(camera())
        val oldTime = now - 48 * 60 * 60 * 1000L
        assertTrue(CameraCaptureFiles.ownedFile(context, active)!!.setLastModified(oldTime))
        assertTrue(CameraCaptureFiles.ownedFile(context, expired)!!.setLastModified(oldTime))
        val unrelated = File(CameraCaptureFiles.ownedFile(context, active)!!.parentFile, "unrelated.txt").also {
            temporaryFiles.add(it)
            it.writeText("keep")
            it.setLastModified(oldTime)
        }
        CameraCaptureFiles.removeExpired(context, active, now)
        assertTrue(CameraCaptureFiles.ownedFile(context, active)!!.exists())
        assertFalse(CameraCaptureFiles.ownedFile(context, expired)!!.exists())
        assertTrue(CameraCaptureFiles.ownedFile(context, recent)!!.exists())
        assertTrue(unrelated.exists())
    }

    @Test fun activityDefaultFactoryCreatesCameraViewModelWithSavedState() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create()
        try {
            val vm = ViewModelProvider(controller.get())[CameraCaptureViewModel::class.java]
            assertNull(vm.pendingUri.value)
            assertNull(vm.error.value)
        } finally { controller.destroy() }
    }

    @Test fun providerPreparationFailureDoesNotLeaveAnOutputOrExposePaths() {
        var allocated: File? = null
        val camera = CameraCaptureViewModel(context, SavedStateHandle()) { app ->
            CameraCaptureFiles.create(app) { file ->
                allocated = file
                throw IllegalArgumentException("PRIVATE_INTERNAL_PATH")
            }
        }.also { store.put("failed-preparation", it) }
        assertNull(camera.beginCapture())
        assertNotNull(allocated)
        assertFalse(allocated!!.exists())
        assertNull(camera.pendingUri.value)
        assertFalse(camera.error.value.orEmpty().contains("PRIVATE_INTERNAL_PATH"))
        assertTrue(camera.error.value.orEmpty().contains("저장 공간"))
    }

    /** A controlled host provider; it does not verify Android's cross-app permission enforcement. */
    private class HostCameraProvider : ContentProvider() {
        override fun onCreate() = true
        override fun getType(uri: Uri) = "image/jpeg"
        override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
            val file = CameraCaptureFiles.ownedFile(context!!, uri) ?: throw FileNotFoundException()
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.parseMode(mode))
        }
        override fun query(uri: Uri, projection: Array<out String>?, selection: String?,
            selectionArgs: Array<out String>?, sortOrder: String?): Cursor? = null
        override fun insert(uri: Uri, values: ContentValues?): Uri? = throw UnsupportedOperationException()
        override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?) = 0
        override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?) = 0
    }
}
