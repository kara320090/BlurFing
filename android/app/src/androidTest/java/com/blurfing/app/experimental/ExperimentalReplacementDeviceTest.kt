package com.blurfing.app.experimental

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.ViewMatchers.isRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Actual replacement dialog and system Back, with synthetic decision metadata only. */
@RunWith(AndroidJUnit4::class)
class ExperimentalReplacementDeviceTest {
    @get:Rule val compose = createComposeRule()
    private val pending = mutableStateOf<ExperimentalPhotoReplacement?>(null)
    private val confirmed = mutableListOf<String>()
    private val dismissed = mutableListOf<String>()
    private val title = "현재 결과를 바꿀까요?"

    private fun content(restorer: StateRestorationTester = StateRestorationTester(compose)) {
        restorer.setContent {
            MaterialTheme {
                ExperimentalPhotoReplacementDialog(pending.value,
                    { confirmed += it; pending.value = null },
                    { dismissed += it; pending.value = null })
            }
        }
    }

    @Test fun keepViewingDismissesTheEngineDecisionWithoutConfirmingIt() {
        pending.value = ExperimentalPhotoReplacement("engine-ticket", ExperimentalPhotoReplacementKind.ENGINE,
            ExperimentalPhotoEngine.POSE)
        content()
        compose.onNodeWithText(title).assertIsDisplayed()
        compose.onNodeWithText("계속 보기").performClick()
        compose.onNodeWithText(title).assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(emptyList<String>(), confirmed)
            assertEquals(listOf("engine-ticket"), dismissed)
        }
    }

    @Test fun explicitPhotoConfirmationDeliversTheExactDecisionOnce() {
        pending.value = ExperimentalPhotoReplacement("photo-ticket", ExperimentalPhotoReplacementKind.PHOTO)
        content()
        compose.onNodeWithText("저장하지 않고 진행").performClick()
        compose.onNodeWithText(title).assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(listOf("photo-ticket"), confirmed)
            assertEquals(emptyList<String>(), dismissed)
        }
    }

    @Test fun dialogBackKeepsTheResultByDismissingTheRerunDecision() {
        pending.value = ExperimentalPhotoReplacement("run-ticket", ExperimentalPhotoReplacementKind.RUN)
        content()
        onView(isRoot()).inRoot(isDialog()).perform(ViewActions.pressBack())
        compose.onNodeWithText(title).assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(emptyList<String>(), confirmed)
            assertEquals(listOf("run-ticket"), dismissed)
        }
    }

    @Test fun existingDecisionIsRedisplayedAfterCompositionRestorationWithoutExecutingIt() {
        pending.value = ExperimentalPhotoReplacement("retained-ticket", ExperimentalPhotoReplacementKind.RUN)
        val restorer = StateRestorationTester(compose)
        content(restorer)
        restorer.emulateSavedInstanceStateRestore()
        compose.onNodeWithText(title).assertIsDisplayed()
        compose.runOnIdle { assertEquals(emptyList<String>(), confirmed) }
        compose.onNodeWithText("저장하지 않고 진행").performClick()
        compose.runOnIdle { assertEquals(listOf("retained-ticket"), confirmed) }
    }
}
