package com.blurfing.app.experimental

/** Explicit full-resolution buffers; display previews are bounded separately. */
object ExperimentalPhotoMemory {
    const val MAX_PIXELS = 20_000_000L
    const val MAX_PNG_BYTES = 15 * 1024 * 1024
    const val HEADROOM = 32L * 1024 * 1024
    private const val PREVIEWS = 8L * 1024 * 1024
    // BAOS capacity <=16MiB + final PNG <=15MiB + IDAT buffers <=128KiB.
    private const val ENCODER = 32L * 1024 * 1024
    private const val PNG_STREAMS = 2L * 64 * 1024 // two simultaneous full-resolution row readers

    data class Plan(val peakBytes: Long, val additionalBytes: Long)
    fun dimensions(width: Int, height: Int): Long {
        val pixels = width.toLong() * height.toLong()
        require(width > 0 && height > 0 && pixels <= MAX_PIXELS) { "15MiB · 2,000만 화소 이하 사진만 지원합니다." }
        return pixels
    }
    fun upload(width: Int, height: Int): Plan {
        val n = dimensions(width, height)
        val extra = ENCODER + 16L*width + PREVIEWS + PNG_STREAMS
        return Plan(4*n + extra, extra)
    }
    fun importPhoto(width: Int, height: Int,inputBytes: Int=MAX_PNG_BYTES): Plan {
        val n = dimensions(width,height)
        require(inputBytes in 1..MAX_PNG_BYTES)
        // Raw orientation copy is released before encoding; source stores PNG, never a full Bitmap.
        val buffers = maxOf(8*n,4*n+ENCODER+PREVIEWS)+16L*maxOf(width,height)+PNG_STREAMS
        return Plan(buffers+inputBytes,buffers)
    }
    fun canonical(width: Int,height: Int,bytes: Int): Plan {
        dimensions(width,height);require(bytes in 1..MAX_PNG_BYTES)
        return Plan(bytes+PREVIEWS+16L*width+PNG_STREAMS,PREVIEWS+16L*width+PNG_STREAMS)
    }
    fun decode(width: Int, height: Int, uploadBytes: Int, returnedPngBytes: Int, base64Chars: Long): Plan {
        val n = dimensions(width,height)
        require(uploadBytes in 1..MAX_PNG_BYTES && returnedPngBytes in 1..MAX_PNG_BYTES)
        val masks = 2*((n+7)/8)
        val extra = 4*n + returnedPngBytes + MAX_PNG_BYTES + masks + 24L*width + PREVIEWS + PNG_STREAMS
        // Mask PNGs are streamed into compact bits: no full mask Bitmap/IntArray.
        return Plan(uploadBytes + 2*base64Chars + extra, extra)
    }
    fun responseRead(width: Int, height: Int, uploadBytes: Int, responseBytes: Long): Plan {
        val n = dimensions(width,height)
        require(responseBytes in 0..64L*1024*1024)
        val extra = 3*responseBytes + 8L*1024*1024
        return Plan(uploadBytes + PREVIEWS + extra, extra)
    }
    fun requireAvailable(plan: Plan, maxHeap: Long = Runtime.getRuntime().maxMemory(),
                         usedHeap: Long = Runtime.getRuntime().totalMemory()-Runtime.getRuntime().freeMemory()) {
        if (plan.peakBytes > maxHeap-HEADROOM || plan.additionalBytes > maxHeap-usedHeap-HEADROOM)
            throw ExperimentalPhotoException("메모리가 부족해 원본을 유지했습니다. 다른 앱을 정리한 뒤 다시 시도해 주세요.")
    }
}

class CompactPermissionMask(val width: Int, val height: Int) {
    val size = ExperimentalPhotoMemory.dimensions(width,height).toInt()
    private val bytes = ByteArray((size+7)/8)
    operator fun get(index: Int): Boolean {
        require(index in 0 until size)
        return (bytes[index ushr 3].toInt() and (1 shl (index and 7))) != 0
    }
    internal fun set(index: Int) { bytes[index ushr 3] = (bytes[index ushr 3].toInt() or (1 shl (index and 7))).toByte() }
    val storageBytes: Int get() = bytes.size
}
