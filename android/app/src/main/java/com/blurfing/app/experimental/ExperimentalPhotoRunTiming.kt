package com.blurfing.app.experimental

/** Process-local monotonic evidence. Never restored across reboot/process death. */
data class ExperimentalPhotoRunTiming(
    val requestId: String,
    val startedAtMs: Long,
    val includesImport: Boolean,
    val resultAtMs: Long? = null,
    val savedAtMs: Long? = null
) {
    init {
        require(requestId.isNotBlank() && startedAtMs >= 0)
        require(resultAtMs == null || resultAtMs >= startedAtMs)
        require(savedAtMs == null || (resultAtMs != null && savedAtMs >= resultAtMs))
    }
    val resultElapsedMs: Long? get() = resultAtMs?.minus(startedAtMs)
    val savedElapsedMs: Long? get() = savedAtMs?.minus(startedAtMs)
    val withinDemoTarget: Boolean? get() = savedElapsedMs?.let { it <= 120_000 }
    fun resultReady(now: Long) = if (resultAtMs != null) this else copy(resultAtMs = now)
    fun saved(now: Long) = if (savedAtMs != null) this else copy(savedAtMs = now)
}
