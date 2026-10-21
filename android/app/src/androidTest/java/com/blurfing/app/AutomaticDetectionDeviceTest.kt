package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.SystemClock
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.blurfing.app.detection.MediaPipeFingertipDetector
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** Real bundled CPU model. Optional private input is supplied outside Git on the test device. */
@RunWith(AndroidJUnit4::class)
class AutomaticDetectionDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Test fun bundledModelRunsOfflineAndBlankImageDoesNotProduceFakeBoxes() = runBlocking {
        val source = Bitmap.createBitmap(256,256,Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        try {
            assertTrue(MediaPipeFingertipDetector.detect(compose.activity,source).isEmpty())
            assertFalse(source.isRecycled)
            assertEquals(Color.BLUE,source.getPixel(100,100))
        } finally { source.recycle() }
    }
    @Test fun privateVPhotoAutomaticallyShowsTwoEditablePadsAndRescans() {
        val name = InstrumentationRegistry.getArguments().getString("private_detection_file")
        assumeTrue("Provide a consented local V photo to run this real-image check", name != null)
        require(name!!.matches(Regex("[A-Za-z0-9._-]+")))
        val context = compose.activity
        val input = File(context.cacheDir,name)
        assertTrue("Private input was not transferred to target cache", input.isFile)
        val vm = ViewModelProvider(context)[BlurFingViewModel::class.java]
        val started = SystemClock.elapsedRealtime()
        try {
            compose.runOnUiThread { vm.resetToIdle(); vm.onImageSelected(Uri.fromFile(input),context) }
            compose.waitUntil(30_000) {
                (vm.uiState.value as? UiState.Ready)?.let { !it.isDetecting && it.detectionMessage != null } == true
            }
            val detected = vm.uiState.value as UiState.Ready
            assertEquals(detected.detectionMessage,2,detected.regions.size)
            compose.onNodeWithText("손끝 자동 탐지").assertIsDisplayed()
            val initial = detected.regions
            compose.onNodeWithText("손끝 자동 탐지").performClick()
            compose.waitUntil(30_000) { (vm.uiState.value as? UiState.Ready)?.isDetecting == false }
            assertEquals(initial,(vm.uiState.value as UiState.Ready).regions)
            File(context.cacheDir,"private-detection-report.txt").writeText(
                "Real bundled MediaPipe CPU model; private provided V photo; two editable pads; rescan deduplicated.\n" +
                    "elapsed_ms=" + (SystemClock.elapsedRealtime()-started) + "\n" +
                    "regions=" + initial.joinToString() + "\n")
            // Leave this view visible for a local QA screenshot; no server upload is performed.
        } catch (error: Throwable) {
            compose.runOnUiThread { vm.resetToIdle() }
            throw error
        }
    }
}
