package com.blurfing.app.model

/** Monotonic elapsed durations of this app request; not AI or sensor performance. */
data class ProcessingTiming(val encodeMs: Long, val requestMs: Long, val decodeMs: Long, val totalMs: Long) {
    companion object {
        fun between(start: Long, encoded: Long, received: Long, decoded: Long): ProcessingTiming {
            require(start >= 0 && start <= encoded && encoded <= received && received <= decoded)
            return ProcessingTiming(encoded - start, received - encoded, decoded - received, decoded - start)
        }
    }
}

data class ProcessingRunInfo(val method: ProtectionMethod, val strength: Float, val useServer: Boolean)
