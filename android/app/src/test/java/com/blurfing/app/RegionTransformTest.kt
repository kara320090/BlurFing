package com.blurfing.app

import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.utils.RegionTransform
import com.blurfing.app.utils.RegionCorner
import org.junit.Assert.*
import org.junit.Test

class RegionTransformTest {
    private val r=NormalizedRegion(.2f,.3f,.2f,.2f)
    @Test fun movementClampsPositionWithoutShrinking() {
        val moved=RegionTransform.move(r,5f,-5f)
        assertEquals(.8f,moved.x,.0001f); assertEquals(0f,moved.y,.0001f)
        assertEquals(r.width,moved.width,0f); assertEquals(r.height,moved.height,0f)
    }
    @Test fun allCornersKeepOppositeAnchorAndPreventInversion() {
        for(corner in RegionCorner.entries) {
            val resized=RegionTransform.resize(r,corner,5f,-5f)
            assertTrue(resized.width>0f && resized.height>0f)
            assertTrue(resized.x+resized.width<=1.0001f && resized.y+resized.height<=1.0001f)
            if(corner==RegionCorner.TOP_LEFT || corner==RegionCorner.BOTTOM_LEFT)
                assertEquals(r.x+r.width,resized.x+resized.width,.0001f)
            else assertEquals(r.x,resized.x,0f)
        }
    }
}
