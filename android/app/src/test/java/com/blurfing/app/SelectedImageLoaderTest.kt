package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.ViewModelStore
import com.blurfing.app.utils.PhotoImportException
import com.blurfing.app.utils.SelectedImageLoader
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
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.util.zip.CRC32

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class SelectedImageLoaderTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private val files = mutableListOf<File>()
    private val store = ViewModelStore()

    @Before fun setUp() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
        files.forEach { it.delete() }
    }

    private fun file(): File = File.createTempFile("blurfing-import-", ".image", context.cacheDir).also { files.add(it) }

    private fun photo(format: Bitmap.CompressFormat = Bitmap.CompressFormat.PNG): File {
        val bitmap = Bitmap.createBitmap(8, 6, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        return file().also { output ->
            try { output.outputStream().use { assertTrue(bitmap.compress(format, 100, it)) } }
            finally { bitmap.recycle() }
        }
    }

    private suspend fun expectInputError(input: File): PhotoImportException {
        try {
            SelectedImageLoader.load(context, Uri.fromFile(input))
            throw AssertionError("Expected rejected input")
        } catch (e: PhotoImportException) { return e }
    }

    private fun oversizedHeader(): File = photo().also { input ->
        val bytes = input.readBytes()
        // A valid PNG header with 20,004,000 pixels; no oversized bitmap is allocated by the test.
        ByteBuffer.wrap(bytes).putInt(16, 5001).putInt(20, 4000)
        val crc = CRC32().apply { update(bytes, 12, 17) }
        ByteBuffer.wrap(bytes).putInt(29, crc.value.toInt())
        input.writeBytes(bytes)
    }

    @Test fun validPngKeepsDimensionsPixelsAndOriginalFile() = runBlocking {
        val input = photo()
        val originalBytes = input.readBytes()
        val bitmap = SelectedImageLoader.load(context, Uri.fromFile(input))
        try {
            assertEquals(8, bitmap.width)
            assertEquals(6, bitmap.height)
            assertEquals(Color.BLUE, bitmap.getPixel(0, 0))
            assertArrayEquals(originalBytes, input.readBytes())
        } finally { bitmap.recycle() }
    }

    @Test fun jpegExifRotationUsesNormalizedPixelDimensions() = runBlocking {
        val input = photo(Bitmap.CompressFormat.JPEG)
        ExifInterface(input.path).apply {
            setAttribute(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_ROTATE_90.toString())
            saveAttributes()
        }
        val originalBytes = input.readBytes()
        val bitmap = SelectedImageLoader.load(context, Uri.fromFile(input))
        try {
            assertEquals(6, bitmap.width)
            assertEquals(8, bitmap.height)
            assertTrue(Color.blue(bitmap.getPixel(0, 0)) > 240)
            assertArrayEquals(originalBytes, input.readBytes())
            assertFalse(bitmap.isRecycled)
        } finally { bitmap.recycle() }
    }

    @Test fun oversizedPngHeaderIsRejectedBeforePixelDecoding() = runBlocking {
        assertTrue(expectInputError(oversizedHeader()).message.orEmpty().contains("2,000만 화소"))
    }

    @Test fun byteLimitIsCheckedBeforeDecoding() = runBlocking {
        val input = photo()
        RandomAccessFile(input, "rw").use { it.setLength(SelectedImageLoader.MAX_IMAGE_BYTES.toLong() + 1) }
        assertTrue(expectInputError(input).message.orEmpty().contains("15MB"))
    }

    @Test fun exactlyTheByteLimitIsAccepted() = runBlocking {
        val input = photo()
        RandomAccessFile(input, "rw").use { it.setLength(SelectedImageLoader.MAX_IMAGE_BYTES.toLong()) }
        val bitmap = SelectedImageLoader.load(context, Uri.fromFile(input))
        try { assertEquals(Color.BLUE, bitmap.getPixel(0, 0)) }
        finally { bitmap.recycle() }
    }

    @Test fun invalidDimensionsAndOverflowCannotBypassPixelLimit() {
        SelectedImageLoader.validateDimensions(5000, 4000)
        listOf(0 to 10, -1 to 10, 10 to 0, Int.MAX_VALUE to Int.MAX_VALUE, 5001 to 4000).forEach { (w, h) ->
            assertThrows(PhotoImportException::class.java) { SelectedImageLoader.validateDimensions(w, h) }
        }
    }

    @Test fun malformedInputIsReportedAsUnreadable() = runBlocking {
        val input = file().apply { writeText("synthetic non-image data") }
        assertTrue(expectInputError(input).message.orEmpty().contains("손상"))
    }

    @Test fun missingFileDetailsAreNotExposedInUi() = runBlocking {
        val vm = BlurFingViewModel().also { store.put("import", it) }
        val uri = Uri.fromFile(File(context.cacheDir, "PRIVATE_PHOTO_PATH-does-not-exist.png"))
        vm.onImageSelected(uri, context)
        val failure = withTimeout(5000) { vm.uiState.first { it is UiState.Error } as UiState.Error }
        assertFalse(failure.message.contains("PRIVATE_PHOTO_PATH"))
        assertFalse(failure.message.contains("file://"))
        assertTrue(failure.retryable)
    }

    @Test fun rejectedLargePhotoCanBeReplacedWithValidPhoto() = runBlocking {
        val vm = BlurFingViewModel().also { store.put("import", it) }
        vm.onImageSelected(Uri.fromFile(oversizedHeader()), context)
        val failure = withTimeout(5000) { vm.uiState.first { it is UiState.Error } as UiState.Error }
        assertTrue(failure.message.contains("2,000만 화소"))
        val validUri = Uri.fromFile(photo())
        vm.onImageSelected(validUri, context)
        val loaded = withTimeout(5000) { vm.uiState.first { it is UiState.Ready } as UiState.Ready }
        assertEquals(ScreenStep.REGION_EDITOR, loaded.step)
        assertEquals(validUri, loaded.originalUri)
        assertEquals(Color.BLUE, loaded.originalBitmap.getPixel(0, 0))
    }

    @Test fun cancellingPickerKeepsExistingPhotoAndRegions() = runBlocking {
        val vm = BlurFingViewModel().also { store.put("import", it) }
        vm.onImageSelected(Uri.fromFile(photo()), context)
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready } }
        vm.deleteRegion(1)
        val before = vm.uiState.value
        vm.onImageSelected(null, context)
        assertSame(before, vm.uiState.value)
    }
}
