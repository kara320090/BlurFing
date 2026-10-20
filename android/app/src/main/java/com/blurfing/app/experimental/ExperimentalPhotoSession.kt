package com.blurfing.app.experimental

import android.content.Context
import androidx.lifecycle.SavedStateHandle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.io.File
import java.util.UUID
import kotlin.coroutines.coroutineContext

/** Private immutable snapshots. Only a token, hashes and timestamp enter Android saved state. */
internal class ExperimentalPhotoSession(context: Context, private val state: SavedStateHandle) {
    private val root = File(context.applicationContext.cacheDir, "experimental-photo-drafts")
    private val json = Json { ignoreUnknownKeys = false }
    private val tokenPattern = Regex("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}")
    private val group=state.get<String>(GROUP)?.takeIf { tokenPattern.matches(it) }
        ?: UUID.randomUUID().toString().also { state[GROUP]=it }
    private val groupDirectory=File(root,group).canonicalFile.also { require(it.parentFile==root.canonicalFile) }
    data class Reference(val token: String, val created: Long, val sourceHash: String, val responseHash: String?)
    data class Restored(val source: ExperimentalPhotoUpload, val result: ValidatedExperimentalPhoto?, val savedId: String?)
    val hasSnapshot get() = state.get<String>(TOKEN) != null

    private fun directory(token: String): File {
        require(tokenPattern.matches(token))
        return File(groupDirectory, token).canonicalFile.also { require(it.parentFile == groupDirectory) }
    }
    suspend fun write(source: ExperimentalPhotoUpload, result: ValidatedExperimentalPhoto?): Reference {
        var createdDirectory: File?=null
        return try { withContext(Dispatchers.IO) {
        val dir = directory(UUID.randomUUID().toString())
        createdDirectory=dir
        val job=coroutineContext
        try {
            check(dir.mkdirs())
            source.verify { job.ensureActive() }
            File(dir, "source.png").outputStream().use { it.write(source.png) }
            coroutineContext.ensureActive()
            val responseHash = result?.recoveryResponse?.let { dto ->
                // Serialization is optional recovery work. Refuse a heap-expensive extra copy.
                val estimate=2L*(dto.imageBase64.length+dto.acceptedPermissionMask.imageBase64.length+dto.rejectedPermissionMask.imageBase64.length)+1024*1024
                ExperimentalPhotoMemory.requireAvailable(ExperimentalPhotoMemory.Plan(estimate,estimate))
                val bytes=json.encodeToString(dto).toByteArray(Charsets.UTF_8)
                require(bytes.size.toLong()<=ExperimentalPhotoRepository.MAX_RESPONSE_BYTES)
                File(dir,"response.json").outputStream().use { it.write(bytes) }
                ExperimentalPngCodec.hash(bytes)
            }
            coroutineContext.ensureActive()
            Reference(dir.name,System.currentTimeMillis(),source.sourceSha256,responseHash)
        } catch(e: Throwable) { dir.deleteRecursively();throw e }
        } } catch(e: Throwable) { createdDirectory?.deleteRecursively();throw e }
    }
    fun attach(reference: Reference) {
        state[TOKEN]=reference.token;state[CREATED]=reference.created
        state[SOURCE_HASH]=reference.sourceHash;state[RESPONSE_HASH]=reference.responseHash
        state[SAVED_ID]=null
        // Android may already have saved an older Bundle while the app is stopped.
        // Keep its immutable snapshot until explicit discard/expiry so background completion
        // cannot leave that OS-owned Bundle pointing at a deleted file.
    }
    fun markSaved(id: String) { if(hasSnapshot)state[SAVED_ID]=id }
    suspend fun restore(): Restored = withContext(Dispatchers.IO) {
        val job=coroutineContext
        val created=state.get<Long>(CREATED) ?: error("Missing timestamp")
        require(System.currentTimeMillis()-created in 0..MAX_AGE)
        val dir=directory(requireNotNull(state.get<String>(TOKEN)))
        fun read(name: String,limit: Long): ByteArray {
            val file=File(dir,name);require(file.isFile && file.length() in 1..limit)
            file.inputStream().use { input ->
                val output=java.io.ByteArrayOutputStream();val buffer=ByteArray(8192)
                while(true) { job.ensureActive();val n=input.read(buffer);if(n<0)break
                    require(output.size().toLong()+n<=limit);output.write(buffer,0,n) }
                return output.toByteArray()
            }
        }
        val sourceBytes=read("source.png",ExperimentalPhotoMemory.MAX_PNG_BYTES.toLong())
        require(ExperimentalPngCodec.hash(sourceBytes)==state.get<String>(SOURCE_HASH))
        val source=ExperimentalPhotoUpload.fromCanonicalPng(sourceBytes,{job.ensureActive()})
        val result=state.get<String>(RESPONSE_HASH)?.let { hash ->
            val bytes=read("response.json",ExperimentalPhotoRepository.MAX_RESPONSE_BYTES)
            require(ExperimentalPngCodec.hash(bytes)==hash)
            val text=bytes.toString(Charsets.UTF_8);ExperimentalJsonGuard.verify(text)
            val response=json.decodeFromString<ExperimentalPhotoResponse>(text)
            ExperimentalPhotoDecoder.decode(response,source,ExperimentalPhotoEngine.fromId(response.photoEngine),response.requestId,
                {job.ensureActive()}).also { it.recoveryResponse=null }
        }
        Restored(source,result,state.get<String>(SAVED_ID)?.takeIf { it==result?.requestId })
    }
    fun discard(token: String) { runCatching { directory(token).deleteRecursively() } }
    fun clear() {
        state.remove<String>(TOKEN)
        state.remove<Long>(CREATED);state.remove<String>(SOURCE_HASH);state.remove<String>(RESPONSE_HASH);state.remove<String>(SAVED_ID)
        runCatching { groupDirectory.deleteRecursively() }
    }
    suspend fun removeExpired() = withContext(Dispatchers.IO) {
        val current=state.get<String>(TOKEN)
        root.listFiles()?.filter { tokenPattern.matches(it.name) && it.isDirectory }?.forEach { owner ->
            if(owner.name!=group && System.currentTimeMillis()-owner.lastModified()>MAX_AGE && owner.canonicalFile.parentFile==root.canonicalFile)
                owner.deleteRecursively()
        }
        groupDirectory.listFiles()?.filter { tokenPattern.matches(it.name) && it.name!=current &&
            System.currentTimeMillis()-it.lastModified()>MAX_AGE }?.forEach { discard(it.name) }
    }
    companion object {
        const val TOKEN="photo-v2-snapshot"
        const val GROUP="photo-v2-session"
        private const val CREATED="photo-v2-created"
        private const val SOURCE_HASH="photo-v2-source-sha"
        private const val RESPONSE_HASH="photo-v2-response-sha"
        private const val SAVED_ID="photo-v2-saved-id"
        internal const val MAX_AGE=24L*60*60*1000
    }
}
