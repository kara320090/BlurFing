package com.blurfing.app

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.onRoot
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File

/** Own-app render artifacts from public synthetic workflow fixtures only. */
internal fun ComposeContentTestRule.captureDesignArtifact(name: String) {
    waitForIdle()
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    val output = File(context.getExternalFilesDir(null), "design-qa/$name.png").apply { parentFile!!.mkdirs() }
    onRoot().captureToImage().asAndroidBitmap().let { image ->
        output.outputStream().use { check(image.compress(Bitmap.CompressFormat.PNG, 100, it)) }
    }
}
