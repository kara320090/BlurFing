package com.blurfing.app.utils

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException
import java.util.UUID

class CameraFileProvider : FileProvider()

/** Grant the camera access to this output only; request a full-size file, not a thumbnail. */
class CameraCaptureContract : ActivityResultContracts.TakePicture() {
    override fun createIntent(context: Context, input: Uri): Intent =
        super.createIntent(context, input).apply {
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            clipData = ClipData.newRawUri("BlurFing camera output", input)
        }
}

object CameraCaptureFiles {
    private const val DIRECTORY = "camera-captures"
    private const val ROOT_NAME = "camera"
    private const val MAX_AGE_MS = 24 * 60 * 60 * 1000L
    private val fileNamePattern = Regex("capture-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.jpg")

    fun create(context: Context, uriForFile: (File) -> Uri = {
        FileProvider.getUriForFile(context, "${context.packageName}.camera", it)
    }): Uri {
        val directory = File(context.cacheDir, DIRECTORY)
        if (!directory.isDirectory && !directory.mkdirs()) throw IOException("Camera cache unavailable")
        val file = File(directory, "capture-${UUID.randomUUID()}.jpg")
        if (!file.createNewFile()) throw IOException("Camera output unavailable")
        return try {
            uriForFile(file)
        } catch (error: Exception) {
            file.delete()
            throw error
        }
    }

    /** Never resolve a caller-supplied URI outside our dedicated capture directory. */
    internal fun ownedFile(context: Context, uri: Uri): File? {
        if (uri.scheme != "content" || uri.authority != "${context.packageName}.camera" ||
            uri.query != null || uri.fragment != null) return null
        val segments = uri.pathSegments
        if (segments.size != 2 || segments[0] != ROOT_NAME || !fileNamePattern.matches(segments[1])) return null
        return try {
            val directory = File(context.cacheDir, DIRECTORY).canonicalFile
            File(directory, segments[1]).canonicalFile.takeIf { it.parentFile == directory }
        } catch (_: IOException) { null }
    }

    fun isOwned(context: Context, uri: Uri): Boolean = ownedFile(context, uri) != null

    fun hasOutput(context: Context, uri: Uri): Boolean =
        ownedFile(context, uri)?.let { it.isFile && it.length() > 0 } == true

    fun revoke(context: Context, uri: Uri) {
        if (!isOwned(context, uri)) return
        try {
            context.revokeUriPermission(uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        } catch (_: SecurityException) {
            Log.w("BlurFingCamera", "Could not revoke temporary camera permission")
        }
    }

    fun discard(context: Context, uri: Uri) {
        val file = ownedFile(context, uri) ?: return
        revoke(context, uri)
        if (file.exists() && !file.delete()) Log.w("BlurFingCamera", "Could not remove temporary camera output")
    }

    /** Recover abandoned files after a crash; keep a camera request restored from saved state. */
    fun removeExpired(context: Context, keepUri: Uri?, nowMillis: Long = System.currentTimeMillis()) {
        val keepFile = keepUri?.let { ownedFile(context, it) }
        val directory = File(context.cacheDir, DIRECTORY)
        directory.listFiles()?.forEach { file ->
            if (fileNamePattern.matches(file.name) && file.lastModified() < nowMillis - MAX_AGE_MS) {
                val uri = Uri.Builder().scheme("content").authority("${context.packageName}.camera")
                    .appendPath(ROOT_NAME).appendPath(file.name).build()
                val owned = ownedFile(context, uri)
                if (owned != null && owned != keepFile && owned.isFile) discard(context, uri)
            }
        }
    }
}
