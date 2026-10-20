package com.blurfing.app.experimental

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.lifecycle.ViewModel
import androidx.lifecycle.SavedStateHandle
import com.blurfing.app.utils.CameraCaptureFiles
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.yield
import kotlinx.coroutines.withContext
import java.util.UUID
import java.security.MessageDigest
import kotlin.coroutines.coroutineContext

data class ExperimentalPhotoState(
    val source: ExperimentalPhotoUpload?=null,val result: ValidatedExperimentalPhoto?=null,
    val engine: ExperimentalPhotoEngine=ExperimentalPhotoEngine.NATIVE,
    val serverAddress: String=EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT,
    val busy: Boolean=false,val importing: Boolean=false,val saving: Boolean=false,
    val awaitingSave: Boolean=false,val message: String?=null,
    val savedResultRequestId: String?=null,
    val replacement: ExperimentalPhotoReplacement?=null,
    val checkingServer: Boolean=false, val readiness: ExperimentalServerReadiness?=null,
    val sharing: Boolean=false, val pendingShare: ExperimentalPhotoShare?=null,
    val recoveryWarning: String?=null
) {
    val hasActiveWork: Boolean get() = busy || importing || saving || awaitingSave || checkingServer || sharing || pendingShare!=null
    val hasUnsavedResult: Boolean get() = result?.let {
        it.presentation.canSaveChangedCopy && it.requestId != savedResultRequestId
    } == true
    val requiresExitConfirmation: Boolean get() = hasActiveWork || hasUnsavedResult
}

/** Independent request lifecycle; old v1 jobs/settings/results are never reused. */
class ExperimentalPhotoViewModel(
    private val serviceFactory: (String)->ExperimentalPhotoService={ ExperimentalPhotoRepository(it) },
    private val loader: suspend (Context,Uri)->ExperimentalPhotoUpload={ context,uri -> ExperimentalPhotoUpload.load(context,uri) },
    private val savedState: SavedStateHandle=SavedStateHandle()
): ViewModel() {
    private val mutable=MutableStateFlow(ExperimentalPhotoState())
    val state: StateFlow<ExperimentalPhotoState> = mutable.asStateFlow()
    @Volatile private var generation=0L
    private var task: Job?=null
    private var saveTask: Job?=null
    private var shareTask: Job?=null
    private var app: Context?=null
    private var settings: ExperimentalPhotoSettings?=null
    private var session: ExperimentalPhotoSession?=null
    private var service: ExperimentalPhotoService?=null
    private var requestId: String?=null
    private data class PendingSave(val generation: Long,val result: ValidatedExperimentalPhoto)
    private var pendingSave: PendingSave?=null
    private var outstandingSaveTicket: String?=null
    private sealed interface ReplacementAction {
        data class Engine(val engine: ExperimentalPhotoEngine): ReplacementAction
        data class Photo(val app: Context, val uri: Uri): ReplacementAction
        data object Run: ReplacementAction
    }
    private data class PendingReplacement(val token: String, val generation: Long,
        val result: ValidatedExperimentalPhoto, val action: ReplacementAction)
    private var pendingReplacement: PendingReplacement?=null

    fun initialize(context: Context) {
        if(app!=null)return
        app=context.applicationContext
        settings=ExperimentalPhotoSettings(context)
        val stored=settings!!.load()
        mutable.value=mutable.value.copy(serverAddress=stored.address,engine=stored.engine)
        val cache=ExperimentalPhotoSession(context,savedState);session=cache
        viewModelScope.launch { cache.removeExpired() }
        if(!cache.hasSnapshot)return
        val token=generation
        mutable.value=mutable.value.copy(importing=true)
        task=viewModelScope.launch {
            try {
                val restored=cache.restore();coroutineContext.ensureActive()
                if(token==generation) {
                    mutable.value=mutable.value.copy(source=restored.source,result=restored.result,
                        engine=restored.result?.engine ?: mutable.value.engine,importing=false,
                        savedResultRequestId=restored.savedId,
                        message="이전 사진과 검증 가능한 결과를 복원했습니다. 중단된 업로드·저장·공유는 자동 재실행하지 않습니다.")
                    persistSettings()
                }
            } catch(e: CancellationException) { throw e }
            catch(_: Exception) { if(token==generation) { cache.clear();mutable.value=mutable.value.copy(importing=false,
                message="이전 임시 작업을 복원하지 못했습니다. 사진을 다시 선택해 주세요. 원본 파일은 유지됩니다.") } }
            catch(_: OutOfMemoryError) { if(token==generation) { cache.clear();mutable.value=mutable.value.copy(importing=false,
                message="메모리가 부족해 이전 작업을 복원하지 못했습니다. 사진을 다시 선택해 주세요.") } }
        }
    }
    private fun persistSettings() { mutable.value.let { settings?.save(it.serverAddress,it.engine) } }
    private suspend fun checkpoint(source: ExperimentalPhotoUpload,result: ValidatedExperimentalPhoto?,token: Long) {
        val cache=session ?: return
        try {
            val reference=cache.write(source,result)
            if(token==generation) { cache.attach(reference);mutable.value=mutable.value.copy(recoveryWarning=null) }
            else cache.discard(reference.token)
        } catch(e: CancellationException) { throw e }
        catch(_: Exception) { if(token==generation)mutable.value=mutable.value.copy(recoveryWarning="임시 복원 사본을 만들지 못했습니다. 앱을 닫기 전에 결과를 저장해 주세요.") }
        catch(_: OutOfMemoryError) { if(token==generation)mutable.value=mutable.value.copy(recoveryWarning="메모리가 부족해 임시 복원 사본을 만들지 못했습니다. 앱을 닫기 전에 결과를 저장해 주세요.") }
        finally { result?.recoveryResponse=null }
    }
    fun setAddress(value: String) {
        if(!mutable.value.hasActiveWork && pendingReplacement==null) {
            if(value==mutable.value.serverAddress)return
            mutable.value=mutable.value.copy(serverAddress=value.take(2048),message=null,readiness=null)
            persistSettings()
        }
    }
    fun checkServer() {
        val state=mutable.value
        if(state.hasActiveWork || pendingReplacement!=null)return
        val token=generation
        mutable.value=state.copy(checkingServer=true,readiness=null,message=null)
        task=viewModelScope.launch {
            try {
                val ready=serviceFactory(state.serverAddress).readiness()
                coroutineContext.ensureActive();ready.verify()
                if(token==generation)mutable.value=mutable.value.copy(checkingServer=false,readiness=ready,
                    message=if(state.engine.id in ready.photoEngines)"선택한 엔진의 서버 설정이 확인됐습니다. 실제 사진 처리·보호 성능 확인은 별도입니다."
                        else "선택한 엔진이 서버에 구성되어 있지 않습니다. 사용할 엔진을 선택하거나 서버 구성을 확인해 주세요.")
            } catch(e: CancellationException) { throw e }
            catch(e: Exception) { if(token==generation)mutable.value=mutable.value.copy(checkingServer=false,
                message=if(e is ExperimentalPhotoException || e is IllegalArgumentException)e.message else "사진 AI 서버의 준비 상태를 확인하지 못했습니다.") }
        }
    }
    fun setEngine(value: ExperimentalPhotoEngine) {
        val state=mutable.value
        if(value==state.engine || state.hasActiveWork || deferReplacement(ReplacementAction.Engine(value)))return
        changeEngine(value)
    }
    private fun changeEngine(value: ExperimentalPhotoEngine) {
        invalidate();mutable.value=mutable.value.copy(engine=value,result=null,message=null,awaitingSave=false,savedResultRequestId=null)
        persistSettings()
        session?.clear()
        mutable.value.source?.let { source -> val token=generation;task=viewModelScope.launch { checkpoint(source,null,token) } }
    }
    /** Keep the result until one decision for this exact generation is confirmed. */
    private fun deferReplacement(action: ReplacementAction): Boolean {
        if(pendingReplacement!=null)return true
        val state=mutable.value
        if(!state.hasUnsavedResult)return false
        val token=UUID.randomUUID().toString()
        pendingReplacement=PendingReplacement(token,generation,state.result!!,action)
        val kind=when(action) {
            is ReplacementAction.Engine -> ExperimentalPhotoReplacementKind.ENGINE
            is ReplacementAction.Photo -> ExperimentalPhotoReplacementKind.PHOTO
            ReplacementAction.Run -> ExperimentalPhotoReplacementKind.RUN
        }
        mutable.value=state.copy(replacement=ExperimentalPhotoReplacement(token,kind,
            (action as? ReplacementAction.Engine)?.engine))
        return true
    }
    fun dismissReplacement(token: String) {
        if(token!=pendingReplacement?.token)return
        (pendingReplacement?.action as? ReplacementAction.Photo)?.let { CameraCaptureFiles.discard(it.app,it.uri) }
        pendingReplacement=null;mutable.value=mutable.value.copy(replacement=null)
    }
    fun confirmReplacement(token: String) {
        val pending=pendingReplacement ?: return
        if(token!=pending.token)return
        pendingReplacement=null;mutable.value=mutable.value.copy(replacement=null)
        val state=mutable.value
        if(pending.generation!=generation || state.result!==pending.result || state.hasActiveWork)return
        when(val action=pending.action) {
            is ReplacementAction.Engine -> changeEngine(action.engine)
            is ReplacementAction.Photo -> loadSelected(action.app,action.uri)
            ReplacementAction.Run -> runSelected()
        }
    }
    private fun invalidate() {
        generation++;requestId?.let { service?.cancel(it) };task?.cancel();saveTask?.cancel();shareTask?.cancel()
        (pendingReplacement?.action as? ReplacementAction.Photo)?.let { CameraCaptureFiles.discard(it.app,it.uri) }
        app?.let { context -> mutable.value.pendingShare?.let { ExperimentalPhotoShareFiles.discard(context,it) } }
        requestId=null;task=null;saveTask=null;service=null;pendingSave=null
        pendingReplacement=null;mutable.value=mutable.value.copy(replacement=null,sharing=false,pendingShare=null,checkingServer=false)
    }
    fun select(context: Context,uri: Uri?) {
        if(uri==null)return
        val state=mutable.value
        if(state.importing || state.saving || state.awaitingSave || state.checkingServer || state.sharing || state.pendingShare!=null) {
            CameraCaptureFiles.discard(context,uri);return
        }
        pendingReplacement?.let { pending ->
            if((pending.action as? ReplacementAction.Photo)?.uri!=uri)CameraCaptureFiles.discard(context,uri)
            return
        }
        if(deferReplacement(ReplacementAction.Photo(context.applicationContext,uri)))return
        loadSelected(context.applicationContext,uri)
    }
    private fun loadSelected(context: Context,uri: Uri) {
        invalidate();val token=generation
        session?.clear()
        mutable.value=mutable.value.copy(source=null,result=null,busy=false,importing=true,saving=false,awaitingSave=false,message=null,savedResultRequestId=null)
        task=viewModelScope.launch {
            try {
                val source=loader(context.applicationContext,uri);coroutineContext.ensureActive()
                checkpoint(source,null,token)
                if(token==generation) {
                    mutable.value=mutable.value.copy(source=source,importing=false)
                    if(mutable.value.engine==ExperimentalPhotoEngine.SYNTHETIC) viewModelScope.launch {
                        // Let import cleanup finish. A replacement, cancellation or engine
                        // change invalidates this exact pending automatic request.
                        yield()
                        if(token==generation && mutable.value.source===source &&
                            mutable.value.engine==ExperimentalPhotoEngine.SYNTHETIC) start()
                    }
                }
            } catch(e: CancellationException) { throw e }
            catch(_: OutOfMemoryError) { if(token==generation)mutable.value=mutable.value.copy(importing=false,message="메모리가 부족해 사진을 불러오지 못했습니다. 원본 파일은 변경되지 않았습니다.") }
            catch(e: Exception) { if(token==generation)mutable.value=mutable.value.copy(importing=false,message=if(e is ExperimentalPhotoException)e.message else "사진을 불러오지 못했습니다. 15MiB · 2,000만 화소 제한과 방향 정보를 확인해 주세요.") }
            finally { CameraCaptureFiles.discard(context,uri) }
        }
    }
    fun start() {
        val state=mutable.value
        if(state.source==null || state.hasActiveWork || deferReplacement(ReplacementAction.Run))return
        runSelected()
    }
    private fun runSelected() {
        val state=mutable.value;val source=state.source ?: return
        if(state.readiness?.let { state.engine.id !in it.photoEngines }==true) {
            mutable.value=state.copy(message="선택한 엔진이 서버에 구성되어 있지 않습니다. 엔진을 선택하고 연결을 다시 확인해 주세요.");return
        }
        invalidate();val token=generation;val id=UUID.randomUUID().toString()
        requestId=id
        session?.clear()
        mutable.value=state.copy(result=null,busy=true,awaitingSave=false,message=null,savedResultRequestId=null)
        task=viewModelScope.launch {
            try {
                checkpoint(source,null,token)
                val api=serviceFactory(state.serverAddress);service=api
                val result=api.protect(source,state.engine,id);coroutineContext.ensureActive()
                require(result.requestId==id && result.engine==state.engine)
                checkpoint(source,result,token)
                if(token==generation)mutable.value=mutable.value.copy(result=result,busy=false)
            } catch(e: CancellationException) { throw e }
            catch(_: OutOfMemoryError) { if(token==generation)mutable.value=mutable.value.copy(busy=false,message="메모리가 부족해 처리를 중단했습니다. 선택한 원본은 유지됩니다.") }
            catch(e: Exception) { if(token==generation)mutable.value=mutable.value.copy(busy=false,message=if(e is ExperimentalPhotoException)e.message else "AI 결과의 픽셀·마스크 계약을 확인하지 못했습니다. 선택한 원본은 유지됩니다.") }
            finally { if(token==generation) { requestId=null;service=null } }
        }
    }
    fun cancel() { invalidate();mutable.value=mutable.value.copy(busy=false,importing=false,saving=false,awaitingSave=false,message="작업을 취소했습니다. 선택한 원본은 유지됩니다.") }
    fun discardSession() { invalidate();session?.clear() }
    fun share(context: Context) {
        val state=mutable.value;val result=state.result ?: return
        if(state.hasActiveWork || pendingReplacement!=null || state.pendingShare!=null || !result.presentation.canSaveChangedCopy)return
        val token=generation;mutable.value=state.copy(sharing=true,message=null)
        shareTask=viewModelScope.launch {
            var prepared: ExperimentalPhotoShare?=null
            try {
                prepared=ExperimentalPhotoShareFiles.prepare(context.applicationContext,result)
                coroutineContext.ensureActive()
                if(token==generation && mutable.value.result===result) {
                    mutable.value=mutable.value.copy(sharing=false,pendingShare=prepared);prepared=null
                }
            } catch(e: CancellationException) { throw e }
            catch(_: Exception) { if(token==generation)mutable.value=mutable.value.copy(sharing=false,message="공유 사본을 준비하지 못했습니다. 결과를 저장한 뒤 다시 시도해 주세요.") }
            finally { prepared?.let { ExperimentalPhotoShareFiles.discard(context,it) } }
        }
    }
    fun consumeShare(share: ExperimentalPhotoShare,launched: Boolean) {
        if(mutable.value.pendingShare!=share)return
        if(!launched)app?.let { ExperimentalPhotoShareFiles.discard(it,share) }
        mutable.value=mutable.value.copy(pendingShare=null,message=if(launched)"실험 PNG 공유 화면을 열었습니다. 전달·저장 완료를 의미하지 않습니다." else "공유할 앱을 열지 못했습니다. 결과는 유지됩니다.")
    }
    fun prepareSave(): String? {
        val s=mutable.value;val result=s.result ?: return null
        if(s.hasActiveWork || pendingReplacement!=null || outstandingSaveTicket!=null || !result.presentation.canSaveChangedCopy)return null
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
                if(pending.generation==generation) {
                    session?.markSaved(pending.result.requestId)
                    mutable.value=mutable.value.copy(saving=false,savedResultRequestId=pending.result.requestId,message="검증된 반환 PNG 복사본을 저장했습니다. 전체 지문 보호는 보장되지 않습니다.")
                }
            } catch(e: CancellationException) { throw e }
            catch(_: Exception) { if(pending.generation==generation)mutable.value=mutable.value.copy(saving=false,message="복사본을 저장하지 못했습니다. 원본과 비교 결과는 유지됩니다.") }
            finally {
                if(!complete) try { DocumentsContract.deleteDocument(app.contentResolver,uri) } catch(_: Exception) { /* The provider may not support removing the incomplete new document. */ }
            }
        }
    }
    override fun onCleared() { invalidate();super.onCleared() }
}
