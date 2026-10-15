package com.blurfing.app.experimental

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID
import java.security.MessageDigest
import kotlin.coroutines.coroutineContext

data class ExperimentalPhotoState(
    val source: ExperimentalPhotoUpload?=null,val result: ValidatedExperimentalPhoto?=null,
    val engine: ExperimentalPhotoEngine=ExperimentalPhotoEngine.NATIVE,
    val serverAddress: String=EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT,
    val busy: Boolean=false,val importing: Boolean=false,val saving: Boolean=false,
    val awaitingSave: Boolean=false,val message: String?=null
)

/** Independent request lifecycle; old v1 jobs/settings/results are never reused. */
class ExperimentalPhotoViewModel(
    private val serviceFactory: (String)->ExperimentalPhotoService={ ExperimentalPhotoRepository(it) },
    private val loader: suspend (Context,Uri)->ExperimentalPhotoUpload={ context,uri -> ExperimentalPhotoUpload.load(context,uri) }
): ViewModel() {
    private val mutable=MutableStateFlow(ExperimentalPhotoState())
    val state: StateFlow<ExperimentalPhotoState> = mutable.asStateFlow()
    @Volatile private var generation=0L
    private var task: Job?=null
    private var saveTask: Job?=null
    private var service: ExperimentalPhotoService?=null
    private var requestId: String?=null
    private data class PendingSave(val generation: Long,val result: ValidatedExperimentalPhoto)
    private var pendingSave: PendingSave?=null
    private var outstandingSaveTicket: String?=null

    fun setAddress(value: String) { if(!mutable.value.busy)mutable.value=mutable.value.copy(serverAddress=value.take(2048),message=null) }
    fun setEngine(value: ExperimentalPhotoEngine) { if(!mutable.value.busy && !mutable.value.importing && !mutable.value.saving) {
        invalidate();mutable.value=mutable.value.copy(engine=value,result=null,message=null,awaitingSave=false)
    } }
    private fun invalidate() {
        generation++;requestId?.let { service?.cancel(it) };task?.cancel();saveTask?.cancel()
        requestId=null;task=null;saveTask=null;service=null;pendingSave=null
    }
    fun select(context: Context,uri: Uri?) {
        if(uri==null)return
        invalidate();val token=generation
        mutable.value=mutable.value.copy(source=null,result=null,busy=false,importing=true,saving=false,awaitingSave=false,message=null)
        task=viewModelScope.launch {
            try {
                val source=loader(context.applicationContext,uri);coroutineContext.ensureActive()
                if(token==generation)mutable.value=mutable.value.copy(source=source,importing=false)
            } catch(e: CancellationException) { throw e }
            catch(_: OutOfMemoryError) { if(token==generation)mutable.value=mutable.value.copy(importing=false,message="메모리가 부족해 사진을 불러오지 못했습니다. 원본 파일은 변경되지 않았습니다.") }
            catch(e: Exception) { if(token==generation)mutable.value=mutable.value.copy(importing=false,message=if(e is ExperimentalPhotoException)e.message else "사진을 불러오지 못했습니다. 15MiB · 2,000만 화소 제한과 방향 정보를 확인해 주세요.") }
        }
    }
    fun start() {
        val state=mutable.value;val source=state.source ?: return
        if(state.busy || state.importing || state.saving)return
        invalidate();val token=generation;val id=UUID.randomUUID().toString()
        requestId=id
        mutable.value=state.copy(result=null,busy=true,awaitingSave=false,message=null)
        task=viewModelScope.launch {
            try {
                val api=serviceFactory(state.serverAddress);service=api
                val result=api.protect(source,state.engine,id);coroutineContext.ensureActive()
                require(result.requestId==id && result.engine==state.engine)
                if(token==generation)mutable.value=mutable.value.copy(result=result,busy=false)
            } catch(e: CancellationException) { throw e }
            catch(_: OutOfMemoryError) { if(token==generation)mutable.value=mutable.value.copy(busy=false,message="메모리가 부족해 처리를 중단했습니다. 선택한 원본은 유지됩니다.") }
            catch(e: Exception) { if(token==generation)mutable.value=mutable.value.copy(busy=false,message=if(e is ExperimentalPhotoException)e.message else "AI 결과의 픽셀·마스크 계약을 확인하지 못했습니다. 선택한 원본은 유지됩니다.") }
            finally { if(token==generation) { requestId=null;service=null } }
        }
    }
    fun cancel() { invalidate();mutable.value=mutable.value.copy(busy=false,importing=false,saving=false,awaitingSave=false,message="작업을 취소했습니다. 선택한 원본은 유지됩니다.") }
    fun prepareSave(): String? {
        val s=mutable.value;val result=s.result ?: return null
        if(s.busy || s.saving || s.awaitingSave || outstandingSaveTicket!=null || !result.presentation.canSaveChangedCopy)return null
        val ticket=UUID.randomUUID().toString();outstandingSaveTicket=ticket
        pendingSave=PendingSave(generation,result);mutable.value=s.copy(awaitingSave=true,message=null);return ticket
    }
    fun finishSave(context: Context,uri: Uri?,ticket: String?) {
        if(ticket==null || ticket!=outstandingSaveTicket)return
        outstandingSaveTicket=null
        val pending=pendingSave;pendingSave=null
        mutable.value=mutable.value.copy(awaitingSave=false)
        if(uri==null || pending==null || pending.generation!=generation || mutable.value.result!==pending.result)return
        mutable.value=mutable.value.copy(saving=true)
        val app=context.applicationContext
        saveTask=viewModelScope.launch {
            var complete=false
            try {
                withContext(Dispatchers.IO) {
                    coroutineContext.ensureActive()
                    require(pending.generation==generation)
                    app.contentResolver.openOutputStream(uri,"w")?.use { output ->
                        val bytes=pending.result.png
                        var at=0
                        while(at<bytes.size) { coroutineContext.ensureActive();require(pending.generation==generation)
                            val n=minOf(8192,bytes.size-at);output.write(bytes,at,n);at+=n
                        };output.flush()
                    } ?: throw ExperimentalPhotoException("저장할 파일을 열 수 없습니다.")
                    val digest=MessageDigest.getInstance("SHA-256");var count=0L
                    app.contentResolver.openInputStream(uri)?.use { input ->
                        val buffer=ByteArray(8192)
                        while(true) { coroutineContext.ensureActive();require(pending.generation==generation)
                            val n=input.read(buffer);if(n<0)break;count+=n;require(count<=pending.result.png.size)
                            digest.update(buffer,0,n)
                        }
                    } ?: throw ExperimentalPhotoException("저장한 복사본을 확인할 수 없습니다.")
                    require(count==pending.result.png.size.toLong() && ExperimentalPngCodec.hex(digest.digest())==ExperimentalPngCodec.hash(pending.result.png))
                };complete=true
                if(pending.generation==generation)mutable.value=mutable.value.copy(saving=false,message="검증된 반환 PNG 복사본을 저장했습니다. 전체 지문 보호는 보장되지 않습니다.")
            } catch(e: CancellationException) { throw e }
            catch(_: Exception) { if(pending.generation==generation)mutable.value=mutable.value.copy(saving=false,message="복사본을 저장하지 못했습니다. 원본과 비교 결과는 유지됩니다.") }
            finally {
                if(!complete) try { DocumentsContract.deleteDocument(app.contentResolver,uri) } catch(_: Exception) { /* The provider may not support removing the incomplete new document. */ }
            }
        }
    }
    override fun onCleared() { invalidate();super.onCleared() }
}
