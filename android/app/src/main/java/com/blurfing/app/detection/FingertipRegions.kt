package com.blurfing.app.detection

import com.blurfing.app.model.NormalizedRegion
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/** Hand keypoints propose editable pads; they do not establish fingerprint visibility. */
data class HandPoint(val x: Float, val y: Float)

object FingertipRegions {
    fun fromHands(hands: List<List<HandPoint>>, width: Int, height: Int): List<NormalizedRegion> {
        require(width > 0 && height > 0)
        val candidates = hands.flatMap { hand ->
            if (hand.size != 21 || hand.any { !it.x.isFinite() || !it.y.isFinite() }) return@flatMap emptyList()
            val points = hand.map { HandPoint(it.x * width, it.y * height) }
            fun distance(a: Int, b: Int) = hypot(points[a].x - points[b].x, points[a].y - points[b].y)
            if (distance(5, 17) < 8f) return@flatMap emptyList()
            listOf(4, 8, 12, 16, 20).mapNotNull { tip ->
                val joint = tip - 1
                val base = tip - 2
                val root = if (tip == 4) 1 else tip - 3
                val a = points[tip]; val b = points[joint]; val c = points[base]
                if (hand[tip].x !in 0f..1f || hand[tip].y !in 0f..1f) return@mapNotNull null
                val length = distance(tip, joint)
                val previous = distance(joint, base)
                if (length < 3f || previous < 1f) return@mapNotNull null
                val straightness = ((a.x-b.x)*(b.x-c.x) + (a.y-b.y)*(b.y-c.y)) / (length*previous)
                // Folded digits can still have landmarks. Do not propose their knuckles as pads.
                if (straightness < .35f || distance(tip, 0) < distance(base, 0) * 1.08f ||
                    distance(tip, root) < distance(base, root)) return@mapNotNull null
                if (tip == 4 && distance(tip, 17) < distance(2, 17) * 1.08f) return@mapNotNull null
                val ux = (a.x-b.x)/length; val uy = (a.y-b.y)/length
                val cx = a.x - ux*length*.40f; val cy = a.y - uy*length*.40f
                val halfX = kotlin.math.abs(ux)*length*.55f + kotlin.math.abs(uy)*length*.40f
                val halfY = kotlin.math.abs(uy)*length*.55f + kotlin.math.abs(ux)*length*.40f
                val left = max(0f, cx-halfX); val top = max(0f, cy-halfY)
                val right = min(width.toFloat(), cx+halfX); val bottom = min(height.toFloat(), cy+halfY)
                if (right-left < 2f || bottom-top < 2f) null
                else NormalizedRegion(left/width, top/height, (right-left)/width, (bottom-top)/height)
            }
        }
        return merge(emptyList(), candidates).sortedWith(compareBy({ it.y }, { it.x }))
    }

    /** Preserve manual edits, adding only pads that are not already substantially covered. */
    fun merge(existing: List<NormalizedRegion>, candidates: List<NormalizedRegion>): List<NormalizedRegion> {
        val result = existing.toMutableList()
        for (candidate in candidates.take(10)) {
            if (result.none { covered(it, candidate) }) result.add(candidate)
        }
        return result.toList()
    }

    private fun covered(a: NormalizedRegion, b: NormalizedRegion): Boolean {
        val width = max(0f, min(a.x+a.width,b.x+b.width)-max(a.x,b.x))
        val height = max(0f, min(a.y+a.height,b.y+b.height)-max(a.y,b.y))
        return width*height >= min(a.width*a.height,b.width*b.height)*.50f
    }
}
