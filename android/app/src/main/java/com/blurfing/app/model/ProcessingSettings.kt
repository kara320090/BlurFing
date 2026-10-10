package com.blurfing.app.model

import android.content.Context
import com.blurfing.app.repository.BackendAddress

data class ProcessingSettings(
    val method: ProtectionMethod = ProtectionMethod.GAUSSIAN_BLUR,
    val strength: Float = 0.5f,
    val useServer: Boolean = false,
    val serverAddress: String = BackendAddress.EMULATOR_DEFAULT
)

class ProcessingSettingsStore(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences("processing-settings", Context.MODE_PRIVATE)

    fun load(): ProcessingSettings = try {
        ProcessingSettings(
            method = ProtectionMethod.fromApiValue(preferences.getString("method", "gaussian_blur").orEmpty()),
            strength = preferences.getFloat("strength", 0.5f).let {
                if (it.isFinite() && it in 0.1f..1f) it else 0.5f
            },
            useServer = preferences.getBoolean("use-server", false),
            serverAddress = preferences.getString("address", BackendAddress.EMULATOR_DEFAULT).orEmpty().take(2048)
        )
    } catch (_: ClassCastException) { ProcessingSettings() }

    fun save(settings: ProcessingSettings) {
        preferences.edit().putString("method", settings.method.apiValue)
            .putFloat("strength", settings.strength).putBoolean("use-server", settings.useServer)
            .putString("address", settings.serverAddress).apply()
    }
}
