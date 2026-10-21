package com.blurfing.app.detection

import android.content.Context
import android.graphics.Bitmap
import com.blurfing.app.model.NormalizedRegion
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.withContext
import kotlin.math.max
import kotlin.math.roundToInt

/** Bundled, on-device CPU detection. The original photograph never leaves the phone here. */
object MediaPipeFingertipDetector {
    suspend fun detect(context: Context, original: Bitmap): List<NormalizedRegion> = withContext(Dispatchers.Default) {
        currentCoroutineContext().ensureActive()
        if (original.width < 32 || original.height < 32) return@withContext emptyList()
        val scale = minOf(1f, 1280f / max(original.width, original.height))
        val scaled = Bitmap.createScaledBitmap(original, (original.width*scale).roundToInt().coerceAtLeast(1),
            (original.height*scale).roundToInt().coerceAtLeast(1), true)
        val bitmap = if (scaled === original) original.copy(Bitmap.Config.ARGB_8888, false) else scaled
        try {
            val options = HandLandmarker.HandLandmarkerOptions.builder()
                .setBaseOptions(BaseOptions.builder().setModelAssetPath("hand_landmarker.task")
                    .setDelegate(Delegate.CPU).build())
                .setRunningMode(RunningMode.IMAGE).setNumHands(2)
                .setMinHandDetectionConfidence(.5f).setMinHandPresenceConfidence(.5f).build()
            HandLandmarker.createFromOptions(context.applicationContext, options).use { detector ->
                val image = BitmapImageBuilder(bitmap).build()
                try {
                    val hands = detector.detect(image).landmarks().map { hand -> hand.map { HandPoint(it.x(),it.y()) } }
                    currentCoroutineContext().ensureActive()
                    FingertipRegions.fromHands(hands, original.width, original.height)
                } finally { image.close() }
            }
        } catch (error: LinkageError) {
            throw IllegalStateException("이 기기에서 손끝 탐지 모듈을 실행하지 못했습니다.", error)
        } finally { if (!bitmap.isRecycled) bitmap.recycle() }
    }
}
