package com.blurfing.app

import com.blurfing.app.detection.FingertipRegions
import com.blurfing.app.detection.HandPoint
import com.blurfing.app.model.NormalizedRegion
import org.junit.Assert.*
import org.junit.Test

class FingertipRegionsTest {
    private fun vHand(): List<HandPoint> {
        val hand = MutableList(21) { HandPoint(.5f,.85f) }
        fun digit(start: Int, vararg points: Pair<Float,Float>) {
            points.forEachIndexed { offset,p -> hand[start+offset] = HandPoint(p.first,p.second) }
        }
        digit(1,.45f to .80f,.39f to .77f,.49f to .68f,.57f to .73f)
        digit(5,.40f to .65f,.40f to .45f,.40f to .31f,.40f to .20f)
        digit(9,.57f to .63f,.57f to .45f,.57f to .31f,.57f to .18f)
        digit(13,.68f to .66f,.68f to .59f,.68f to .66f,.67f to .72f)
        digit(17,.76f to .68f,.77f to .63f,.76f to .69f,.73f to .75f)
        return hand
    }
    @Test fun extendedIndexAndMiddleProduceTwoPadsWhileCurledDigitsDoNot() {
        val regions = FingertipRegions.fromHands(listOf(vHand()),1000,800)
        assertEquals(2,regions.size)
        assertTrue(regions.all { it.y < .3f && it.width < .15f && it.height < .2f })
    }
    @Test fun portraitAndNinetyDegreeRotationPreserveTheSameSourceCoordinates() {
        val source = FingertipRegions.fromHands(listOf(vHand()),1000,800)
        val rotated = FingertipRegions.fromHands(listOf(vHand().map { HandPoint(1f-it.y,it.x) }),800,1000)
        assertEquals(source.size,rotated.size)
        source.forEach { a ->
            val b = rotated.minBy { kotlin.math.abs(it.y-a.x) }
            assertEquals(1f-a.y-a.height,b.x,.0001f)
            assertEquals(a.x,b.y,.0001f)
            assertEquals(a.height,b.width,.0001f)
            assertEquals(a.width,b.height,.0001f)
        }
    }
    @Test fun imageEdgesAreClippedAndOffFrameTipsAreExcluded() {
        val regions = FingertipRegions.fromHands(listOf(vHand().map { HandPoint(it.x+.58f,it.y) }),1000,800)
        assertEquals(1,regions.size)
        assertTrue(regions.all { it.x >= 0 && it.y >= 0 && it.x+it.width <= 1.0001f && it.y+it.height <= 1.0001f })
    }
    @Test fun noHandsMalformedAndNonfiniteLandmarksDoNotCreateDefaultBoxes() {
        assertTrue(FingertipRegions.fromHands(emptyList(),100,200).isEmpty())
        assertTrue(FingertipRegions.fromHands(listOf(emptyList(),List(21) { HandPoint(Float.NaN,.2f) }),100,200).isEmpty())
    }
    @Test fun repeatedHandDetectionDoesNotDuplicateTheSamePads() {
        assertEquals(2,FingertipRegions.fromHands(listOf(vHand(),vHand()),1000,800).size)
    }
    @Test fun rescanPreservesManualBoxAndAddsOnlyUncoveredPads() {
        val manual = NormalizedRegion(.1f,.1f,.2f,.2f)
        val covered = NormalizedRegion(.12f,.12f,.1f,.1f)
        val extra = NormalizedRegion(.6f,.2f,.1f,.15f)
        assertEquals(listOf(manual,extra),FingertipRegions.merge(listOf(manual),listOf(covered,extra,extra)))
    }
}
