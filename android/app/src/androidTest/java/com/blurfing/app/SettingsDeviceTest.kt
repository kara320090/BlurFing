package com.blurfing.app

import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.UiState
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class SettingsDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val vm get() = ViewModelProvider(compose.activity)[BlurFingViewModel::class.java]

    @Test fun settingsRemainAfterLeavingScreenAndActivityRecreation() {
        val source = File(compose.activity.cacheDir, "settings-synthetic.png")
        source.outputStream().use {
            Bitmap.createBitmap(16, 16, Bitmap.Config.ARGB_8888).apply {
                compress(Bitmap.CompressFormat.PNG, 100, it); recycle()
            }
        }
        try {
            compose.runOnUiThread {
                vm.updateSettings(ProcessingSettings())
                vm.onImageSelected(Uri.fromFile(source), compose.activity)
            }
            compose.waitUntil(10_000) { vm.uiState.value is UiState.Ready }
            compose.onNodeWithText("보호 설정 (BF-04)").performClick()
            compose.onNode(isToggleable()).performClick()
            compose.onNodeWithText("서버 주소").performTextReplacement("https://example.org")
            compose.onNodeWithContentDescription("뒤로가기").performClick()
            compose.onNodeWithText("보호 설정 (BF-04)").performClick()
            compose.onNodeWithText("https://example.org").assertExists()
            compose.activityRule.scenario.recreate()
            compose.onNodeWithText("https://example.org").assertExists()
            compose.onNode(isToggleable()).assertIsOn()
            compose.runOnIdle { assertFalse((vm.uiState.value as UiState.Ready).isProcessing) }
        } finally {
            compose.runOnUiThread { vm.resetToIdle(); vm.updateSettings(ProcessingSettings()) }
            source.delete()
        }
    }
}
