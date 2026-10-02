package com.blurfing.app.utils

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.lifecycle.SavedStateHandle
import com.blurfing.app.model.NormalizedRegion
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

/** Bundle contains only an opaque cache token and coordinates, never full photo bytes. */
class DraftSession(context: Context, private val state: SavedStateHandle) {
    private val directory = File(context.applicationContext.cacheDir, "editing-drafts")
    private val namePattern = Regex("[a-f0-9-]{36}\\.png")
    val hasDraft: Boolean get() = state.get<String>("draft-file") != null

    data class Restored(val bitmap: Bitmap, val regions: List<NormalizedRegion>)

    private fun file(name: String): File {
        require(namePattern.matches(name))
        val candidate = File(directory, name).canonicalFile
        require(candidate.parentFile == directory.canonicalFile)
        return candidate
    }

    suspend fun create(bitmap: Bitmap): String {
        val name = "${UUID.randomUUID()}.png"
        try {
            withContext(Dispatchers.IO) {
                check(directory.isDirectory || directory.mkdirs())
                file(name).outputStream().use { check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
                check(file(name).length() <= MAX_BYTES)
            }
            return name
        } catch (error: Exception) {
            discard(name)
            throw error
        }
    }

    fun attach(name: String, regions: List<NormalizedRegion>) {
        val previous = state.get<String>("draft-file")
        state["draft-file"] = name
        state["draft-created-at"] = System.currentTimeMillis()
        updateRegions(regions)
        if (previous != name && previous != null) discard(previous)
    }

    fun updateRegions(regions: List<NormalizedRegion>) {
        if (!hasDraft) return
        state["draft-regions"] = regions.flatMap { listOf(it.x, it.y, it.width, it.height) }.toFloatArray()
    }

    suspend fun restore(): Restored {
        val name = state.get<String>("draft-file") ?: error("Missing draft")
        val createdAt = state.get<Long>("draft-created-at") ?: 0L
        val coordinates = state.get<FloatArray>("draft-regions") ?: error("Missing coordinates")
        require(coordinates.size % 4 == 0)
        val regions = coordinates.toList().chunked(4).map { NormalizedRegion(it[0], it[1], it[2], it[3]) }
        var allocated: Bitmap? = null
        try {
            return withContext(Dispatchers.IO) {
                require(System.currentTimeMillis() - createdAt in 0..MAX_AGE_MS)
                val source = file(name)
                require(source.isFile && source.length() in 1..MAX_BYTES)
                val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(source.path, options)
                require(options.outWidth > 0 && options.outHeight > 0 &&
                    options.outWidth.toLong() * options.outHeight <= 20_000_000)
                val bitmap = requireNotNull(BitmapFactory.decodeFile(source.path))
                allocated = bitmap
                Restored(bitmap, regions)
            }
        } catch (error: Exception) {
            allocated?.recycle()
            throw error
        }
    }

    fun clear() {
        val name = state.remove<String>("draft-file")
        state.remove<Long>("draft-created-at")
        state.remove<FloatArray>("draft-regions")
        if (name != null) discard(name)
    }

    fun discard(name: String) { runCatching { file(name).delete() } }

    suspend fun removeExpired() {
        val active = state.get<String>("draft-file")
        withContext(Dispatchers.IO) {
            directory.listFiles()?.filter { it.name != active && namePattern.matches(it.name) &&
                System.currentTimeMillis() - it.lastModified() > MAX_AGE_MS }
                ?.forEach { discard(it.name) }
        }
    }

    companion object {
        private const val MAX_BYTES = 100L * 1024 * 1024
        private const val MAX_AGE_MS = 24L * 60 * 60 * 1000
    }
}
