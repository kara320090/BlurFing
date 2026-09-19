package com.blurfing.app

import com.blurfing.app.model.NormalizedRegion
import org.junit.Assert.*
import org.junit.Test

class NormalizedRegionTest {

    @Test
    fun validCoordinates_createSuccessfully() {
        val region = NormalizedRegion(x = 0.1f, y = 0.2f, width = 0.3f, height = 0.4f)
        assertEquals(0.1f, region.x, 0.001f)
        assertEquals(0.2f, region.y, 0.001f)
        assertEquals(0.3f, region.width, 0.001f)
        assertEquals(0.4f, region.height, 0.001f)
    }

    @Test(expected = IllegalArgumentException::class)
    fun negativeX_throwsException() {
        NormalizedRegion(x = -0.01f, y = 0.2f, width = 0.3f, height = 0.4f)
    }

    @Test(expected = IllegalArgumentException::class)
    fun negativeY_throwsException() {
        NormalizedRegion(x = 0.1f, y = -0.01f, width = 0.3f, height = 0.4f)
    }

    @Test(expected = IllegalArgumentException::class)
    fun zeroWidth_throwsException() {
        NormalizedRegion(x = 0.1f, y = 0.2f, width = 0.0f, height = 0.4f)
    }

    @Test(expected = IllegalArgumentException::class)
    fun xPlusWidthExceedsOne_throwsException() {
        NormalizedRegion(x = 0.8f, y = 0.2f, width = 0.3f, height = 0.4f)
    }

    @Test(expected = IllegalArgumentException::class)
    fun yPlusHeightExceedsOne_throwsException() {
        NormalizedRegion(x = 0.1f, y = 0.8f, width = 0.3f, height = 0.3f)
    }

    @Test
    fun safeCreate_clampsOutOfBoundsValuesSafely() {
        // x + width > 1 인 경우 안전하게 클램핑
        val clamped1 = NormalizedRegion.safeCreate(x = 0.85f, y = 0.1f, width = 0.5f, height = 0.2f)
        assertTrue("x + width must be <= 1.0", clamped1.x + clamped1.width <= 1.0001f)
        assertTrue(clamped1.width > 0f)

        // 음수 좌표 안전하게 0으로 클램핑
        val clamped2 = NormalizedRegion.safeCreate(x = -0.5f, y = -0.2f, width = 0.3f, height = 0.3f)
        assertEquals(0.0f, clamped2.x, 0.001f)
        assertEquals(0.0f, clamped2.y, 0.001f)
    }
}
