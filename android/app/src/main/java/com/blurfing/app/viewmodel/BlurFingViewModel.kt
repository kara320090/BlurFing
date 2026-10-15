package com.blurfing.app.viewmodel

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.SystemClock
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.blurfing.app.BuildConfig
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionMethod
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.repository.MockProtectionRepository
import com.blurfing.app.repository.ApiProtectionRepository
import com.blurfing.app.repository.BackendAddress
import com.blurfing.app.repository.ProtectionResponseValidator
import com.blurfing.app.repository.ProtectionRepository
import com.blurfing.app.repository.BackendReadiness
import com.blurfing.app.repository.BackendReadinessClient
import com.blurfing.app.repository.ReadinessKind
import com.blurfing.app.utils.ImageSaver
import com.blurfing.app.utils.ProtectedShare
import com.blurfing.app.utils.ProtectedShareFiles
import com.blurfing.app.utils.CameraCaptureFiles
import com.blurfing.app.utils.PhotoImportException
import com.blurfing.app.utils.ProtectedImageDecoder
import com.blurfing.app.utils.SelectedImageLoader
import com.blurfing.app.utils.DraftSession
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.model.ProcessingSettingsStore
import com.blurfing.app.model.RegionEditHistory
import com.blurfing.app.model.ProcessingTiming
import com.blurfing.app.model.ProcessingRunInfo
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.util.UUID

/**
 * 네비게이션 화면 단계 열거형
 */
enum class ScreenStep {
    IMAGE_PICKER,
    REGION_EDITOR,
    PROCESSING,
    COMPARISON
}

enum class BackNavigationResult { UNHANDLED, NAVIGATED, CONFIRM_PROCESSING_CANCEL }

/**
 * UI State for BlurFing application workflow.
 */
sealed interface UiState {
    object Idle : UiState
    data class Loading(val message: String) : UiState
    data class Ready(
        val step: ScreenStep,
        val originalUri: Uri,
        val originalBitmap: Bitmap,
        val regions: List<NormalizedRegion>,
        val isProcessing: Boolean = false,
        val protectedBitmap: Bitmap? = null,
        val protectionResponse: ProtectionResponse? = null,
        val isSaving: Boolean = false,
        val savePermissionRequestId: String? = null,
        val saveError: String? = null,
        val saveMessage: String? = null,
        val processingError: String? = null,
        val sessionNotice: String? = null,
        val canUndoRegions: Boolean = false,
        val canRedoRegions: Boolean = false,
        val isSharing: Boolean = false,
        val pendingShare: ProtectedShare? = null,
        val shareError: String? = null,
        val processingTiming: ProcessingTiming? = null,
        val processingRun: ProcessingRunInfo? = null
    ) : UiState
    data class Error(
        val message: String,
        val cause: Throwable? = null,
        val retryable: Boolean = true
    ) : UiState
}

open class BlurFingViewModel(
    private val protectionRepository: ProtectionRepository = MockProtectionRepository(),
    private val apiRepositoryFactory: (String) -> ProtectionRepository = { ApiProtectionRepository(it) },
    private val saveImage: (suspend (Context, Bitmap) -> Result<Uri>)? = null,
    private val draftSession: DraftSession? = null,
    private val settingsStore: ProcessingSettingsStore? = null,
    private val readinessCheck: suspend (String) -> BackendReadiness = { BackendReadinessClient().check(it) },
    private val prepareShare: suspend (Context, Bitmap, ProcessingSettings, Boolean) -> ProtectedShare =
        { context, bitmap, settings, mock -> ProtectedShareFiles.prepare(context, bitmap, settings, mock) },
    private val monotonicMs: () -> Long = SystemClock::elapsedRealtime
) : ViewModel() {

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()
    private val _settings = MutableStateFlow(settingsStore?.load() ?: ProcessingSettings())
    val settings: StateFlow<ProcessingSettings> = _settings.asStateFlow()
    private val _readiness = MutableStateFlow(BackendReadiness.Idle)
    val readiness: StateFlow<BackendReadiness> = _readiness.asStateFlow()
    private var readinessJob: Job? = null
    private var readinessId: String? = null

    fun updateSettings(settings: ProcessingSettings) {
        val current = _uiState.value as? UiState.Ready
        if (current?.isProcessing == true || current?.isSaving == true || current?.isSharing == true || current?.savePermissionRequestId != null) return
        if (!settings.strength.isFinite() || settings.strength !in 0.1f..1f) return
        if (settings.jpegQuality !in 80..100) return
        val normalized = settings.copy(serverAddress = settings.serverAddress.take(2048))
        if(normalized.serverAddress != _settings.value.serverAddress || normalized.useServer != _settings.value.useServer) clearReadiness()
        _settings.value = normalized
        settingsStore?.save(normalized)
    }

    fun checkBackendReadiness() {
        if((_uiState.value as? UiState.Ready)?.isProcessing == true || !_settings.value.useServer) return
        clearReadiness()
        val address = try { BackendAddress.normalize(_settings.value.serverAddress,BuildConfig.DEBUG) }
            catch (_: IllegalArgumentException) {
                _readiness.value=BackendReadiness(ReadinessKind.ERROR,"서버 주소를 확인해 주세요."); return
            }
        val id=UUID.randomUUID().toString()
        readinessId=id
        _readiness.value=BackendReadiness.Checking
        readinessJob=viewModelScope.launch {
            try {
                val result=readinessCheck(address)
                if(readinessId==id) _readiness.value=result
            } catch(error: CancellationException) { throw error }
            catch(_: Exception) { if(readinessId==id) _readiness.value=BackendReadiness(ReadinessKind.ERROR,"서버 준비 상태를 확인하지 못했습니다.") }
            finally { if(readinessId==id) { readinessId=null; readinessJob=null } }
        }
    }

    private fun clearReadiness() {
        readinessId=null; readinessJob?.cancel(); readinessJob=null
        _readiness.value=BackendReadiness.Idle
    }

    private var activeProcessingJob: Job? = null
    private var activeRequestId: String? = null
    private var activeRepository: ProtectionRepository? = null
    private var imageLoadingJob: Job? = null
    private var activeSavingJob: Job? = null
    private var activeSaveId: String? = null
    private var sharingJob: Job? = null
    private var shareId: String? = null
    private val regionHistory = RegionEditHistory()

    init {
        if (draftSession?.hasDraft == true) {
            _uiState.value = UiState.Loading("이전 사진과 수정 영역을 복원하는 중...")
            imageLoadingJob = viewModelScope.launch {
                try {
                    val restored = draftSession.restore()
                    _uiState.value = UiState.Ready(ScreenStep.REGION_EDITOR, Uri.EMPTY,
                        restored.bitmap, restored.regions,
                        sessionNotice = "이전 사진과 영역을 복원했습니다. 보호 결과는 다시 처리해 주세요.")
                } catch (error: CancellationException) {
                    throw error
                } catch (_: Exception) {
                    draftSession.clear()
                    _uiState.value = UiState.Error("이전 사진을 복원할 수 없습니다. 사진을 다시 선택해 주세요.")
                }
            }
        }
        viewModelScope.launch { draftSession?.removeExpired() }
    }

    /**
     * 사진 선택 및 EXIF 정규화 (BF-01, BF-02).
     */
    fun onImageSelected(uri: Uri?, context: Context) {
        if (uri == null) return
        importImage(uri, context)
    }

    fun onCameraImageCaptured(uri: Uri, context: Context): Job? {
        if (!CameraCaptureFiles.isOwned(context, uri)) return null
        return importImage(uri, context) {
            CameraCaptureFiles.discard(context.applicationContext, uri)
        }
    }

    private fun importImage(uri: Uri, context: Context, onFinished: (() -> Unit)? = null): Job {
        regionHistory.clear()
        cancelSaving()
        cancelProtection()
        imageLoadingJob?.cancel()
        draftSession?.clear()

        _uiState.value = UiState.Loading("사진을 불러오고 방향을 확인하는 중...")

        val job = viewModelScope.launch {
            try {
                val normalizedBitmap = SelectedImageLoader.load(context.applicationContext, uri)

                // 자동 탐지 모듈이 연결되기 전에는 임의의 후보를 만들지 않는다.
                val initialRegions = emptyList<NormalizedRegion>()

                var sessionNotice: String? = null
                if (draftSession != null) {
                    try {
                        val token = draftSession.create(normalizedBitmap)
                        draftSession.attach(token, initialRegions)
                    } catch (error: CancellationException) {
                        normalizedBitmap.recycle()
                        throw error
                    } catch (_: Exception) {
                        sessionNotice = "임시 복원 파일을 만들지 못했습니다. 앱이 종료되면 사진을 다시 선택해야 합니다."
                    }
                }

                _uiState.value = UiState.Ready(
                    step = ScreenStep.REGION_EDITOR,
                    originalUri = uri,
                    originalBitmap = normalizedBitmap,
                    regions = initialRegions,
                    sessionNotice = sessionNotice
                )
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _uiState.value = UiState.Error(
                    message = if (e is PhotoImportException) e.message.orEmpty()
                        else "사진을 불러오지 못했습니다. 다른 사진을 선택해 주세요.",
                    cause = e,
                    retryable = true
                )
            }
        }
        imageLoadingJob = job
        // Completion handlers also run if cancellation happens before the coroutine starts.
        if (onFinished != null) job.invokeOnCompletion { onFinished() }
        return job
    }

    fun navigateToStep(step: ScreenStep) {
        val current = _uiState.value
        if (current is UiState.Ready && !current.isProcessing) {
            if (step != current.step) cancelSaving()
            val latest = _uiState.value as? UiState.Ready ?: return
            _uiState.value = latest.copy(step = step, processingError = null)
        }
    }

    /** System Back follows the screen buttons; an active request needs user confirmation. */
    fun onBackRequested(): BackNavigationResult {
        val current = _uiState.value as? UiState.Ready ?: return BackNavigationResult.UNHANDLED
        if (current.isProcessing) return BackNavigationResult.CONFIRM_PROCESSING_CANCEL
        when (current.step) {
            ScreenStep.PROCESSING, ScreenStep.COMPARISON -> navigateToStep(ScreenStep.REGION_EDITOR)
            ScreenStep.REGION_EDITOR, ScreenStep.IMAGE_PICKER -> resetToIdle()
        }
        return BackNavigationResult.NAVIGATED
    }

    // 영역 편집 (BF-03)
    fun updateRegion(index: Int, region: NormalizedRegion) {
        val current = _uiState.value
        if (current is UiState.Ready && index in current.regions.indices) {
            val updated = current.regions.toMutableList().apply { set(index, region) }
            applyRegions(updated)
        }
    }

    fun addRegion() {
        val current = _uiState.value
        if (current is UiState.Ready) {
            val newRegion = NormalizedRegion(x = 0.4f, y = 0.4f, width = 0.15f, height = 0.15f)
            applyRegions(current.regions + newRegion)
        }
    }

    fun deleteRegion(index: Int) {
        val current = _uiState.value
        if (current is UiState.Ready && index in current.regions.indices) {
            val updated = current.regions.toMutableList().apply { removeAt(index) }
            applyRegions(updated)
        }
    }

    private fun applyRegions(updated: List<NormalizedRegion>, record: Boolean = true) {
        val current = _uiState.value as? UiState.Ready ?: return
        if (current.isProcessing || current.step != ScreenStep.REGION_EDITOR || updated == current.regions) return
        if (record) regionHistory.record(current.regions)
        cancelSaving()
        val latest = _uiState.value as? UiState.Ready ?: return
        _uiState.value = latest.copy(regions = updated.toList(), protectedBitmap = null,
            protectionResponse = null, processingError = null, processingTiming = null, processingRun = null,
            canUndoRegions = regionHistory.canUndo, canRedoRegions = regionHistory.canRedo)
        draftSession?.updateRegions(updated)
    }

    fun undoRegions() {
        val current = _uiState.value as? UiState.Ready ?: return
        if (current.step != ScreenStep.REGION_EDITOR || current.isProcessing) return
        regionHistory.undo(current.regions)?.let { applyRegions(it, false) }
    }

    fun redoRegions() {
        val current = _uiState.value as? UiState.Ready ?: return
        if (current.step != ScreenStep.REGION_EDITOR || current.isProcessing) return
        regionHistory.redo(current.regions)?.let { applyRegions(it, false) }
    }

    fun clearRegions() { applyRegions(emptyList()) }

    /**
     * 보호 처리 실행 (BF-04, BF-05, BF-07).
     */
    fun startProtection(
        method: ProtectionMethod = ProtectionMethod.GAUSSIAN_BLUR,
        strength: Float = 0.5f,
        serverUrl: String? = null
    ) {
        val current = _uiState.value as? UiState.Ready ?: return
        if (current.isProcessing) return
        val repository = try {
            require(strength.isFinite() && strength in 0f..1f) { "보호 강도를 확인해 주세요." }
            require(current.regions.isNotEmpty()) { "손끝 영역을 한 개 이상 지정해 주세요." }
            if (serverUrl == null) protectionRepository else {
                apiRepositoryFactory(BackendAddress.normalize(serverUrl, BuildConfig.DEBUG))
            }
        } catch (e: IllegalArgumentException) {
            _uiState.value = current.copy(processingError = e.message)
            return
        }

        cancelSaving()
        val requestId = UUID.randomUUID().toString()
        activeRequestId = requestId
        activeRepository = repository
        // 이전 결과가 새 요청의 결과처럼 저장되지 않도록 지운다.
        val pending = current.copy(
            step = ScreenStep.PROCESSING, isProcessing = true, processingError = null,
            protectedBitmap = null, protectionResponse = null, saveMessage = null,
            isSaving = false, savePermissionRequestId = null, saveError = null,
            isSharing = false, pendingShare = null, shareError = null,
            processingTiming = null, processingRun = null
        )
        _uiState.value = pending

        activeProcessingJob = viewModelScope.launch {
            try {
                val started = monotonicMs()
                val imageBytes = withContext(Dispatchers.IO) {
                    ByteArrayOutputStream().use { stream ->
                        check(current.originalBitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                            "사진을 전송 형식으로 변환하지 못했습니다."
                        }
                        stream.toByteArray()
                    }
                }
                val encoded = monotonicMs()
                val request = ProtectionRequest(requestId, method, strength, current.regions)
                val response = repository.protectImage(request, imageBytes).getOrThrow()
                val received = monotonicMs()
                if (activeRequestId != requestId) return@launch
                ProtectionResponseValidator.validate(response, requestId)
                val protectedBitmap = withContext(Dispatchers.Default) {
                    ProtectedImageDecoder.decode(response, current.originalBitmap, strength)
                }
                val decoded = monotonicMs()
                if (activeRequestId != requestId) return@launch
                _uiState.value = pending.copy(
                    step = ScreenStep.COMPARISON, isProcessing = false,
                    protectedBitmap = protectedBitmap, protectionResponse = response,
                    processingTiming = ProcessingTiming.between(started, encoded, received, decoded),
                    processingRun = ProcessingRunInfo(method, strength, serverUrl != null)
                )
            } catch (e: CancellationException) {
                if (activeRequestId == requestId) {
                    _uiState.value = pending.copy(isProcessing = false)
                }
                throw e
            } catch (e: Exception) {
                if (activeRequestId == requestId) {
                    // 사진·수정 영역을 유지해 설정 화면에서 바로 재시도할 수 있다.
                    _uiState.value = pending.copy(
                        isProcessing = false,
                        processingError = e.localizedMessage ?: "처리하지 못했습니다. 다시 시도해 주세요."
                    )
                }
            } finally {
                if (activeRequestId == requestId) {
                    activeRequestId = null
                    activeProcessingJob = null
                    activeRepository = null
                }
            }
        }
    }

    /**
     * 진행 중인 요청 취소 (BF-07).
     */
    fun cancelProtection() {
        val id = activeRequestId
        activeRequestId = null
        id?.let { activeRepository?.cancelRequest(it) }
        activeRepository = null
        activeProcessingJob?.cancel()
        activeProcessingJob = null

        val current = _uiState.value
        if (current is UiState.Ready) {
            _uiState.value = current.copy(isProcessing = false)
        }
    }

    /**
     * 보호된 사본 저장 (BF-06). 권한이 필요한 경우 UI가 요청할 식별자를 반환한다.
     */
    fun saveProtectedImage(context: Context): String? {
        val current = _uiState.value as? UiState.Ready ?: return null
        if (current.step != ScreenStep.COMPARISON || current.isProcessing || current.isSaving || current.isSharing ||
            current.savePermissionRequestId != null || current.protectedBitmap == null) return null
        if (!hasStoragePermission(context)) {
            val requestId = UUID.randomUUID().toString()
            _uiState.value = current.copy(savePermissionRequestId = requestId, saveError = null, saveMessage = null)
            return requestId
        }
        writeProtectedImage(context, current)
        return null
    }

    fun onSavePermissionResult(context: Context, requestId: String, granted: Boolean) {
        val current = _uiState.value as? UiState.Ready ?: return
        if (current.savePermissionRequestId != requestId || current.step != ScreenStep.COMPARISON) return
        val ready = current.copy(savePermissionRequestId = null)
        _uiState.value = ready
        if (granted && hasStoragePermission(context)) {
            writeProtectedImage(context, ready)
        } else {
            _uiState.value = ready.copy(
                saveError = "사본을 저장하려면 저장 공간 접근 권한이 필요합니다. 다시 시도하거나 앱 설정에서 권한을 허용해 주세요.",
                saveMessage = null
            )
        }
    }

    private fun hasStoragePermission(context: Context): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED

    private fun writeProtectedImage(context: Context, current: UiState.Ready) {
        val protectedBitmap = current.protectedBitmap ?: return
        val exportSettings = _settings.value
        val saveId = UUID.randomUUID().toString()
        activeSaveId = saveId
        _uiState.value = current.copy(isSaving = true, saveMessage = null, saveError = null)

        activeSavingJob = viewModelScope.launch {
            try {
                (saveImage?.invoke(context.applicationContext, protectedBitmap)
                    ?: ImageSaver.saveProtectedCopy(context.applicationContext,protectedBitmap,
                        exportSettings.exportFormat.compression,exportSettings.jpegQuality)).getOrThrow()
                if (activeSaveId != saveId) return@launch
                val latest = _uiState.value as? UiState.Ready ?: return@launch
                _uiState.value = latest.copy(
                    saveMessage = "보호 사본을 갤러리에 저장했습니다. 원본은 유지됩니다.",
                    saveError = null
                )
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (activeSaveId == saveId) {
                    val latest = _uiState.value as? UiState.Ready ?: return@launch
                    _uiState.value = latest.copy(
                        saveError = "사본을 저장하지 못했습니다. 저장 공간과 사진 접근 권한을 확인한 뒤 다시 시도해 주세요.",
                        saveMessage = null
                    )
                }
            } finally {
                if (activeSaveId == saveId) {
                    activeSaveId = null
                    activeSavingJob = null
                    val latest = _uiState.value as? UiState.Ready
                    if (latest != null) _uiState.value = latest.copy(isSaving = false)
                }
            }
        }
    }

    fun shareProtectedImage(context: Context) {
        val current = _uiState.value as? UiState.Ready ?: return
        val bitmap = current.protectedBitmap ?: return
        val response = current.protectionResponse ?: return
        if (current.step != ScreenStep.COMPARISON || current.isProcessing || current.isSaving ||
            current.isSharing || current.pendingShare != null || current.savePermissionRequestId != null) return
        val id = UUID.randomUUID().toString()
        val settings = _settings.value
        shareId = id
        _uiState.value = current.copy(isSharing = true, shareError = null)
        sharingJob = viewModelScope.launch {
            try {
                val share = prepareShare(context.applicationContext, bitmap, settings, response.resultKind == "mock")
                if (shareId != id) return@launch
                val latest = _uiState.value as? UiState.Ready ?: return@launch
                _uiState.value = latest.copy(pendingShare = share, isSharing = false)
            } catch (error: CancellationException) { throw error }
            catch (_: Exception) {
                if (shareId == id) {
                    val latest = _uiState.value as? UiState.Ready
                    if (latest != null) _uiState.value = latest.copy(isSharing = false,
                        shareError = "공유 사본을 준비하지 못했습니다. 저장 공간을 확인한 뒤 다시 시도해 주세요.")
                }
            } finally { if (shareId == id) { shareId = null; sharingJob = null } }
        }
    }

    fun consumeShare(share: ProtectedShare, launched: Boolean) {
        val current = _uiState.value as? UiState.Ready ?: return
        if (current.pendingShare != share) return
        _uiState.value = current.copy(pendingShare = null,
            shareError = if (launched) null else "공유할 앱을 열지 못했습니다. 사본을 저장한 뒤 공유해 주세요.")
    }

    private fun cancelSaving() {
        shareId = null
        sharingJob?.cancel()
        sharingJob = null
        // 먼저 식별자를 무효화해 취소가 늦게 반영되는 저장도 이전 화면을 되살리지 못하게 한다.
        activeSaveId = null
        activeSavingJob?.cancel()
        activeSavingJob = null
        val current = _uiState.value as? UiState.Ready ?: return
        _uiState.value = current.copy(isSaving = false, savePermissionRequestId = null, saveMessage = null, saveError = null,
            isSharing = false, pendingShare = null, shareError = null)
    }

    fun resetToIdle() {
        clearReadiness()
        regionHistory.clear()
        draftSession?.clear()
        cancelSaving()
        imageLoadingJob?.cancel()
        imageLoadingJob = null
        cancelProtection()
        _uiState.value = UiState.Idle
    }

    fun clearError() {
        if (_uiState.value is UiState.Error) {
            _uiState.value = UiState.Idle
        }
    }
}
