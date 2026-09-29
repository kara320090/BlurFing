package com.blurfing.app.viewmodel

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
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
import com.blurfing.app.utils.ImageSaver
import com.blurfing.app.utils.CameraCaptureFiles
import com.blurfing.app.utils.PhotoImportException
import com.blurfing.app.utils.ProtectedImageDecoder
import com.blurfing.app.utils.SelectedImageLoader
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
        val processingError: String? = null
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
    private val saveImage: suspend (Context, Bitmap) -> Result<Uri> = { context, bitmap ->
        ImageSaver.saveProtectedCopy(context, bitmap)
    }
) : ViewModel() {

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private var activeProcessingJob: Job? = null
    private var activeRequestId: String? = null
    private var activeRepository: ProtectionRepository? = null
    private var imageLoadingJob: Job? = null
    private var activeSavingJob: Job? = null
    private var activeSaveId: String? = null

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
        cancelSaving()
        cancelProtection()
        imageLoadingJob?.cancel()

        _uiState.value = UiState.Loading("사진을 불러오고 방향을 확인하는 중...")

        val job = viewModelScope.launch {
            try {
                val normalizedBitmap = SelectedImageLoader.load(context.applicationContext, uri)

                // 초기 후보 영역 (기본 합성 영역)
                val initialRegions = listOf(
                    NormalizedRegion(x = 0.35f, y = 0.30f, width = 0.12f, height = 0.16f),
                    NormalizedRegion(x = 0.52f, y = 0.28f, width = 0.12f, height = 0.16f)
                )

                _uiState.value = UiState.Ready(
                    step = ScreenStep.REGION_EDITOR,
                    originalUri = uri,
                    originalBitmap = normalizedBitmap,
                    regions = initialRegions
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

    // 영역 편집 (BF-03)
    fun updateRegion(index: Int, region: NormalizedRegion) {
        val current = _uiState.value
        if (current is UiState.Ready && index in current.regions.indices) {
            val updated = current.regions.toMutableList().apply { set(index, region) }
            _uiState.value = current.copy(regions = updated)
        }
    }

    fun addRegion() {
        val current = _uiState.value
        if (current is UiState.Ready) {
            val newRegion = NormalizedRegion(x = 0.4f, y = 0.4f, width = 0.15f, height = 0.15f)
            _uiState.value = current.copy(regions = current.regions + newRegion)
        }
    }

    fun deleteRegion(index: Int) {
        val current = _uiState.value
        if (current is UiState.Ready && index in current.regions.indices) {
            val updated = current.regions.toMutableList().apply { removeAt(index) }
            _uiState.value = current.copy(regions = updated)
        }
    }

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
            isSaving = false, savePermissionRequestId = null, saveError = null
        )
        _uiState.value = pending

        activeProcessingJob = viewModelScope.launch {
            try {
                val imageBytes = withContext(Dispatchers.IO) {
                    ByteArrayOutputStream().use { stream ->
                        check(current.originalBitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                            "사진을 전송 형식으로 변환하지 못했습니다."
                        }
                        stream.toByteArray()
                    }
                }
                val request = ProtectionRequest(requestId, method, strength, current.regions)
                val response = repository.protectImage(request, imageBytes).getOrThrow()
                if (activeRequestId != requestId) return@launch
                ProtectionResponseValidator.validate(response, requestId)
                val protectedBitmap = withContext(Dispatchers.Default) {
                    ProtectedImageDecoder.decode(response, current.originalBitmap, strength)
                }
                if (activeRequestId != requestId) return@launch
                _uiState.value = pending.copy(
                    step = ScreenStep.COMPARISON, isProcessing = false,
                    protectedBitmap = protectedBitmap, protectionResponse = response
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
        if (current.step != ScreenStep.COMPARISON || current.isProcessing || current.isSaving ||
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
        val saveId = UUID.randomUUID().toString()
        activeSaveId = saveId
        _uiState.value = current.copy(isSaving = true, saveMessage = null, saveError = null)

        activeSavingJob = viewModelScope.launch {
            try {
                saveImage(context.applicationContext, protectedBitmap).getOrThrow()
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

    private fun cancelSaving() {
        // 먼저 식별자를 무효화해 취소가 늦게 반영되는 저장도 이전 화면을 되살리지 못하게 한다.
        activeSaveId = null
        activeSavingJob?.cancel()
        activeSavingJob = null
        val current = _uiState.value as? UiState.Ready ?: return
        _uiState.value = current.copy(isSaving = false, savePermissionRequestId = null, saveMessage = null, saveError = null)
    }

    fun resetToIdle() {
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
