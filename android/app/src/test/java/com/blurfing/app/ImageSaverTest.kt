package com.blurfing.app

import android.content.ContentProvider
import android.content.ContentValues
import android.content.pm.ProviderInfo
import android.database.Cursor
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.MediaStore
import com.blurfing.app.utils.ImageSaver
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
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

/** Exercises ContentResolver calls with a controlled provider, not a device's gallery. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ImageSaverTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private lateinit var provider: RecordingProvider
    private lateinit var bitmap: Bitmap

    @Before fun setUp() {
        provider = RecordingProvider(File.createTempFile("blurfing-save-", ".image", context.cacheDir))
        provider.attachInfo(context, ProviderInfo().apply { authority = MediaStore.AUTHORITY })
        ShadowContentResolver.registerProviderInternal(MediaStore.AUTHORITY, provider)
        bitmap = Bitmap.createBitmap(8, 6, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
    }

    @After fun tearDown() {
        bitmap.recycle()
        provider.file.delete()
    }

    @Test fun pngIsPublishedOnlyAfterReadablePixelsAreWritten() = runBlocking {
        val result = ImageSaver.saveProtectedCopy(context, bitmap)
        assertEquals(provider.itemUri, result.getOrThrow())
        assertEquals("image/png", provider.inserted!!.getAsString(MediaStore.MediaColumns.MIME_TYPE))
        assertTrue(provider.inserted!!.getAsString(MediaStore.MediaColumns.DISPLAY_NAME).endsWith(".png"))
        assertEquals(1, provider.inserted!!.getAsInteger(MediaStore.MediaColumns.IS_PENDING))
        assertEquals(0, provider.published!!.getAsInteger(MediaStore.MediaColumns.IS_PENDING))
        assertTrue(provider.readableAtPublish)
        assertEquals(Color.BLUE, BitmapFactory.decodeFile(provider.file.path).getPixel(0, 0))
        assertEquals(0, provider.deletes)
        assertFalse(bitmap.isRecycled)
    }

    @Test fun zeroPublishedRowsIsFailureAndRemovesIncompleteItem() = runBlocking {
        provider.updateCount = 0
        val result = ImageSaver.saveProtectedCopy(context, bitmap)
        assertTrue("An unpublished image must not be reported as saved", result.isFailure)
        assertEquals(1, provider.deletes)
        assertFalse(provider.file.exists())
    }

    @Test fun insertExceptionIsReturnedWithoutTryingToDeleteAnotherItem() = runBlocking {
        val denied = SecurityException("synthetic permission failure")
        provider.insertError = denied
        val result = ImageSaver.saveProtectedCopy(context, bitmap)
        assertSame(denied, result.exceptionOrNull())
        assertEquals(0, provider.deletes)
    }

    @Test fun nullInsertedUriIsFailureWithoutCleanupOfUnknownItem() = runBlocking {
        provider.nullInsert = true
        assertTrue(ImageSaver.saveProtectedCopy(context, bitmap).isFailure)
        assertEquals(0, provider.deletes)
    }

    @Test fun cleanupFailureDoesNotHideTheOriginalPublishFailure() = runBlocking {
        val publishError = SecurityException("synthetic publish failure")
        val cleanupError = SecurityException("synthetic cleanup failure")
        provider.updateError = publishError
        provider.deleteError = cleanupError
        val result = ImageSaver.saveProtectedCopy(context, bitmap)
        assertSame(publishError, result.exceptionOrNull())
        assertTrue(result.exceptionOrNull()!!.suppressed.contains(cleanupError))
        assertEquals(1, provider.deletes)
        assertNull(provider.published)
    }

    @Test fun cancellationCleansUpAndPropagatesInsteadOfReturningFailure() {
        val cancellation = CancellationException("synthetic cancellation")
        provider.openError = cancellation
        try {
            runBlocking { ImageSaver.saveProtectedCopy(context, bitmap) }
            fail("Cancellation must propagate")
        } catch (actual: CancellationException) {
            assertEquals(cancellation.message, actual.message)
        }
        assertEquals(1, provider.deletes)
        assertNull(provider.published)
    }

    @Test fun publishExceptionReturnsFailureAndDeletesIncompleteItem() = runBlocking {
        val failure = SecurityException("synthetic publish failure")
        provider.updateError = failure
        assertSame(failure, ImageSaver.saveProtectedCopy(context, bitmap).exceptionOrNull())
        assertEquals(1, provider.deletes)
    }

    @Suppress("DEPRECATION")
    @Test fun unsupportedFormatDoesNotCreateAMislabeledPng() = runBlocking {
        val result = ImageSaver.saveProtectedCopy(context, bitmap, Bitmap.CompressFormat.WEBP)
        assertTrue(result.isFailure)
        assertNull(provider.inserted)
    }

    @Test fun jpegExtensionMimeAndEncodedBytesAgree() = runBlocking {
        assertTrue(ImageSaver.saveProtectedCopy(context, bitmap, Bitmap.CompressFormat.JPEG).isSuccess)
        assertEquals("image/jpeg", provider.inserted!!.getAsString(MediaStore.MediaColumns.MIME_TYPE))
        assertTrue(provider.inserted!!.getAsString(MediaStore.MediaColumns.DISPLAY_NAME).endsWith(".jpg"))
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(provider.file.path, bounds)
        assertEquals("image/jpeg", bounds.outMimeType)
        assertEquals(8, bounds.outWidth)
        assertEquals(6, bounds.outHeight)
    }

    @Config(sdk = [28])
    @Test fun legacyProviderDoesNotReceiveScopedStorageColumns() = runBlocking {
        assertTrue(ImageSaver.saveProtectedCopy(context, bitmap).isSuccess)
        assertFalse(provider.inserted!!.containsKey(MediaStore.MediaColumns.IS_PENDING))
        assertFalse(provider.inserted!!.containsKey(MediaStore.MediaColumns.RELATIVE_PATH))
        assertNull(provider.published)
    }

    private class RecordingProvider(val file: File) : ContentProvider() {
        val itemUri: Uri = Uri.parse("content://media/external/images/media/601")
        var inserted: ContentValues? = null
        var published: ContentValues? = null
        var readableAtPublish = false
        var deletes = 0
        var updateCount = 1
        var nullInsert = false
        var insertError: Exception? = null
        var openError: Exception? = null
        var updateError: Exception? = null
        var deleteError: Exception? = null

        override fun onCreate() = true
        override fun insert(uri: Uri, values: ContentValues?): Uri? {
            insertError?.let { throw it }
            inserted = ContentValues(values)
            return if (nullInsert) null else itemUri
        }
        override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
            openError?.let { throw it }
            return ParcelFileDescriptor.open(file,
                ParcelFileDescriptor.MODE_WRITE_ONLY or ParcelFileDescriptor.MODE_CREATE or ParcelFileDescriptor.MODE_TRUNCATE)
        }
        override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?): Int {
            updateError?.let { throw it }
            published = ContentValues(values)
            val decoded = BitmapFactory.decodeFile(file.path)
            readableAtPublish = decoded != null
            decoded?.recycle()
            return updateCount
        }
        override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int {
            assertEquals(itemUri, uri)
            deletes++
            deleteError?.let { throw it }
            file.delete()
            return 1
        }
        override fun query(uri: Uri, projection: Array<out String>?, selection: String?, selectionArgs: Array<out String>?, sortOrder: String?): Cursor? = null
        override fun getType(uri: Uri) = "image/png"
    }
}
