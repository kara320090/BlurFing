package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.utils.ProtectedImageDecoder
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.Base64

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ProtectedImageDecoderTest {
    private fun bitmap(color: Int, size: Int = 4) =
        Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888).apply { eraseColor(color) }
    private fun response(image: Bitmap): ProtectionResponse {
        val bytes = ByteArrayOutputStream().also { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        return ProtectionResponse("synthetic", "succeeded", "real",
            Base64.getEncoder().encodeToString(bytes.toByteArray()))
    }

    @Test fun realResultUsesServerPixelsAndPreservesOriginal() {
        val original = bitmap(Color.BLUE)
        val decoded = ProtectedImageDecoder.decode(response(bitmap(Color.RED)), original, 0.8f)
        assertEquals(Color.RED, decoded.getPixel(0, 0))
        assertEquals(Color.BLUE, original.getPixel(0, 0))
        assertFalse(original.isRecycled)
    }

    @Test fun brokenOrMissingImageNeverFallsBackToLocalBlur() {
        val original = bitmap(Color.BLUE)
        val valid = response(bitmap(Color.RED))
        listOf(valid.copy(imageBase64 = null), valid.copy(imageBase64 = "!!!"),
            valid.copy(imageBase64 = "AA=="), valid.copy(mimeType = "image/jpeg"),
            response(bitmap(Color.RED, 8))).forEach { invalid ->
            assertThrows(IOException::class.java) { ProtectedImageDecoder.decode(invalid, original, 0.5f) }
        }
    }

    @Test fun fullImageMockRegionDoesNotRecycleOriginal() {
        val original = bitmap(Color.BLUE, 1)
        val mock = ProtectionResponse("synthetic", "succeeded", "mock",
            appliedRegions = listOf(NormalizedRegion(0f, 0f, 1f, 1f)))
        val decoded = ProtectedImageDecoder.decode(mock, original, 1f)
        assertFalse(original.isRecycled)
        assertFalse(decoded.isRecycled)
        assertNotSame(original, decoded)
    }

    @Test fun emptyMockRegionIsNotReportedAsProtected() {
        val mock = ProtectionResponse("synthetic", "succeeded", "mock")
        assertThrows(IOException::class.java) { ProtectedImageDecoder.decode(mock, bitmap(Color.BLUE), 0.5f) }
    }
}
