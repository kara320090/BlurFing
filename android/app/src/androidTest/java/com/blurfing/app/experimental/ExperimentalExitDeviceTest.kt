package com.blurfing.app.experimental

import android.graphics.Bitmap
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.StateRestorationTester
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.Espresso.pressBack
import androidx.test.espresso.action.ViewActions
import androidx.test.espresso.matcher.RootMatchers.isDialog
import androidx.test.espresso.matcher.ViewMatchers.isRoot
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.blurfing.app.model.ExperimentalPhotoPresentation
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises the actual exit guard with synthetic display state, not an AI performance fixture. */
@RunWith(AndroidJUnit4::class)
class ExperimentalExitDeviceTest {
    @get:Rule val compose = createComposeRule()
    private val state = mutableStateOf(ExperimentalPhotoState())
    private var exits = 0
    private var cancels = 0
    private val unsavedTitle = "저장하지 않은 결과가 있습니다"

    private fun result(canSave: Boolean = true): ValidatedExperimentalPhoto {
        val bitmap = Bitmap.createBitmap(1, 1, Bitmap.Config.ARGB_8888)
        return ValidatedExperimentalPhoto("synthetic-exit", ExperimentalPhotoEngine.NATIVE, bitmap,
            byteArrayOf(), CompactPermissionMask(1, 1), CompactPermissionMask(1, 1),
            ExperimentalPhotoPresentation("합성 결과", "화면 상태 시험", canSave, !canSave),
            1, if (canSave) 1 else 0, if (canSave) 0 else 1, if (canSave) 1 else 0,
            emptyList(), bitmap, bitmap)
    }

    private fun content(restorer: StateRestorationTester = StateRestorationTester(compose)) {
        restorer.setContent {
            MaterialTheme {
                val request = rememberExperimentalExitRequest(state.value, { cancels++ }, { exits++ })
                Button(onClick = request) { Text("일반 화면으로 돌아가기") }
            }
        }
    }

    @Test fun returnButtonCanKeepUnsavedResultOrExplicitlyDiscardIt() {
        state.value = ExperimentalPhotoState(result = result())
        content()
        compose.onNodeWithText("일반 화면으로 돌아가기").performClick()
        compose.onNodeWithText(unsavedTitle).assertIsDisplayed()
        compose.onNodeWithText("계속 보기").performClick()
        compose.onNodeWithText(unsavedTitle).assertDoesNotExist()
        compose.runOnIdle { assertEquals(0, exits); assertEquals(0, cancels) }
        compose.onNodeWithText("일반 화면으로 돌아가기").performClick()
        compose.onNodeWithText("저장하지 않고 종료").performClick()
        compose.runOnIdle { assertEquals(1, exits); assertEquals(1, cancels) }
    }

    @Test fun systemBackConfirmationRestoresAndDialogBackKeepsResult() {
        state.value = ExperimentalPhotoState(result = result())
        val restorer = StateRestorationTester(compose)
        content(restorer)
        pressBack()
        compose.onNodeWithText(unsavedTitle).assertIsDisplayed()
        restorer.emulateSavedInstanceStateRestore()
        compose.onNodeWithText(unsavedTitle).assertIsDisplayed()
        onView(isRoot()).inRoot(isDialog()).perform(ViewActions.pressBack())
        compose.onNodeWithText(unsavedTitle).assertDoesNotExist()
        compose.runOnIdle { assertEquals(0, exits); assertEquals(0, cancels) }
    }

    @Test fun workCompletionUpdatesPromptAndVerifiedSaveClosesItWithoutExiting() {
        state.value = ExperimentalPhotoState(busy = true)
        content()
        compose.onNodeWithText("일반 화면으로 돌아가기").performClick()
        compose.onNodeWithText("실험을 종료할까요?").assertIsDisplayed()
        val result = result()
        compose.runOnIdle { state.value = ExperimentalPhotoState(result = result) }
        compose.onNodeWithText(unsavedTitle).assertIsDisplayed()
        compose.onNodeWithText("실험을 종료할까요?").assertDoesNotExist()
        compose.runOnIdle { state.value = state.value.copy(savedResultRequestId = result.requestId) }
        compose.onNodeWithText(unsavedTitle).assertDoesNotExist()
        compose.runOnIdle { state.value = ExperimentalPhotoState(result = result) }
        compose.onNodeWithText(unsavedTitle).assertDoesNotExist()
        compose.runOnIdle { assertEquals(0, exits); assertEquals(0, cancels) }
    }

    @Test fun idleAndUnchangedOriginalReturnExitWithoutDiscardConfirmation() {
        content()
        compose.onNodeWithText("일반 화면으로 돌아가기").performClick()
        compose.runOnIdle { assertEquals(1, exits); state.value = ExperimentalPhotoState(result = result(false)) }
        compose.onNodeWithText("일반 화면으로 돌아가기").performClick()
        compose.onNodeWithText(unsavedTitle).assertDoesNotExist()
        compose.runOnIdle { assertEquals(2, exits); assertEquals(0, cancels) }
    }
}
