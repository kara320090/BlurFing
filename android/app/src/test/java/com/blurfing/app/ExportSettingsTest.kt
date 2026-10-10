package com.blurfing.app

import com.blurfing.app.model.*
import com.blurfing.app.viewmodel.BlurFingViewModel
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28])
class ExportSettingsTest {
    @Test fun jpegSettingsSurviveStoreReload() {
        val context=RuntimeEnvironment.getApplication()
        val settings=ProcessingSettings(exportFormat=ExportFormat.JPEG,jpegQuality=85)
        ProcessingSettingsStore(context).save(settings)
        assertEquals(settings,ProcessingSettingsStore(context).load())
    }
    @Test fun corruptFormatAndQualityFallbackAndInvalidUpdateRejected() {
        val context=RuntimeEnvironment.getApplication()
        context.getSharedPreferences("processing-settings",0).edit()
            .putString("export-format","UNSUPPORTED").putInt("jpeg-quality",-100).commit()
        val loaded=ProcessingSettingsStore(context).load()
        assertEquals(ExportFormat.PNG,loaded.exportFormat); assertEquals(80,loaded.jpegQuality)
        val vm=BlurFingViewModel()
        vm.updateSettings(ProcessingSettings(jpegQuality=200))
        assertEquals(95,vm.settings.value.jpegQuality)
    }
}
