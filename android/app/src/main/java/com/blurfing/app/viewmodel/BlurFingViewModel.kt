package com.blurfing.app.viewmodel

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionMethod
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.repository.MockProtectionRepository
import com.blurfing.app.repository.ProtectionRepository
import com.blurfing.app.utils.ExifNormalizer
import com.blurfing.app.utils.ImageSaver
import com.blurfing.app.utils.LocalBlurProcessor
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
import java.io.InputStream
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
        val saveMessage: String? = null
    ) : UiState
    data class Error(
        val message: String,
        val cause: Throwable? = null,
        val retryable: Boolean = true
    ) : UiState
}

open class BlurFingViewModel(
    private val protectionRepository: ProtectionRepository = MockProtectionRepository()
) : ViewModel() {

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    private var activeProcessingJob: Job? = null
    private var activeRequestId: String? = null

    /**
     * 사진 선택 및 EXIF 정규화 (BF-01, BF-02).
     */
    fun onImageSelected(uri: Uri?, context: Context) {
        if (uri == null) return

        _uiState.value = UiState.Loading("사진을 불러오고 방향을 확인하는 중...")

        viewModelScope.launch {
            try {
                val normalizedBitmap = withContext(Dispatchers.IO) {
                    val inputStream: InputStream? = context.contentResolver.openInputStream(uri)
                    requireNotNull(inputStream) { "이미지 파일을 열 수 없습니다: $uri" }
                    val rawBitmap = inputStream.use { stream ->
                        BitmapFactory.decodeStream(stream)
                    } ?: throw IllegalStateException("유효한 이미지 형식이 아닙니다.")

                    ExifNormalizer.getNormalizedBitmap(context, uri, rawBitmap)
                }

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
            } catch (e: Exception) {
                _uiState.value = UiState.Error(
                    message = "사진을 불러오지 못했습니다: ${e.localizedMessage ?: "알 수 없는 오류"}",
                    cause = e,
                    retryable = true
                )
            }
        }
    }

    fun navigateToStep(step: ScreenStep) {
        val current = _uiState.value
        if (current is UiState.Ready) {
            _uiState.value = current.copy(step = step)
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
        strength: Float = 0.5f
    ) {
        val current = _uiState.value as? UiState.Ready ?: return
        if (current.isProcessing) return // 중복 실행 방지

        val requestId = UUID.randomUUID().toString()
        activeRequestId = requestId

        _uiState.value = current.copy(isProcessing = true)

        activeProcessingJob = viewModelScope.launch {
            try {
                // 이미지 바이트 변환
                val imageBytes = withContext(Dispatchers.IO) {
                    val stream = ByteArrayOutputStream()
                    current.originalBitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
                    stream.toByteArray()
                }

                val request = ProtectionRequest(
                    requestId = requestId,
                    method = method,
                    strength = strength,
                    regions = current.regions
                )

                val result = protectionRepository.protectImage(request, imageBytes)

                // 취소되거나 다른 요청으로 교체된 경우 늦은 응답 무시
                if (activeRequestId != requestId) {
                    return@launch
                }

                result.fold(
                    onSuccess = { response ->
                        // 로컬 프리뷰 블러 적용 (실제 서버 응답 시에는 서버 이미지 사용)
                        val protectedBitmap = LocalBlurProcessor.applyBlur(
                            sourceBitmap = current.originalBitmap,
                            regions = response.appliedRegions.ifEmpty { current.regions },
                            strength = strength
                        )

                        _uiState.value = current.copy(
                            step = ScreenStep.COMPARISON,
                            isProcessing = false,
                            protectedBitmap = protectedBitmap,
                            protectionResponse = response
                        )
                    },
                    onFailure = { error ->
                        if (error is CancellationException) {
                            _uiState.value = current.copy(isProcessing = false)
                        } else {
                            _uiState.value = UiState.Error(
                                message = "보호 처리에 실패했습니다: ${error.localizedMessage}",
                                cause = error,
                                retryable = true
                            )
                        }
                    }
                )
            } catch (e: CancellationException) {
                _uiState.value = current.copy(isProcessing = false)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(
                    message = "처리 중 오류 발생: ${e.localizedMessage}",
                    cause = e,
                    retryable = true
                )
            } finally {
                if (activeRequestId == requestId) {
                    activeRequestId = null
                    activeProcessingJob = null
                }
            }
        }
    }

    /**
     * 진행 중인 요청 취소 (BF-07).
     */
    fun cancelProtection() {
        activeRequestId?.let { id ->
            protectionRepository.cancelRequest(id)
            activeRequestId = null
        }
        activeProcessingJob?.cancel()
        activeProcessingJob = null

        val current = _uiState.value
        if (current is UiState.Ready) {
            _uiState.value = current.copy(isProcessing = false)
        }
    }

    /**
     * 보호된 사본 저장 (BF-06). 원본을 덮어쓰지 않습니다.
     */
    fun saveProtectedImage(context: Context) {
        val current = _uiState.value as? UiState.Ready ?: return
        val protectedBitmap = current.protectedBitmap ?: return

        viewModelScope.launch {
            val result = ImageSaver.saveProtectedCopy(context, protectedBitmap)
            result.fold(
                onSuccess = { uri ->
                    _uiState.value = current.copy(
                        saveMessage = "보호된 사본이 저장되었습니다 (원본 보존): $uri"
                    )
                },
                onFailure = { error ->
                    _uiState.value = UiState.Error(
                        message = "사본 저장에 실패했습니다: ${error.localizedMessage}",
                        cause = error,
                        retryable = true
                    )
                }
            )
        }
    }

    fun resetToIdle() {
        cancelProtection()
        _uiState.value = UiState.Idle
    }

    fun clearError() {
        if (_uiState.value is UiState.Error) {
            _uiState.value = UiState.Idle
        }
    }
}
