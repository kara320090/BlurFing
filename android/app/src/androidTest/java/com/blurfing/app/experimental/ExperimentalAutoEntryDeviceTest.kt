package com.blurfing.app.experimental

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import com.blurfing.app.MainActivity
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Verify the user-facing main entry selects the automatic engine, without uploading a photo. */
@RunWith(AndroidJUnit4::class)
class ExperimentalAutoEntryDeviceTest {
    @get:Rule val compose=createAndroidComposeRule<MainActivity>()

    @Test fun mainAutomaticEntryOpensV23ReadyForPhotoSelection() {
        compose.onNodeWithText("자동 지문 보호 · V23 실험").performScrollTo().performClick()
        var activity: ExperimentalPhotoActivity?=null
        compose.waitUntil(10000) {
            InstrumentationRegistry.getInstrumentation().runOnMainSync {
                activity=ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED)
                    .filterIsInstance<ExperimentalPhotoActivity>().firstOrNull()
            }
            activity!=null
        }
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val model=ViewModelProvider(activity!!)[ExperimentalPhotoViewModel::class.java]
            assertEquals(ExperimentalPhotoEngine.SYNTHETIC,model.state.value.engine)
            assertFalse(model.state.value.busy)
            assertNull(model.state.value.source)
            model.discardSession()
            activity!!.finish()
        }
    }
}
